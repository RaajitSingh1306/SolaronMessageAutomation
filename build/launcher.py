"""
launcher.py - Desktop launcher and controller for Solaron Messaging Dashboard.
Starts the background server, launches the default browser, and provides
a simple control panel for non-technical users.
"""

import os
import sys
import threading
import time
import urllib.request
import webbrowser
import logging
import tkinter as tk
from tkinter import messagebox

# Determine application directories
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    APP_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    # Running from source: root is parent of build/
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BUNDLE_DIR = APP_DIR
    _build_dir = os.path.dirname(os.path.abspath(__file__))
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    if _build_dir not in sys.path:
        sys.path.insert(0, _build_dir)

# ---------------------------------------------------------------------------
# Fix for PyInstaller --windowed mode: sys.stdout/stderr are None, which
# causes uvicorn's DefaultFormatter to crash on sys.stderr.isatty().
# Redirect both to a log file so all output is captured for debugging.
# ---------------------------------------------------------------------------
_log_file_path = os.path.join(APP_DIR, "solaron_server.log")
if sys.stdout is None or sys.stderr is None:
    _log_file = open(_log_file_path, "a", encoding="utf-8", errors="replace")
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file

# Configure Playwright browser path if bundled
possible_browser_dirs = [
    os.path.join(APP_DIR, "playwright-browsers"),
    os.path.join(BUNDLE_DIR, "playwright-browsers"),
    os.path.join(APP_DIR, "_internal", "playwright-browsers"),
]
for b_dir in possible_browser_dirs:
    if os.path.exists(b_dir):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = b_dir
        break

from config import Config
from settings_ui import load_env_phone_number, show_settings_window


class SolaronAppLauncher:
    """Desktop manager GUI for Solaron Messaging Dashboard."""

    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 5000
        self.url = f"http://{self.host}:{self.port}"
        self.server_thread = None
        self.server = None
        self.is_running = True

        # First run check: prompt settings if phone number is not set
        current_phone = load_env_phone_number()
        if not current_phone or "--settings" in sys.argv:
            show_settings_window()

        # Start FastAPI / Uvicorn in background thread
        self._start_server_thread()

        # Initialize Control Panel GUI
        self.root = tk.Tk()
        self.root.title("Solaron Messaging Dashboard")
        self.root.geometry("460x320")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        # Center on screen
        self.root.update_idletasks()
        width = 460
        height = 320
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self._build_ui()

        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Launch browser once server is responsive
        threading.Thread(target=self._wait_and_open_browser, daemon=True).start()

    def _start_server_thread(self):
        """Start uvicorn server in a separate daemon thread."""
        import uvicorn
        from app import app

        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            log_config=None,  # Bypass uvicorn's DefaultFormatter (crashes in windowed mode)
        )
        self.server = uvicorn.Server(config)

        def run():
            try:
                self.server.run()
            except Exception as e:
                print(f"Server error: {e}")

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

    def _wait_and_open_browser(self):
        """Wait for server to become responsive, then open browser."""
        for _ in range(30):
            try:
                req = urllib.request.Request(self.url, headers={"User-Agent": "SolaronLauncher"})
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.3)

        time.sleep(0.5)
        webbrowser.open(self.url)

    def _build_ui(self):
        # Header banner
        header = tk.Frame(self.root, bg="#1e293b", padx=20, pady=15)
        header.pack(fill="x")

        title = tk.Label(
            header,
            text="☀️ Solaron Messaging Dashboard",
            font=("Segoe UI", 15, "bold"),
            fg="#f8fafc",
            bg="#1e293b",
        )
        title.pack(anchor="w")

        # Status badge
        status_frame = tk.Frame(header, bg="#1e293b")
        status_frame.pack(anchor="w", pady=(4, 0))

        dot = tk.Label(status_frame, text="●", font=("Segoe UI", 11), fg="#22c55e", bg="#1e293b")
        dot.pack(side="left")

        status_lbl = tk.Label(
            status_frame,
            text=f" Server is running at {self.url}",
            font=("Segoe UI", 9),
            fg="#cbd5e1",
            bg="#1e293b",
        )
        status_lbl.pack(side="left")

        # Body buttons
        body = tk.Frame(self.root, bg="#0f172a", padx=25, pady=20)
        body.pack(fill="both", expand=True)

        # Open in Browser button
        open_btn = tk.Button(
            body,
            text="🌐 Open Dashboard in Browser",
            font=("Segoe UI", 10, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=8,
            command=lambda: webbrowser.open(self.url),
        )
        open_btn.pack(fill="x", pady=(0, 10))

        # Change Phone Number button
        settings_btn = tk.Button(
            body,
            text="⚙️ Change WhatsApp Phone Number",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._open_settings,
        )
        settings_btn.pack(fill="x", pady=(0, 10))

        # Open Data Folder button
        folder_btn = tk.Button(
            body,
            text="📁 Open Data & Reports Folder",
            font=("Segoe UI", 9),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._open_data_folder,
        )
        folder_btn.pack(fill="x", pady=(0, 10))

        # Stop & Exit button
        exit_btn = tk.Button(
            body,
            text="🛑 Stop Server & Exit",
            font=("Segoe UI", 9, "bold"),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=6,
            command=self._on_close,
        )
        exit_btn.pack(fill="x")

    def _open_settings(self):
        """Open settings dialog to update phone number."""
        show_settings_window(parent=self.root)

    def _open_data_folder(self):
        """Open the data directory in Windows File Explorer."""
        data_dir = Config.DATA_FOLDER
        if os.path.exists(data_dir):
            os.startfile(data_dir)
        else:
            os.makedirs(data_dir, exist_ok=True)
            os.startfile(data_dir)

    def _on_close(self):
        """Gracefully shut down the server and exit GUI."""
        if messagebox.askokcancel("Quit", "Are you sure you want to stop Solaron Dashboard and exit?", parent=self.root):
            self.is_running = False
            if self.server:
                self.server.should_exit = True
            self.root.destroy()
            sys.exit(0)

    def run(self):
        """Start the tkinter main loop."""
        self.root.mainloop()


if __name__ == "__main__":
    launcher = SolaronAppLauncher()
    launcher.run()
