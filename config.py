"""
config.py - Centralised configuration loader for BY BOTS.

Reads all settings from environment variables (populated via .env).
Raises clear errors on startup if required values are missing.
"""

import os
import logging
from urllib.parse import urlparse

from dotenv import load_dotenv

# Project root (directory containing this file)
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# Load .env file into the environment before anything else reads it
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

logger = logging.getLogger(__name__)


def _require(key: str) -> str:
    """Return the value of an env var, raising if it is absent or empty."""
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            "Please check your .env file."
        )
    return value


def _resolve_path(path: str) -> str:
    """Resolve a path relative to BASE_DIR unless already absolute."""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key, "true" if default else "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


# ── Discord ───────────────────────────────────────────────────────────────────
DISCORD_TOKEN: str = _require("DISCORD_TOKEN")
DISCORD_CHANNEL_ID: int = int(_require("DISCORD_CHANNEL_ID"))

# Dynamic keyword routing configuration (Option B)
# Scan environment variables for DISCORD_ROUTE_<keyword> = channel_id
DISCORD_ROUTES: dict[str, int] = {}
DISCORD_ROUTE_COLORS: dict[str, int] = {}  # Custom colors per route

for _key, _val in os.environ.items():
    if _key.startswith("DISCORD_ROUTE_"):
        # Skip color configurations
        if _key.startswith("DISCORD_ROUTE_COLOR_"):
            continue
            
        # Map underscores in key suffix to spaces to support multi-word keywords
        _keyword = _key[len("DISCORD_ROUTE_"):].lower().replace("_", " ")
        _val_clean = _val.strip()
        if _val_clean:
            try:
                DISCORD_ROUTES[_keyword] = int(_val_clean)
            except ValueError:
                logger.warning(
                    "Invalid channel ID for keyword route '%s': '%s'", _key, _val
                )
    elif _key.startswith("DISCORD_ROUTE_COLOR_"):
        # Extract keyword and color
        _keyword = _key[len("DISCORD_ROUTE_COLOR_"):].lower().replace("_", " ")
        _val_clean = _val.strip()
        if _val_clean:
            try:
                # Support both hex (#FF0000) and integer (16711680) formats
                if _val_clean.startswith("#"):
                    DISCORD_ROUTE_COLORS[_keyword] = int(_val_clean[1:], 16)
                elif _val_clean.startswith("0x"):
                    DISCORD_ROUTE_COLORS[_keyword] = int(_val_clean, 16)
                else:
                    DISCORD_ROUTE_COLORS[_keyword] = int(_val_clean)
            except ValueError:
                logger.warning(
                    "Invalid color for route '%s': '%s'", _key, _val
                )

# Optional: set this to your server (guild) ID for instant slash command syncing
# in dev. Leave blank to sync globally (takes up to 1 hour on first deploy).
_guild_id_raw = os.getenv("DISCORD_GUILD_ID", "").strip()
DISCORD_GUILD_ID: int | None = int(_guild_id_raw) if _guild_id_raw else None

# Optional: role ID to ping when a new post is forwarded (leave blank to disable)
_role_id_raw = os.getenv("DISCORD_PING_ROLE_ID", "").strip()
DISCORD_PING_ROLE_ID: int | None = int(_role_id_raw) if _role_id_raw else None

# Optional: dedicated channel for streamer live stream announcements
_streamer_channel_raw = os.getenv("DISCORD_STREAMER_CHANNEL_ID", "").strip()
DISCORD_STREAMER_CHANNEL_ID: int | None = int(_streamer_channel_raw) if _streamer_channel_raw else None

# Optional: security reminder channel and interval (in seconds)
_security_channel_raw = os.getenv("DISCORD_SECURITY_CHANNEL_ID", "").strip()
DISCORD_SECURITY_CHANNEL_ID: int | None = int(_security_channel_raw) if _security_channel_raw else None
SECURITY_REMINDER_INTERVAL: int = int(os.getenv("SECURITY_REMINDER_INTERVAL", "300"))  # Default: 5 minutes
SECURITY_REMINDER_ENABLED: bool = _env_bool("SECURITY_REMINDER_ENABLED", default=False)
SECURITY_REMINDER_PING_EVERYONE: bool = _env_bool("SECURITY_REMINDER_PING_EVERYONE", default=False)

if DISCORD_GUILD_ID and DISCORD_CHANNEL_ID == DISCORD_GUILD_ID:
    logger.warning(
        "DISCORD_CHANNEL_ID (%s) matches DISCORD_GUILD_ID — "
        "you likely set the server ID instead of a text channel ID.",
        DISCORD_CHANNEL_ID,
    )

# ── Post Filtering ────────────────────────────────────────────────────────────
# Optional: comma-separated list of Facebook author names to whitelist
# If set, only posts from these authors will be forwarded to Discord
# Leave blank to forward all posts (default behavior)
_allowed_authors_raw = os.getenv("ALLOWED_AUTHORS", "").strip()
if _allowed_authors_raw:
    ALLOWED_AUTHORS: list[str] = [
        name.strip() for name in _allowed_authors_raw.split(",") if name.strip()
    ]
