import os
import sys
import subprocess
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import time

# ── Theme Colors ─────────────────────────────────────────────────────────────
COLOR_BG = "#12131a"
COLOR_CARD = "#1a1c26"
COLOR_TEXT = "#eceef5"
COLOR_TEXT_MUTED = "#8c92ac"
COLOR_ACCENT = "#5865F2"          # Discord Blurple
COLOR_ACCENT_HOVER = "#4752c4"
COLOR_GREEN = "#23a55a"           # Discord Green
COLOR_GREEN_HOVER = "#1e8e4c"
COLOR_RED = "#f23f43"             # Discord Red
COLOR_RED_HOVER = "#d8373b"
COLOR_CONSOLE_BG = "#0f1015"
COLOR_BORDER = "#2f313f"

class ByBotsGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BY BOTS — Community Monitor Dashboard")
        self.geometry("1100x680")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self.project_dir = os.path.dirname(os.path.abspath(__file__))
        self.lock_file = os.path.join(self.project_dir, ".bybots.lock")
        self.log_file = os.path.join(self.project_dir, "logs", "bybots.log")
        self.db_file = os.path.join(self.project_dir, "database.db")
        self.env_file = os.path.join(self.project_dir, ".env")

        self.bot_process = None
        self.log_file_pointer = None
        self.last_log_size = 0
        self.autoscroll_var = None

        self.setup_ui()
        self.load_config()
        self.update_status_loop()
        self.start_log_tailer()

    def setup_ui(self):
        # Configure Grid Weights
        self.grid_columnconfigure(0, weight=4)  # Left panel (Controls, Settings, Actions)
        self.grid_columnconfigure(1, weight=6)  # Right panel (Logs Console)
        self.grid_rowconfigure(0, weight=1)

        # ── LEFT PANEL ────────────────────────────────────────────────────────
        left_panel = tk.Frame(self, bg=COLOR_BG, padx=15, pady=15)
        left_panel.grid(row=0, column=0, sticky="nsew")
        left_panel.grid_columnconfigure(0, weight=1)

        # 1. Header Card
        header_card = tk.Frame(left_panel, bg=COLOR_CARD, bd=1, relief="flat", highlightbackground=COLOR_BORDER, highlightthickness=1)
        header_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header_card.grid_columnconfigure(0, weight=1)

        header_lbl = tk.Label(header_card, text="BY BOTS CONTROL PANEL", font=("Segoe UI", 16, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD)
        header_lbl.pack(anchor="w", padx=15, pady=(15, 2))
        
        subtitle_lbl = tk.Label(header_card, text="Facebook scraper -> Discord embeds", font=("Segoe UI", 10), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        subtitle_lbl.pack(anchor="w", padx=15, pady=(0, 15))

        # 2. Status Card
        status_card = tk.Frame(left_panel, bg=COLOR_CARD, bd=1, relief="flat", highlightbackground=COLOR_BORDER, highlightthickness=1)
        status_card.grid(row=1, column=0, sticky="ew", pady=10)

        status_title = tk.Label(status_card, text="SYSTEM STATUS", font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        status_title.pack(anchor="w", padx=15, pady=(12, 5))

        self.status_val_lbl = tk.Label(status_card, text="STOPPED", font=("Segoe UI", 20, "bold"), fg=COLOR_RED, bg=COLOR_CARD)
        self.status_val_lbl.pack(anchor="w", padx=15, pady=(0, 10))

        # Control Buttons Frame
        btn_frame = tk.Frame(status_card, bg=COLOR_CARD)
        btn_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.btn_start = tk.Button(btn_frame, text="▶ Start Bot", font=("Segoe UI", 11, "bold"), fg=COLOR_TEXT, bg=COLOR_GREEN,
                                   activebackground=COLOR_GREEN_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                   command=self.start_bot, height=2)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_stop = tk.Button(btn_frame, text="■ Stop Bot", font=("Segoe UI", 11, "bold"), fg=COLOR_TEXT, bg=COLOR_RED,
                                  activebackground=COLOR_RED_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                  command=self.stop_bot, height=2)
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(5, 0))

        # 3. Settings Card
        settings_card = tk.Frame(left_panel, bg=COLOR_CARD, bd=1, relief="flat", highlightbackground=COLOR_BORDER, highlightthickness=1)
        settings_card.grid(row=2, column=0, sticky="ew", pady=10)

        settings_title = tk.Label(settings_card, text="CONFIGURATION INFO", font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        settings_title.pack(anchor="w", padx=15, pady=(12, 10))

        self.config_vars = {
            "FB Sources": tk.StringVar(value="Loading..."),
            "Discord Channel": tk.StringVar(value="Loading..."),
            "Scan Interval": tk.StringVar(value="Loading..."),
            "Role Ping": tk.StringVar(value="None"),
        }

        row_idx = 0
        for name, var in self.config_vars.items():
            row_frame = tk.Frame(settings_card, bg=COLOR_CARD)
            row_frame.pack(fill="x", padx=15, pady=4)
            
            lbl_name = tk.Label(row_frame, text=f"{name}:", font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD, width=15, anchor="w")
            lbl_name.pack(side="left")
            
            lbl_val = tk.Label(row_frame, textvariable=var, font=("Segoe UI", 10), fg=COLOR_TEXT, bg=COLOR_CARD, anchor="w", justify="left")
            lbl_val.pack(side="left", fill="x", expand=True)
            row_idx += 1

        # Spacer to push action buttons
        tk.Label(settings_card, bg=COLOR_CARD).pack(pady=5)

        # 4. Action Center Card
        actions_card = tk.Frame(left_panel, bg=COLOR_CARD, bd=1, relief="flat", highlightbackground=COLOR_BORDER, highlightthickness=1)
        actions_card.grid(row=3, column=0, sticky="ew", pady=10)

        actions_title = tk.Label(actions_card, text="ACTION CENTER", font=("Segoe UI", 10, "bold"), fg=COLOR_TEXT_MUTED, bg=COLOR_CARD)
        actions_title.pack(anchor="w", padx=15, pady=(12, 10))

        actions_btn_frame = tk.Frame(actions_card, bg=COLOR_CARD)
        actions_btn_frame.pack(fill="x", padx=15, pady=(0, 15))
        actions_btn_frame.grid_columnconfigure(0, weight=1)
        actions_btn_frame.grid_columnconfigure(1, weight=1)

        btn_edit_env = tk.Button(actions_btn_frame, text="⚙ Edit Config (.env)", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_ACCENT,
                                 activebackground=COLOR_ACCENT_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                 command=self.edit_env, height=2)
        btn_edit_env.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 8))

        btn_clear_log = tk.Button(actions_btn_frame, text="🗑 Clear Logs", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_ACCENT,
                                  activebackground=COLOR_ACCENT_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                  command=self.clear_logs, height=2)
        btn_clear_log.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 8))

        btn_reset_db = tk.Button(actions_btn_frame, text="🔄 Reset DB (Seed)", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_ACCENT,
                                 activebackground=COLOR_ACCENT_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                 command=self.reset_db, height=2)
        btn_reset_db.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        btn_setup_pw = tk.Button(actions_btn_frame, text="🔧 Playwright Install", font=("Segoe UI", 9, "bold"), fg=COLOR_TEXT, bg=COLOR_ACCENT,
                                 activebackground=COLOR_ACCENT_HOVER, activeforeground=COLOR_TEXT, bd=0, cursor="hand2",
                                 command=self.install_playwright, height=2)
        btn_setup_pw.grid(row=1, column=1, sticky="ew", padx=(4, 0))

        # ── RIGHT PANEL (CONSOLE) ─────────────────────────────────────────────
        right_panel = tk.Frame(self, bg=COLOR_BG, padx=15, pady=15)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(1, weight=1)
        right_panel.grid_columnconfigure(0, weight=1)

        # Console Header
        console_hdr_frame = tk.Frame(right_panel, bg=COLOR_BG)
        console_hdr_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        console_title = tk.Label(console_hdr_frame, text="LIVE CONSOLE LOG", font=("Segoe UI", 12, "bold"), fg=COLOR_TEXT, bg=COLOR_BG)
        console_title.pack(side="left")

        self.autoscroll_var = tk.BooleanVar(value=True)
        autoscroll_check = tk.Checkbutton(console_hdr_frame, text="Autoscroll", variable=self.autoscroll_var, font=("Segoe UI", 9),
                                          fg=COLOR_TEXT_MUTED, bg=COLOR_BG, selectcolor=COLOR_BG, activebackground=COLOR_BG,
                                          activeforeground=COLOR_TEXT)
        autoscroll_check.pack(side="right")

        # Log Text Box
        self.log_text = scrolledtext.ScrolledText(right_panel, font=("Consolas", 10), bg=COLOR_CONSOLE_BG, fg="#a9b1d6",
                                                 insertbackground=COLOR_TEXT, bd=0, highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.log_text.grid(row=1, column=0, sticky="nsew")
        
        # Configure simple tag styling for highlights
        self.log_text.tag_config("INFO", foreground="#73daca")
        self.log_text.tag_config("WARNING", foreground="#e0af68")
        self.log_text.tag_config("ERROR", foreground="#f7768e")
        self.log_text.tag_config("CRITICAL", foreground="#ff5555", font=("Consolas", 10, "bold"))
        self.log_text.tag_config("SUCCESS", foreground="#9ece6a")

    # ── Log Processing ────────────────────────────────────────────────────────
    def append_log_line(self, line: str):
        if not line:
            return
        
        self.log_text.config(state=tk.NORMAL)
        
        # Apply visual coloring based on tag
        tag = None
        if "[INFO]" in line or "INFO" in line.upper():
            tag = "INFO"
        elif "[WARNING]" in line or "WARNING" in line.upper():
            tag = "WARNING"
        elif "[ERROR]" in line or "ERROR" in line.upper():
            tag = "ERROR"
        elif "[CRITICAL]" in line or "CRITICAL" in line.upper():
            tag = "CRITICAL"
        elif "success" in line.lower() or "posted" in line.lower() or "online" in line.lower():
            tag = "SUCCESS"

        self.log_text.insert(tk.END, line, tag)
        
        # Limit text length to prevent memory usage issues (keep last ~2000 lines)
        num_lines = int(self.log_text.index('end-1c').split('.')[0])
        if num_lines > 2000:
            self.log_text.delete("1.0", f"{num_lines - 2000}.0")

        if self.autoscroll_var.get():
            self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def start_log_tailer(self):
        # Start log file checker thread
        t = threading.Thread(target=self.tail_log_file_loop, daemon=True)
        t.start()

    def tail_log_file_loop(self):
        # Read existing log contents
        if os.path.exists(self.log_file):
            try:
                self.last_log_size = os.path.getsize(self.log_file)
                with open(self.log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # Show last 100 lines initially
                    for line in lines[-100:]:
                        self.after(0, self.append_log_line, line)
            except Exception as e:
                self.after(0, self.append_log_line, f"Error reading log file on start: {e}\n")

        while True:
            try:
                if os.path.exists(self.log_file):
                    current_size = os.path.getsize(self.log_file)
                    if current_size < self.last_log_size:
                        # Log was cleared / truncated
                        self.log_text.config(state=tk.NORMAL)
                        self.log_text.delete("1.0", tk.END)
                        self.log_text.config(state=tk.DISABLED)
                        self.last_log_size = 0
                    
                    if current_size > self.last_log_size:
                        with open(self.log_file, "r", encoding="utf-8") as f:
                            f.seek(self.last_log_size)
                            new_data = f.read()
                            if new_data:
                                for line in new_data.splitlines(keepends=True):
                                    self.after(0, self.append_log_line, line)
                        self.last_log_size = current_size
            except Exception as e:
                pass
            time.sleep(0.5)

    # ── Config Loader ─────────────────────────────────────────────────────────
    def load_config(self):
        if not os.path.exists(self.env_file):
            self.config_vars["FB Sources"].set("Missing .env")
            self.config_vars["Discord Channel"].set("Missing .env")
            self.config_vars["Scan Interval"].set("Missing .env")
            return

        try:
            settings = {}
            with open(self.env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        settings[k.strip()] = v.strip()

            fb_sources_raw = settings.get("FACEBOOK_SOURCES", "")
            if fb_sources_raw:
                fb_urls = [u.strip() for u in fb_sources_raw.split(",") if u.strip()]
            else:
                legacy_fb = settings.get("FACEBOOK_GROUP_URL", "")
                fb_urls = [legacy_fb] if legacy_fb else []

            if not fb_urls:
                display_fb = "Not set"
            else:
                first_url = fb_urls[0]
                if "facebook.com/groups/" in first_url:
                    try:
                        display_first = "groups/" + first_url.split("facebook.com/groups/")[-1].split("/")[0]
                    except Exception:
                        display_first = first_url
                else:
                    try:
                        display_first = first_url.split("facebook.com/")[-1].split("/")[0]
                    except Exception:
                        display_first = first_url

                if len(fb_urls) > 1:
                    display_fb = f"{display_first} (+ {len(fb_urls) - 1} more)"
                else:
                    display_fb = display_first

            self.config_vars["FB Sources"].set(display_fb)
            routes_count = sum(1 for k, v in settings.items() if k.startswith("DISCORD_ROUTE_") and v.strip())
            default_channel = settings.get("DISCORD_CHANNEL_ID", "Not set")
            if routes_count > 0:
                self.config_vars["Discord Channel"].set(f"{default_channel} (+ {routes_count} routes)")
            else:
                self.config_vars["Discord Channel"].set(default_channel)
            self.config_vars["Scan Interval"].set(f"{settings.get('CHECK_INTERVAL', '300')} seconds")
            
            ping_role = settings.get("DISCORD_PING_ROLE_ID", "")
            self.config_vars["Role Ping"].set(ping_role if ping_role else "Disabled")
        except Exception as e:
            self.config_vars["FB Sources"].set("Error loading config")

    # ── Process Checker ───────────────────────────────────────────────────────
    def check_if_running_by_lock(self):
        """Check if lock file exists and if the registered PID is currently active."""
        if not os.path.exists(self.lock_file):
            return False, None

        try:
            with open(self.lock_file, "r", encoding="utf-8") as f:
                pid_str = f.read().strip()
                if not pid_str.isdigit():
                    # Invalid lock file content, can clear it
                    return False, None
                pid = int(pid_str)
        except Exception:
            return False, None

        # Check if pid is active
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(f'tasklist /fi "PID eq {pid}"', shell=True).decode("utf-8", errors="ignore")
                if str(pid) in out and "python" in out.lower():
                    return True, pid
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 0)
                return True, pid
            except OSError:
                pass

        return False, None

    def update_status_loop(self):
        is_running, pid = self.check_if_running_by_lock()
        
        # Check if our subprocess is running
        sub_running = False
        if self.bot_process is not None:
            if self.bot_process.poll() is None:
                sub_running = True
            else:
                self.bot_process = None

        if is_running or sub_running:
            self.status_val_lbl.config(text=f"RUNNING (PID: {pid or (self.bot_process.pid if self.bot_process else '?')})", fg=COLOR_GREEN)
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
        else:
            self.status_val_lbl.config(text="STOPPED", fg=COLOR_RED)
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)

        self.after(1000, self.update_status_loop)

    # ── Button Commands ───────────────────────────────────────────────────────
    def start_bot(self):
        self.load_config() # Reload config variables first

        is_running, pid = self.check_if_running_by_lock()
        if is_running:
            messagebox.showwarning("Already Running", f"Another BY BOTS instance is already running at PID {pid}.\nPlease stop it first.")
            return

        # Clean stale lock file if it exists without active PID
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except Exception:
                pass

        # Check environment configuration variables are set
        try:
            with open(self.env_file, "r") as f:
                env_content = f.read()
                if "YOUR_DISCORD_TOKEN" in env_content or "YOUR_FACEBOOK_GROUP_URL" in env_content:
                    messagebox.showerror("Configuration Error", "Please update the placeholders in your .env file with actual credentials first.")
                    return
        except Exception:
            pass

        self.append_log_line("\n--- Starting Bot Launch Sequence ---\n")
        
        try:
            # Launch bot.py as background process
            self.bot_process = subprocess.Popen(
                [sys.executable, "bot.py"],
                cwd=self.project_dir,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            self.append_log_line(f"Process spawned successfully (PID: {self.bot_process.pid})\n")
        except Exception as e:
            messagebox.showerror("Execution Error", f"Failed to start bot.py:\n{e}")
            self.append_log_line(f"Error launching bot: {e}\n")

    def stop_bot(self):
        self.append_log_line("\n--- Stopping Bot Process ---\n")
        
        # Terminate subprocess if managed here
        if self.bot_process is not None:
            try:
                self.bot_process.terminate()
                self.bot_process.wait(timeout=3)
                self.append_log_line("Managed subprocess terminated cleanly.\n")
            except Exception as e:
                try:
                    self.bot_process.kill()
                    self.append_log_line("Managed subprocess killed.\n")
                except Exception:
                    pass

        # Also terminate using PID from lock file if present
        is_running, pid = self.check_if_running_by_lock()
        if is_running:
            try:
                if sys.platform == "win32":
                    subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
                else:
                    os.kill(pid, 9)
                self.append_log_line(f"Killed process PID {pid}.\n")
            except Exception as e:
                self.append_log_line(f"Could not kill process {pid}: {e}\n")

        # Remove lock file
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except Exception:
                pass
        
        self.append_log_line("Bot stopped successfully.\n")

    def edit_env(self):
        if not os.path.exists(self.env_file):
            # Create .env from template if missing
            example = os.path.join(self.project_dir, ".env.example")
            if os.path.exists(example):
                try:
                    import shutil
                    shutil.copy(example, self.env_file)
                except Exception:
                    pass

        try:
            if sys.platform == "win32":
                os.startfile(self.env_file)
            else:
                subprocess.run(["xdg-open", self.env_file])
            self.append_log_line("Opened .env for editing.\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open .env file:\n{e}")

    def clear_logs(self):
        if messagebox.askyesno("Clear Logs", "Are you sure you want to delete all current log files?"):
            try:
                if os.path.exists(self.log_file):
                    # Open file with 'w' write mode to truncate
                    with open(self.log_file, "w", encoding="utf-8") as f:
                        f.write("")
                self.log_text.config(state=tk.NORMAL)
                self.log_text.delete("1.0", tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.last_log_size = 0
                self.append_log_line("Logs cleared successfully.\n")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear logs:\n{e}")

    def reset_db(self):
        # Show warning
        warning_msg = (
            "Resetting the database will delete the history of stored posts.\n\n"
            "This causes the bot to enter seed mode on the next start, "
            "where it will re-record all current posts on the Facebook group page "
            "without posting them to Discord. This prevents duplicates from spamming.\n\n"
            "Do you want to proceed?"
        )
        if messagebox.askyesno("Reset Database", warning_msg):
            # Stop bot first
            self.stop_bot()
            
            try:
                if os.path.exists(self.db_file):
                    os.remove(self.db_file)
                    self.append_log_line("Database file deleted successfully.\n")
                else:
                    self.append_log_line("Database file not found (already clean).\n")
                messagebox.showinfo("Success", "Database reset complete. Next start will trigger fresh seed scan.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete database:\n{e}")

    def install_playwright(self):
        self.append_log_line("\n--- Installing Playwright Chromium Browser ---\n")
        
        def run_install():
            try:
                # Run playwright install chromium
                cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
                self.append_log_line(f"Running: {' '.join(cmd)}\n")
                
                # Use CREATE_NO_WINDOW on Windows to prevent popping a cmd shell
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                
                for line in proc.stdout:
                    self.after(0, self.append_log_line, line)
                
                proc.wait()
                if proc.returncode == 0:
                    self.after(0, self.append_log_line, "Playwright chromium installed successfully!\n")
                    self.after(0, lambda: messagebox.showinfo("Playwright", "Playwright chromium browser installation completed successfully!"))
                else:
                    self.after(0, self.append_log_line, f"Playwright install failed with exit code: {proc.returncode}\n")
                    self.after(0, lambda: messagebox.showerror("Playwright Error", f"Playwright install failed (Code: {proc.returncode})"))
            except Exception as e:
                self.after(0, self.append_log_line, f"Error running Playwright installer: {e}\n")
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to launch playwright installer:\n{e}"))

        t = threading.Thread(target=run_install, daemon=True)
        t.start()

if __name__ == "__main__":
    app = ByBotsGUI()
    app.mainloop()
