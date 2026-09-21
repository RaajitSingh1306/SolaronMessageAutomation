"""
settings_ui.py - Simple, user-friendly settings dialog for Solaron Dashboard.
Allows non-technical users to set or update their WhatsApp Web sender number.
"""

import os
import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional


def get_base_dir() -> str:
    """Get the base directory where .env and user data reside."""
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # workspace root is one level above build/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_env_file_path() -> str:
    """Return the absolute path to .env file."""
    return os.path.join(get_base_dir(), ".env")


def load_env_phone_number() -> str:
    """Read the current TEST_PHONE_NUMBER from .env if available."""
    env_path = get_env_file_path()
    if not os.path.exists(env_path):
        return ""
    try:
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TEST_PHONE_NUMBER="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    return val
    except Exception:
        pass
    return ""


def save_phone_number_to_env(phone_number: str) -> bool:
    """
    Save or update TEST_PHONE_NUMBER in the .env file.
    Preserves all other configuration entries and baked-in credentials.
    """
    env_path = get_env_file_path()
    phone_clean = phone_number.strip()

    # Default template if .env does not exist
    default_template = f"""# Solaron Messaging Dashboard Configuration
ISOLARCLOUD_USER=
ISOLARCLOUD_PASSWORD=
ISOLARCLOUD_URL=https://web3.isolarcloud.in/

SURYALOG_USER=
SURYALOG_PASSWORD=
SURYALOG_URL=https://cloud.suryalog.ae/

GROWATT_USER=
GROWATT_PASSWORD=
GROWATT_SERVER_URL=https://server-api.growatt.com/

# WhatsApp sender number (configured by user)
TEST_PHONE_NUMBER={phone_clean}

SUPPORT_PHONE=
PRICE_PER_UNIT=14.0

MSG_ACTIVE="Greetings From Solaron Homes Pvt Ltd,\\n\\nDear Sir/Madam,\\nYour solar plant generated {{energy}} units in the previous month {{month_name}} {{year}}\\nYou have saved approximately ₹{{savings}}\\nKindly ensure regular cleaning of your plant maximizes your savings.\\nIf you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\\n\\nThank You,\\nTeam Solaron"

MSG_OFFLINE="Greetings From Solaron Homes Pvt Ltd,\\n\\nDear Sir/Madam,\\nyour solar plant is offline. please check once physically...\\n\\nIf any queries, please connect with our team at {{support_phone}}\\n\\nTeam solaron,\\n\\nसोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं\\n\\nप्रिय महोदय/मैम,\\nआपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें...\\n\\nयदि कोई प्रश्न हैं, तो कृपया हमारी टीम को कॉल कीजिए {{support_phone}}\\n\\nटीम सोलरॉन"

MSG_MONSOON="Greetings From Solaron Homes Pvt Ltd,\\nDear Sir/Madam,\\nThe monsoon season is going on and this will result in wind speed going up. We strongly recommend that you’ll carry out the pre monsoon check up for your solar plants. As part of the pre monsoon check up we shall check the overall plant working and also tighten any loose nuts and bolts. Please contact us at {{support_phone}} for a single visit or for the annual service contracts.\\nThank You\\nTeam Solaron"
"""

    try:
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(default_template)
            return True

        # If .env exists, update TEST_PHONE_NUMBER line or append it
        lines = []
        found = False
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip().startswith("TEST_PHONE_NUMBER="):
                    lines.append(f"TEST_PHONE_NUMBER={phone_clean}\n")
                    found = True
                else:
                    lines.append(line)

        if not found:
            lines.append(f"\nTEST_PHONE_NUMBER={phone_clean}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return True
    except Exception as e:
        print(f"Error saving .env file: {e}")
        return False


def validate_phone(phone: str) -> tuple[bool, str]:
    """Validate phone number string."""
    clean = phone.strip().replace(" ", "").replace("-", "")
    digits = re.sub(r"\D", "", clean)
    if not digits:
        return False, "Phone number cannot be empty."
    if len(digits) < 10 or len(digits) > 13:
        return False, f"Phone number should have 10 digits (got {len(digits)} digits)."
    return True, clean


class SolaronSettingsWindow:
    """Tkinter window for setting the WhatsApp sender phone number."""

    def __init__(self, on_save_callback: Optional[Callable[[str], None]] = None, parent: Optional[tk.Tk] = None):
        self.on_save = on_save_callback
        self.saved = False
        self.saved_phone = ""
        self._has_parent = parent is not None

        if parent:
            self.root = tk.Toplevel(parent)
            self.root.transient(parent)  # Stay on top of parent
            self.root.grab_set()         # Make modal
        else:
            self.root = tk.Tk()

        self.root.title("Solaron Messaging Dashboard - Setup")
        self.root.geometry("480x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f172a")

        # Center on screen
        self.root.update_idletasks()
        width = 480
        height = 420
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        self._build_ui()

    def _build_ui(self):
        # Header banner
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=20, pady=18)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(
            header_frame,
            text="☀️ Solaron Dashboard Setup",
            font=("Segoe UI", 16, "bold"),
            fg="#f8fafc",
            bg="#1e293b",
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = tk.Label(
            header_frame,
            text="Solaron Homes Pvt Ltd — Automated Messaging",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#1e293b",
        )
        subtitle_lbl.pack(anchor="w", pady=(2, 0))

        # Main content area
        content_frame = tk.Frame(self.root, bg="#0f172a", padx=25, pady=20)
        content_frame.pack(fill="both", expand=True)

        info_lbl = tk.Label(
            content_frame,
            text="Enter your WhatsApp number to use for test sending and message verification:",
            font=("Segoe UI", 10),
            fg="#e2e8f0",
            bg="#0f172a",
            wraplength=430,
            justify="left",
        )
        info_lbl.pack(anchor="w", pady=(0, 15))

        # Phone Number Label
        phone_lbl = tk.Label(
            content_frame,
            text="WhatsApp Sender / Test Number:",
            font=("Segoe UI", 10, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
        )
        phone_lbl.pack(anchor="w", pady=(0, 5))

        # Phone Entry
        entry_frame = tk.Frame(content_frame, bg="#1e293b", padx=2, pady=2)
        entry_frame.pack(fill="x", pady=(0, 8))

        self.phone_var = tk.StringVar()
        current_phone = load_env_phone_number()
        if current_phone:
            self.phone_var.set(current_phone)
        else:
            self.phone_var.set("")

        self.phone_entry = tk.Entry(
            entry_frame,
            textvariable=self.phone_var,
            font=("Consolas", 13),
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="#38bdf8",
            relief="flat",
            bd=8,
        )
        self.phone_entry.pack(fill="x")
        self.phone_entry.focus_set()
        self.phone_entry.select_range(0, tk.END)

        help_lbl = tk.Label(
            content_frame,
            text="Example: 9580404775 or +919580404775",
            font=("Segoe UI", 8),
            fg="#64748b",
            bg="#0f172a",
        )
        help_lbl.pack(anchor="w", pady=(0, 20))

        # Chrome requirement notice box
        notice_frame = tk.Frame(content_frame, bg="#1e293b", padx=12, pady=10, relief="groove", bd=1)
        notice_frame.pack(fill="x", pady=(0, 20))

        notice_title = tk.Label(
            notice_frame,
            text="ℹ️ WhatsApp Web Requirement:",
            font=("Segoe UI", 9, "bold"),
            fg="#fbbf24",
            bg="#1e293b",
        )
        notice_title.pack(anchor="w")

        notice_text = tk.Label(
            notice_frame,
            text="Before sending messages from the dashboard, open Google Chrome and make sure you are logged into WhatsApp Web (web.whatsapp.com).",
            font=("Segoe UI", 8),
            fg="#cbd5e1",
            bg="#1e293b",
            wraplength=400,
            justify="left",
        )
        notice_text.pack(anchor="w", pady=(2, 0))

        # Save & Launch Button
        btn_frame = tk.Frame(content_frame, bg="#0f172a")
        btn_frame.pack(fill="x", pady=(5, 0))

        save_btn = tk.Button(
            btn_frame,
            text="🚀 Save & Launch Dashboard",
            font=("Segoe UI", 11, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=15,
            pady=8,
            command=self._on_save_clicked,
        )
        save_btn.pack(fill="x")

        # Allow pressing Enter to submit
        self.root.bind("<Return>", lambda e: self._on_save_clicked())

    def _on_save_clicked(self):
        val = self.phone_var.get()
        valid, msg = validate_phone(val)
        if not valid:
            messagebox.showerror("Invalid Phone Number", msg, parent=self.root)
            return

        success = save_phone_number_to_env(val)
        if not success:
            messagebox.showerror("Error", "Could not save configuration file.", parent=self.root)
            return

        self.saved = True
        self.saved_phone = val

        if self.on_save:
            self.on_save(val)

        self.root.destroy()

    def run(self) -> bool:
        """Run the main loop and return True if saved."""
        if self._has_parent:
            # When opened from the launcher, wait for the dialog to close
            self.root.wait_window()
        else:
            # Standalone mode (first launch)
            self.root.mainloop()
        return self.saved


def show_settings_window(on_save_callback: Optional[Callable[[str], None]] = None, parent: Optional[tk.Tk] = None) -> bool:
    """Show the settings window. Pass parent to open as a child dialog."""
    app = SolaronSettingsWindow(on_save_callback=on_save_callback, parent=parent)
    return app.run()


if __name__ == "__main__":
    show_settings_window()
