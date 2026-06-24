"""
dashboard.py - Web Dashboard + Watchdog for BY BOTS

A browser-based control panel that also acts as a watchdog:
  - View and edit all configuration settings (.env)
  - Start / stop / restart the bot
  - Auto-restart watchdog with exponential back-off (toggle via UI)
  - Live log streaming
  - Statistics & recent-posts view

Usage:
    python dashboard.py [--host 0.0.0.0] [--port 5000]

Then open http://localhost:5000 in your browser.
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Tuple

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from dotenv import load_dotenv, set_key, find_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
LOG_FILE = BASE_DIR / "logs" / "bybots.log"
WATCHDOG_LOG_FILE = BASE_DIR / "logs" / "watchdog.log"
PID_FILE = BASE_DIR / ".bybots.service.pid"
LOCK_FILE = BASE_DIR / ".bybots.lock"

# ── Dashboard logging ─────────────────────────────────────────────────────────
BASE_DIR.joinpath("logs").mkdir(exist_ok=True)
_dash_logger = logging.getLogger("dashboard")
if not _dash_logger.handlers:
    _h = logging.handlers.RotatingFileHandler(
        WATCHDOG_LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    _h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _dash_logger.addHandler(_h)
    _dash_logger.addHandler(logging.StreamHandler(sys.stdout))
    _dash_logger.setLevel(logging.INFO)


def get_database_path() -> Path:
    """Resolve database path from environment."""
    load_dotenv(ENV_FILE, override=True)
    db_path = os.getenv("DATABASE_PATH", "database.db").strip()
    path = Path(db_path)
    return path if path.is_absolute() else BASE_DIR / path


# ── Flask ─────────────────────────────────────────────────────────────────────
load_dotenv(ENV_FILE)
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_SECRET_KEY = os.getenv(
    "DASHBOARD_SECRET_KEY", "bybots-dashboard-secret-change-me"
)

app = Flask(__name__)
app.secret_key = DASHBOARD_SECRET_KEY


@app.context_processor
def inject_bot_status():
    return {"bot_running": is_bot_running(), "bot_pid": get_bot_pid()}


# ── Watchdog thread ───────────────────────────────────────────────────────────
class _WatchdogThread(threading.Thread):
    """
    Background thread that monitors bot.py and auto-restarts it on crash.
    Lives for the lifetime of the dashboard process.
    Can be paused/resumed via the .enabled flag.
    """

    MAX_RESTARTS = 5
    BASE_COOLDOWN = 5      # seconds
    STABLE_AFTER = 300     # seconds of continuous uptime → reset counter

    def __init__(self):
        super().__init__(daemon=True, name="watchdog")
        self.enabled = False          # Toggled by the UI
        self._stop_event = threading.Event()
        self._restart_count = 0
        self._process: Optional[subprocess.Popen] = None
        self._status = "idle"         # idle | running | restarting | failed | disabled

    # -- Public API -----------------------------------------------------------

    def stop_watchdog(self):
        self._stop_event.set()
        self._kill_bot()

    def enable(self):
        self.enabled = True
        self._restart_count = 0
        self._stop_event.clear()
        _dash_logger.info("Watchdog enabled.")

    def disable(self):
        self.enabled = False
        _dash_logger.info("Watchdog disabled — bot will not be auto-restarted.")

    @property
    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "state": self._status,
            "restart_count": self._restart_count,
            "max_restarts": self.MAX_RESTARTS,
        }

    # -- Internals ------------------------------------------------------------

    def _kill_bot(self):
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            except Exception:
                pass
        self._process = None

    def _cooldown(self) -> int:
        return min(self.BASE_COOLDOWN * (2 ** self._restart_count), 300)

    def _start_bot_process(self) -> subprocess.Popen:
        _dash_logger.info("Watchdog: launching bot.py (attempt %d)…", self._restart_count + 1)
        kwargs: dict = {
            "cwd": str(BASE_DIR),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        return subprocess.Popen([sys.executable, str(BASE_DIR / "bot.py")], **kwargs)

    def run(self):
        while not self._stop_event.is_set():
            if not self.enabled:
                self._status = "disabled"
                time.sleep(1)
                continue

            if self._restart_count >= self.MAX_RESTARTS:
                _dash_logger.error(
                    "Watchdog: reached max restarts (%d). Disabling auto-restart.",
                    self.MAX_RESTARTS,
                )
                self._status = "failed"
                self.enabled = False
                continue

            try:
                self._process = self._start_bot_process()
                self._status = "running"
                start_ts = time.time()

                while not self._stop_event.is_set():
                    rc = self._process.poll()
                    if rc is not None:
                        runtime = time.time() - start_ts
                        _dash_logger.warning(
                            "Watchdog: bot exited (rc=%d) after %.1fs.", rc, runtime
                        )
                        if runtime >= self.STABLE_AFTER:
                            if self._restart_count > 0:
                                _dash_logger.info("Watchdog: resetting restart counter (stable run).")
                            self._restart_count = 0
                        else:
                            self._restart_count += 1

                        if not self.enabled or self._restart_count >= self.MAX_RESTARTS:
                            self._status = "failed" if self._restart_count >= self.MAX_RESTARTS else "idle"
                            break

                        cooldown = self._cooldown()
                        self._status = "restarting"
                        _dash_logger.info(
                            "Watchdog: restarting in %ds (attempt %d/%d)…",
                            cooldown,
                            self._restart_count,
                            self.MAX_RESTARTS,
                        )
                        for _ in range(cooldown * 10):
                            if self._stop_event.is_set():
                                break
                            time.sleep(0.1)
                        break  # re-enter outer loop to launch fresh process

                    # Drain stdout → watchdog log
                    try:
                        line = self._process.stdout.readline()
                        if line:
                            _dash_logger.debug("[BOT] %s", line.rstrip())
                    except Exception:
                        pass

                    # Stable-run counter reset
                    if time.time() - start_ts >= self.STABLE_AFTER and self._restart_count > 0:
                        _dash_logger.info("Watchdog: resetting restart counter (stable run).")
                        self._restart_count = 0

                    time.sleep(0.1)

            except Exception as exc:
                _dash_logger.error("Watchdog loop error: %s", exc, exc_info=True)
                self._restart_count += 1
                time.sleep(self._cooldown())

        self._kill_bot()
        self._status = "idle"
        _dash_logger.info("Watchdog thread stopped.")


_watchdog = _WatchdogThread()
_watchdog.start()


# ── Process helpers ───────────────────────────────────────────────────────────

def _is_process_running(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except (OSError, AttributeError):
        return False


def _read_pid_file(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _cleanup_stale_lock() -> None:
    pid = _read_pid_file(LOCK_FILE)
    if LOCK_FILE.exists() and (pid is None or not _is_process_running(pid)):
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass


def is_bot_running() -> bool:
    pid = get_bot_pid()
    if pid is not None and _is_process_running(pid):
        return True
    # Also check watchdog-managed process
    if _watchdog._process and _watchdog._process.poll() is None:
        return True
    _cleanup_stale_lock()
    return False


def get_bot_pid() -> Optional[int]:
    for path in (LOCK_FILE, PID_FILE):
        pid = _read_pid_file(path)
        if pid is not None and _is_process_running(pid):
            return pid
    if _watchdog._process and _watchdog._process.poll() is None:
        return _watchdog._process.pid
    return None


# ── Config helpers ────────────────────────────────────────────────────────────

def get_config() -> Dict[str, Any]:
    load_dotenv(ENV_FILE, override=True)
    cfg = {
        "DISCORD_TOKEN": os.getenv("DISCORD_TOKEN", ""),
        "DISCORD_CHANNEL_ID": os.getenv("DISCORD_CHANNEL_ID", ""),
        "DISCORD_GUILD_ID": os.getenv("DISCORD_GUILD_ID", ""),
        "DISCORD_PING_ROLE_ID": os.getenv("DISCORD_PING_ROLE_ID", ""),
        "DISCORD_STREAMER_CHANNEL_ID": os.getenv("DISCORD_STREAMER_CHANNEL_ID", ""),
        "FACEBOOK_SOURCES": os.getenv("FACEBOOK_SOURCES", ""),
        "FACEBOOK_GROUP_URL": os.getenv("FACEBOOK_GROUP_URL", ""),
        "FILTER_BY_AUTHOR": os.getenv("FILTER_BY_AUTHOR", "false"),
        "ALLOWED_AUTHORS": os.getenv("ALLOWED_AUTHORS", ""),
        "CHECK_INTERVAL": os.getenv("CHECK_INTERVAL", "300"),
        "SEED_ON_FIRST_RUN": os.getenv("SEED_ON_FIRST_RUN", "true"),
        "DATABASE_PATH": os.getenv("DATABASE_PATH", "database.db"),
        "LOG_MAX_BYTES": os.getenv("LOG_MAX_BYTES", "5242880"),
        "LOG_BACKUP_COUNT": os.getenv("LOG_BACKUP_COUNT", "3"),
    }
    routes: Dict[str, str] = {}
    colors: Dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("DISCORD_ROUTE_COLOR_"):
            colors[key[len("DISCORD_ROUTE_COLOR_"):]] = value
        elif key.startswith("DISCORD_ROUTE_"):
            routes[key[len("DISCORD_ROUTE_"):]] = value
    cfg["DISCORD_ROUTES"] = routes
    cfg["DISCORD_ROUTE_COLORS"] = colors
    return cfg


def save_config(cfg: Dict[str, Any]) -> bool:
    try:
        env_path = find_dotenv(str(ENV_FILE))
        if not env_path:
            ENV_FILE.touch()
            env_path = str(ENV_FILE)
        for key, value in cfg.items():
            if key in ("DISCORD_ROUTES", "DISCORD_ROUTE_COLORS"):
                continue
            set_key(env_path, key, str(value))
        for kw, cid in cfg.get("DISCORD_ROUTES", {}).items():
            set_key(env_path, f"DISCORD_ROUTE_{kw}", str(cid))
        for kw, color in cfg.get("DISCORD_ROUTE_COLORS", {}).items():
            set_key(env_path, f"DISCORD_ROUTE_COLOR_{kw}", str(color))
        return True
    except Exception as exc:
        _dash_logger.error("Error saving config: %s", exc)
        return False


# ── Stats ─────────────────────────────────────────────────────────────────────

def _empty_stats(configured_sources: int = 0) -> Dict[str, Any]:
    return {
        "total_posts": 0,
        "unique_authors": 0,
        "authors": [],
        "author_counts": [],
        "posts_today": 0,
        "posts_7d": 0,
        "posts_30d": 0,
        "avg_posts_per_day": 0.0,
        "posts_by_day": [],
        "last_scan": None,
        "first_post_at": None,
        "last_post_at": None,
        "configured_sources": configured_sources,
        "recent_posts": [],
    }


def get_database_stats() -> Dict[str, Any]:
    cfg = get_config()
    sources = [s.strip() for s in cfg.get("FACEBOOK_SOURCES", "").split(",") if s.strip()]
    configured_sources = len(sources)
    db_path = get_database_path()
    if not db_path.exists():
        return _empty_stats(configured_sources)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM posts")
        total_posts = cur.fetchone()[0]

        cur.execute("SELECT author, COUNT(*) AS cnt FROM posts GROUP BY author ORDER BY cnt DESC, author ASC")
        author_rows = cur.fetchall()
        authors = [r[0] for r in author_rows]
        author_counts = [{"author": r[0], "count": r[1]} for r in author_rows]

        cur.execute("SELECT COUNT(*) FROM posts WHERE date(stored_at) = date('now')")
        posts_today = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM posts WHERE datetime(stored_at) >= datetime('now', '-7 days')")
        posts_7d = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM posts WHERE datetime(stored_at) >= datetime('now', '-30 days')")
        posts_30d = cur.fetchone()[0]

        cur.execute(
            "SELECT date(stored_at) AS day, COUNT(*) AS cnt FROM posts "
            "WHERE datetime(stored_at) >= datetime('now', '-30 days') "
            "GROUP BY date(stored_at) ORDER BY day ASC"
        )
        posts_by_day = [{"date": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("SELECT MIN(stored_at), MAX(stored_at) FROM posts")
        first_post_at, last_post_at = cur.fetchone()

        if total_posts > 0 and first_post_at and last_post_at:
            cur.execute(
                "SELECT CAST(julianday(MAX(stored_at)) - julianday(MIN(stored_at)) AS REAL) + 1 FROM posts"
            )
            day_span = cur.fetchone()[0] or 1.0
            avg_posts_per_day = round(total_posts / max(day_span, 1.0), 2)
        else:
            avg_posts_per_day = 0.0

        cur.execute("SELECT value FROM meta WHERE key = 'last_scan' LIMIT 1")
        meta_row = cur.fetchone()
        last_scan = meta_row[0] if meta_row else None

        cur.execute(
            "SELECT post_id, author, post_url, created_at, stored_at FROM posts ORDER BY id DESC LIMIT 10"
        )
        recent_posts = [
            {"post_id": r[0], "author": r[1], "post_url": r[2], "created_at": r[3], "stored_at": r[4]}
            for r in cur.fetchall()
        ]
        conn.close()

        return {
            "total_posts": total_posts,
            "unique_authors": len(authors),
            "authors": authors,
            "author_counts": author_counts,
            "posts_today": posts_today,
            "posts_7d": posts_7d,
            "posts_30d": posts_30d,
            "avg_posts_per_day": avg_posts_per_day,
            "posts_by_day": posts_by_day,
            "last_scan": last_scan,
            "first_post_at": first_post_at,
            "last_post_at": last_post_at,
            "configured_sources": configured_sources,
            "recent_posts": recent_posts,
        }
    except Exception as exc:
        _dash_logger.error("Error reading DB stats: %s", exc)
        return _empty_stats(configured_sources)


def get_logs(lines: int = 100) -> List[str]:
    if not LOG_FILE.exists():
        return ["No logs available yet."]
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return f.readlines()[-lines:]
    except Exception as exc:
        return [f"Error reading logs: {exc}"]


# ── Bot control ───────────────────────────────────────────────────────────────

def start_bot() -> Tuple[bool, str]:
    """Start bot directly (no watchdog auto-restart)."""
    if is_bot_running():
        return False, "Bot is already running"
    try:
        kwargs: dict = {"cwd": str(BASE_DIR)}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            kwargs["stdout"] = subprocess.DEVNULL
            kwargs["stderr"] = subprocess.DEVNULL
        subprocess.Popen([sys.executable, str(BASE_DIR / "bot.py")], **kwargs)
        time.sleep(2)
        if is_bot_running():
            return True, "Bot started successfully"
        return False, "Bot failed to start — check logs/bybots.log"
    except Exception as exc:
        return False, f"Error starting bot: {exc}"


def stop_bot() -> Tuple[bool, str]:
    """Stop the bot process (and pause watchdog auto-restart)."""
    # Pause watchdog so it doesn't immediately relaunch
    was_enabled = _watchdog.enabled
    _watchdog.disable()
    _watchdog._kill_bot()

    if not is_bot_running():
        _cleanup_stale_lock()
        return True, "Bot stopped (was not running)"

    try:
        pid = get_bot_pid()
        if pid:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, capture_output=True)
            else:
                os.kill(pid, 15)
            time.sleep(2)
            _cleanup_stale_lock()
            if PID_FILE.exists():
                PID_FILE.unlink(missing_ok=True)
            if not is_bot_running():
                return True, "Bot stopped successfully"
            return False, "Bot did not stop cleanly — try Force Stop"
        _cleanup_stale_lock()
        if PID_FILE.exists():
            PID_FILE.unlink(missing_ok=True)
        return True, "Lock files removed"
    except Exception as exc:
        return False, f"Error stopping bot: {exc}"


def restart_bot() -> Tuple[bool, str]:
    success, msg = stop_bot()
    if not success and "not running" not in msg.lower():
        return False, f"Failed to stop bot: {msg}"
    time.sleep(1)
    return start_bot()


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    cfg = get_config()
    stats = get_database_stats()
    return render_template(
        "index.html",
        config=cfg,
        stats=stats,
        bot_running=is_bot_running(),
        bot_pid=get_bot_pid(),
        watchdog=_watchdog.status,
    )


@app.route("/config")
def config_page():
    return render_template("config.html", config=get_config())


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(get_config())
    new_cfg = request.json or {}
    if save_config(new_cfg):
        return jsonify({"success": True, "message": "Configuration saved"})
    return jsonify({"success": False, "message": "Failed to save configuration"}), 500


@app.route("/logs")
def logs_page():
    return render_template("logs.html")


@app.route("/api/logs")
def api_logs():
    lines = request.args.get("lines", 100, type=int)
    return jsonify({"logs": get_logs(lines)})


@app.route("/stats")
def stats_page():
    return render_template("stats.html", stats=get_database_stats())


@app.route("/api/stats")
def api_stats():
    return jsonify(get_database_stats())


# ── Bot control API -----------------------------------------------------------

@app.route("/api/bot/status")
def api_bot_status():
    return jsonify({
        "running": is_bot_running(),
        "pid": get_bot_pid(),
        "lock_file_exists": LOCK_FILE.exists(),
        "pid_file_exists": PID_FILE.exists(),
        "watchdog": _watchdog.status,
    })


@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    success, message = start_bot()
    return jsonify({"success": success, "message": message})


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    success, message = stop_bot()
    return jsonify({"success": success, "message": message})


@app.route("/api/bot/restart", methods=["POST"])
def api_bot_restart():
    success, message = restart_bot()
    return jsonify({"success": success, "message": message})


# ── Watchdog control API ------------------------------------------------------

@app.route("/api/watchdog/enable", methods=["POST"])
def api_watchdog_enable():
    """Enable watchdog — bot is (re)started and monitored automatically."""
    if is_bot_running():
        _watchdog.enable()
        return jsonify({"success": True, "message": "Watchdog enabled — monitoring active bot"})
    # Start bot first via watchdog
    _watchdog.enable()
    return jsonify({"success": True, "message": "Watchdog enabled — bot will start automatically"})


@app.route("/api/watchdog/disable", methods=["POST"])
def api_watchdog_disable():
    """Disable watchdog — bot keeps running but won't auto-restart on crash."""
    _watchdog.disable()
    return jsonify({"success": True, "message": "Watchdog disabled"})


@app.route("/api/watchdog/status")
def api_watchdog_status():
    return jsonify(_watchdog.status)


# ── Entry point ───────────────────────────────────────────────────────────────

def main(host: str = DASHBOARD_HOST, port: int = DASHBOARD_PORT):
    print("=" * 60)
    print("  BY BOTS — Web Dashboard & Watchdog")
    print("=" * 60)
    print(f"\n  Open: http://{host}:{port}")
    print("\n  Features:")
    print("    • View / edit config (.env)")
    print("    • Start / Stop / Restart bot")
    print("    • Auto-restart watchdog (toggle in UI)")
    print("    • Live log viewer")
    print("    • Statistics & analytics")
    print("\n  Press Ctrl+C to stop.\n")

    BASE_DIR.joinpath("templates").mkdir(exist_ok=True)

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BY BOTS Web Dashboard")
    parser.add_argument("--host", default=DASHBOARD_HOST)
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT)
    args = parser.parse_args()
    main(args.host, args.port)