else:
    ALLOWED_AUTHORS = []

# Enable/disable author filtering
FILTER_BY_AUTHOR: bool = _env_bool("FILTER_BY_AUTHOR", default=False)

# ── Facebook ──────────────────────────────────────────────────────────────────
def facebook_source_display_path(url: str) -> str:
    """Human-readable Facebook source path for embeds (e.g. groups/byranofficial or RanOnlineBY)."""
    try:
        path = urlparse(url).path.strip("/")
        return path or url
    except Exception:
        return url


_sources_raw = os.getenv("FACEBOOK_SOURCES", "").strip()
if _sources_raw:
    FACEBOOK_SOURCES: list[str] = [u.strip() for u in _sources_raw.split(",") if u.strip()]
else:
    _legacy_url = os.getenv("FACEBOOK_GROUP_URL", "").strip()
    if _legacy_url:
        FACEBOOK_SOURCES = [_legacy_url]
    else:
        _require("FACEBOOK_GROUP_URL")
        FACEBOOK_SOURCES = []

# Keep FACEBOOK_GROUP_URL pointing to the first source for backward compatibility
FACEBOOK_GROUP_URL: str = FACEBOOK_SOURCES[0] if FACEBOOK_SOURCES else ""


def facebook_group_display_path() -> str:
    """Legacy helper for backward compatibility."""
    return facebook_source_display_path(FACEBOOK_GROUP_URL)


# ── Scheduler ─────────────────────────────────────────────────────────────────
# How often (in seconds) to poll Facebook for new posts. Default: 300 s (5 min)
CHECK_INTERVAL: int = int(os.getenv("CHECK_INTERVAL", "300"))
if CHECK_INTERVAL <= 0:
    raise EnvironmentError(
        f"CHECK_INTERVAL must be a positive integer (got {CHECK_INTERVAL}). "
        "Please check your .env file."
    )

# On first run with an empty DB, record visible posts without posting to Discord
SEED_ON_FIRST_RUN: bool = _env_bool("SEED_ON_FIRST_RUN", default=True)

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_PATH: str = _resolve_path(os.getenv("DATABASE_PATH", "database.db"))

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_DIR: str = os.path.join(BASE_DIR, "logs")
LOG_FILE: str = os.path.join(LOG_DIR, "bybots.log")
LOG_MAX_BYTES: int = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "3"))

# ── Process lock ────────────────────────────────────────────────────────────────
LOCK_FILE: str = os.path.join(BASE_DIR, ".bybots.lock")

# ── Facebook scraper (proxy, cookies, user-agent) ───────────────────────────
SCRAPER_PROXY: str = os.getenv("SCRAPER_PROXY", "").strip()
SCRAPER_PROXY_USERNAME: str = os.getenv("SCRAPER_PROXY_USERNAME", "").strip()
SCRAPER_PROXY_PASSWORD: str = os.getenv("SCRAPER_PROXY_PASSWORD", "").strip()

FACEBOOK_COOKIES_ENABLED: bool = _env_bool("FACEBOOK_COOKIES_ENABLED", default=True)
FACEBOOK_COOKIES_PATH: str = _resolve_path(
    os.getenv("FACEBOOK_COOKIES_PATH", "cookies/facebook_cookies.json")
)

SCRAPER_ROTATE_USER_AGENT: bool = _env_bool("SCRAPER_ROTATE_USER_AGENT", default=True)
_custom_ua_raw = os.getenv("SCRAPER_USER_AGENTS", "").strip()
# Pipe-separated list (commas appear inside user-agent strings)
SCRAPER_USER_AGENTS: list[str] = [
    ua.strip() for ua in _custom_ua_raw.split("|") if ua.strip()
]

# ── Webhooks ──────────────────────────────────────────────────────────────────
_webhook_urls_raw = os.getenv("WEBHOOK_URLS", "").strip()
WEBHOOK_URLS: list[str] = [
    url.strip() for url in _webhook_urls_raw.split(",") if url.strip()
]
WEBHOOK_ENABLED: bool = _env_bool("WEBHOOK_ENABLED", default=bool(WEBHOOK_URLS))
WEBHOOK_ONLY: bool = _env_bool("WEBHOOK_ONLY", default=False)
WEBHOOK_TIMEOUT: int = int(os.getenv("WEBHOOK_TIMEOUT", "30"))

if WEBHOOK_ONLY and not WEBHOOK_URLS:
    logger.warning(
        "WEBHOOK_ONLY is enabled but WEBHOOK_URLS is empty — "
        "new posts will be saved to the database but not forwarded anywhere."
    )

# ── Bot identity ──────────────────────────────────────────────────────────────
BOT_NAME: str = "BY BOTS"
BOT_FOOTER: str = "BY BOTS • Facebook Community Monitor"
BOT_COLOUR: int = 0x1877F2  # Facebook blue
