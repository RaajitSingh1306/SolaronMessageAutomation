"""
services/whatsapp.py

Sends WhatsApp messages via pywhatkit (WhatsApp Web automation).
Requires Chrome to be open and logged into WhatsApp Web before sending.

Timing: ~20-25s per message. 425 plants ≈ 2.5 hours total.
Future upgrade path: WhatsApp Business Cloud API (Meta) — paid per conversation.
See FUTURE_EXPANSION.md for pricing details and migration plan.
"""

import logging
import os
import random
import time
from typing import Any, Callable, Optional
from urllib.parse import quote

from config import Config

logger = logging.getLogger(__name__)


try:
    import requests
    _orig_requests_get = requests.get
    try:
        requests.get = lambda *a, **k: type("DummyResponse", (), {"status_code": 200})()
        import pywhatkit
        _PYWHATKIT_AVAILABLE = True
    finally:
        requests.get = _orig_requests_get
except Exception as exc:
    _PYWHATKIT_AVAILABLE = False
    logger.warning("pywhatkit unavailable: %s", exc)

import shutil
import sys
import webbrowser

def _find_system_browser_path() -> Optional[str]:
    """
    Dynamically locate Chrome or Edge on any Windows machine
    without relying on hardcoded paths.
    """
    candidates = []

    # 1. Check Windows Registry App Paths (covers custom drive installs like D:, E:, user installs)
    if sys.platform == "win32":
        try:
            import winreg
            for subkey in [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
            ]:
                for root in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    try:
                        val = winreg.QueryValue(root, subkey)
                        if val and os.path.exists(val):
                            candidates.append(val)
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. Check system PATH
    for name in ["chrome", "google-chrome", "msedge", "chromium"]:
        p = shutil.which(name)
        if p and os.path.exists(p):
            candidates.append(p)

    # 3. Check standard environment program directories
    prog_dirs = [
        os.environ.get("PROGRAMFILES", ""),
        os.environ.get("PROGRAMFILES(X86)", ""),
        os.environ.get("PROGRAMW6432", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for pdir in prog_dirs:
        if pdir:
            candidates.append(os.path.join(pdir, "Google", "Chrome", "Application", "chrome.exe"))
            candidates.append(os.path.join(pdir, "Microsoft", "Edge", "Application", "msedge.exe"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None

def _register_chrome():
    browser_path = _find_system_browser_path()
    if browser_path:
        try:
            browser = webbrowser.BackgroundBrowser(browser_path)
            webbrowser.register("chrome", None, browser)
            webbrowser.open = webbrowser.get("chrome").open
            logger.info("Registered browser for WhatsApp automation: %s", browser_path)
            return True
        except Exception as e:
            logger.warning("Could not register browser %s: %s", browser_path, e)
    # If no specific Chromium browser executable is found, fallback to system default browser
    return False

# Attempt to register browser dynamically
_register_chrome()



def is_valid_sendable_phone(phone: str) -> bool:
    """Verify phone has valid 10-digit Indian mobile format (starting with 6, 7, 8, or 9)."""
    if not phone:
        return False
    digits = "".join(c for c in str(phone) if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return len(digits) == 10 and digits[0] in "6789"


def _normalize_phone(phone: str) -> str:
    """
    Normalize a phone number to E.164 format (+91XXXXXXXXXX for India).

    Handles:
        +91XXXXXXXXXX   → unchanged
        91XXXXXXXXXX    → +91XXXXXXXXXX
        XXXXXXXXXX      → +91XXXXXXXXXX  (10 digits)
        0XXXXXXXXXX     → +91XXXXXXXXXX  (11 digits starting with 0)
        other           → prepend + and use as-is
    """
    phone = str(phone).strip().replace(" ", "").replace("-", "")

    if phone.startswith("+"):
        return phone

    if phone.startswith("91") and len(phone) == 12:
        return f"+{phone}"

    if len(phone) == 11 and phone.startswith("0"):
        return f"+91{phone[1:]}"

    if len(phone) == 10:
        return f"+91{phone}"

    return f"+{phone}"


def get_whatsapp_web_url(phone: str, message: str) -> str:
    """
    Generate a direct WhatsApp Web URL for 1-click browser dispatch.
    """
    if not phone or not is_valid_sendable_phone(phone):
        return ""
    norm = _normalize_phone(phone).lstrip("+")
    return f"https://web.whatsapp.com/send?phone={norm}&text={quote(message)}"


try:
    import ctypes
    # Enable per-monitor DPI awareness so pixel coordinates match screen DPI exactly
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    import pyautogui
    _PYAUTOGUI_AVAILABLE = True
except Exception:
    _PYAUTOGUI_AVAILABLE = False


def _activate_browser_window(hwnd: int) -> bool:
    """
    Robustly activates and brings a window to the foreground on Windows 10/11,
    bypassing the OS restriction on background processes setting the foreground window.
    """
    if sys.platform != "win32":
        return False
    try:
        import win32gui
        import win32con
        import ctypes

        user32 = ctypes.windll.user32

        # 1. Restore if minimized, or maximize for consistent coordinate layout
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)

        # 2. Bypass Windows foreground lock via Alt key press simulation
        user32.keybd_event(0x12, 0, 0, 0)  # Alt key down
        user32.keybd_event(0x12, 0, 2, 0)  # Alt key up

        # 3. Attach input threads to inherit foreground activation rights
        cur_tid = user32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0

        if fg_tid and cur_tid != fg_tid:
            user32.AttachThreadInput(cur_tid, fg_tid, True)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            user32.AttachThreadInput(cur_tid, fg_tid, False)
        else:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)

        return True
    except Exception as e:
        logger.debug("Could not activate browser window: %s", e)
        return False


def _find_whatsapp_window() -> Optional[int]:
    """
    Finds the browser window where WhatsApp Web is actively displayed in the foreground tab.
    Strictly filters for 'whatsapp' in the window title to avoid ever interacting with
    the Solaron Messaging Dashboard or other user tabs.
    """
    if sys.platform != "win32":
        return None
    try:
        import win32gui

        matches = []

        def enum_cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).strip()
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w > 400 and h > 300:
                    t_lower = title.lower()
                    if "whatsapp" in t_lower:
                        matches.append(hwnd)
            return True

        win32gui.EnumWindows(enum_cb, None)
        if matches:
            return matches[0]
    except Exception as e:
        logger.debug("Window enumeration note: %s", e)
    return None


def _submit_whatsapp_message(target_hwnd: Optional[int] = None) -> None:
    """
    Submits the pre-populated WhatsApp message by safely focusing the composer
    at an offset well above the taskbar, then pressing Enter to send.
    """
    browser_rect = None
    if target_hwnd:
        _activate_browser_window(target_hwnd)
        time.sleep(0.5)
        try:
            import win32gui
            browser_rect = win32gui.GetWindowRect(target_hwnd)
        except Exception:
            pass

    if not _PYAUTOGUI_AVAILABLE:
        raise RuntimeError("pyautogui is required for WhatsApp Web transmission automation.")

    sw, sh = pyautogui.size()
    if browser_rect and (browser_rect[2] > browser_rect[0]) and (browser_rect[3] > browser_rect[1]):
        left, top, right, bottom = browser_rect
        left = max(0, left)
        right = min(right, sw)
        bottom = min(bottom, sh)
        w = right - left
        h = bottom - top
        # Safe focus point: 65% across (chat area) and well above taskbar (at least 90px above bottom)
        focus_x = left + int(w * 0.65)
        focus_y = max(top + 200, min(top + int(h * 0.88), bottom - 95))
    else:
        focus_x = int(sw * 0.65)
        focus_y = sh - 100

    # Step 1: Click safely inside the composer box to ensure keyboard focus
    pyautogui.moveTo(focus_x, focus_y, duration=random.uniform(0.12, 0.22))
    pyautogui.mouseDown()
    time.sleep(random.uniform(0.06, 0.12))
    pyautogui.mouseUp()
    time.sleep(random.uniform(0.35, 0.65))

    # Step 2: Press Enter to submit the pre-populated message with realistic human jitter
    pyautogui.keyDown("enter")
    time.sleep(random.uniform(0.12, 0.20))
    pyautogui.keyUp("enter")
    time.sleep(0.5)


def _safe_close_whatsapp_tab(target_hwnd: Optional[int]) -> None:
    """
    Safely closes ONLY an actively verified WhatsApp tab.
    Strictly verifies that 'whatsapp' is in the window title and 'solaron' is NOT,
    preventing any accidental closure of the dashboard or user tabs.
    """
    if not target_hwnd or sys.platform != "win32":
        return
    try:
        import win32gui
        title = win32gui.GetWindowText(target_hwnd).lower().strip()
        if "whatsapp" in title and "solaron" not in title:
            _activate_browser_window(target_hwnd)
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "w")
            time.sleep(0.5)
            logger.info("Closed WhatsApp tab for clean session.")
    except Exception as e:
        logger.debug("Safe tab close skipped: %s", e)


def _wait_for_user_enter(
    target_hwnd: Optional[int] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    pause_check: Optional[Callable[[], bool]] = None,
    skip_check: Optional[Callable[[], bool]] = None,
    advance_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Waits for the user to review the pre-populated WhatsApp message and physically
    press the Enter key (without Shift) in WhatsApp Web.
    Does NOT advance until the user presses Enter, or triggers Skip, Advance, Cancel, or Pause.
    Returns: 'sent', 'skipped', or 'cancelled'.
    """
    if sys.platform != "win32":
        # Non-Windows fallback: wait fixed time
        time.sleep(10)
        return "sent"

    try:
        import ctypes
        user32 = ctypes.windll.user32
        VK_RETURN = 0x0D
        VK_SHIFT = 0x10
        # Flush any previously queued/stale keystroke state
        user32.GetAsyncKeyState(VK_RETURN)
    except Exception as e:
        logger.warning("Could not access user32 GetAsyncKeyState: %s", e)
        time.sleep(8)
        return "sent"

    logger.info("Waiting for user to review and press ENTER in WhatsApp Web...")

    while True:
        # 1. Cancellation check
        if cancel_check and cancel_check():
            logger.info("Send cancelled while waiting for user Enter.")
            return "cancelled"

        # 2. Pause check
        if pause_check and pause_check():
            while pause_check():
                if cancel_check and cancel_check():
                    return "cancelled"
                time.sleep(0.5)
            # Flush key state after resuming
            user32.GetAsyncKeyState(VK_RETURN)

        # 3. Skip check (user clicked 'Skip Plant' in dashboard)
        if skip_check and skip_check():
            logger.info("Contact skipped by user action.")
            return "skipped"

        # 4. Advance check (user clicked 'I Sent It / Next' in dashboard)
        if advance_check and advance_check():
            logger.info("Advance triggered manually by user action.")
            return "sent"

        # 5. Physical Enter key check
        # High bit (0x8000) indicates key is currently held down
        if user32.GetAsyncKeyState(VK_RETURN) & 0x8000:
            shift_pressed = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            if not shift_pressed:
                # User pressed Enter to send message!
                # Wait briefly for key release (debounce)
                t0 = time.time()
                while (user32.GetAsyncKeyState(VK_RETURN) & 0x8000) and (time.time() - t0 < 0.6):
                    time.sleep(0.03)
                logger.info("User pressed Enter in WhatsApp! Message sent.")
                return "sent"

        time.sleep(0.05)


def _send_whatsapp_instantly(
    phone_no: str,
    message: str,
    wait_time: int = 10,
    tab_close: bool = True,
    close_time: int = 2,
    is_first: bool = True,
    gap_time: int = 14,
    manual_mode: bool = True,
    cancel_check: Optional[Callable[[], bool]] = None,
    pause_check: Optional[Callable[[], bool]] = None,
    skip_check: Optional[Callable[[], bool]] = None,
    advance_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Send WhatsApp message via WhatsApp Web.
    - manual_mode=True: Opens WhatsApp Web, pasts the message into the composer, focuses the window,
      and WAITS indefinitely until the user presses Enter on their keyboard.
    - manual_mode=False: Automates focus and presses Enter automatically.
    - Closes only the WhatsApp tab after delivery so tabs never pile up.
    Returns: 'sent', 'skipped', or 'cancelled'.
    """
    clean_phone = phone_no.lstrip("+")
    url = f"https://web.whatsapp.com/send?phone={clean_phone}&text={quote(message)}"

    mode_label = "Manual (Waiting for Enter)" if manual_mode else f"Auto (wait: {wait_time}s)"
    logger.info("Opening WhatsApp Web for %s [%s]...", clean_phone, mode_label)
    webbrowser.open(url)

    # Initial wait for WhatsApp Web to open and pre-populate the composer
    render_wait = max(4, min(wait_time, 7)) if manual_mode else wait_time
    if is_first and manual_mode:
        render_wait = max(render_wait, 6)
    time.sleep(render_wait)

    # Find the active WhatsApp window
    target_hwnd = None
    for _ in range(12):
        target_hwnd = _find_whatsapp_window()
        if target_hwnd:
            _activate_browser_window(target_hwnd)
            break
        time.sleep(0.35)

    if manual_mode:
        # Await the user's manual Enter key press
        action = _wait_for_user_enter(
            target_hwnd=target_hwnd,
            cancel_check=cancel_check,
            pause_check=pause_check,
            skip_check=skip_check,
            advance_check=advance_check,
        )

        if action == "cancelled":
            return "cancelled"

        if action == "skipped":
            if tab_close:
                w_hwnd = _find_whatsapp_window() or target_hwnd
                _safe_close_whatsapp_tab(w_hwnd)
            return "skipped"

        # action == "sent"
        time.sleep(close_time)
        if tab_close:
            w_hwnd = _find_whatsapp_window() or target_hwnd
            _safe_close_whatsapp_tab(w_hwnd)
        return "sent"
    else:
        # Fully automated submit
        _submit_whatsapp_message(target_hwnd)
        time.sleep(close_time)
        if tab_close and target_hwnd:
            _safe_close_whatsapp_tab(target_hwnd)
        return "sent"


def send_whatsapp_messages(
    messages_to_send: list[dict[str, Any]],
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    pause_check: Optional[Callable[[], bool]] = None,
    skip_check: Optional[Callable[[], bool]] = None,
    advance_check: Optional[Callable[[], bool]] = None,
    wait_time: Optional[int] = None,
    tab_close: Optional[bool] = None,
    close_time: Optional[int] = None,
    gap_time: Optional[int] = None,
    manual_mode: bool = True,
) -> dict[str, Any]:
    """
    Send WhatsApp messages directly to WhatsApp Web.
    - manual_mode=True (Default): Opens each chat with pre-pasted message,
      then waits indefinitely for the user to press Enter to send.
    - manual_mode=False: Runs automated anti-ban pacing.
    """
    results: dict[str, Any] = {
        "sent": 0,
        "failed": 0,
        "skipped": 0,
        "sent_plants": [],
        "errors": [],
    }

    initial_wait = wait_time if wait_time is not None else getattr(Config, "WHATSAPP_WAIT_TIME", 12)
    min_gap = getattr(Config, "WHATSAPP_MIN_GAP", 12)
    max_gap = getattr(Config, "WHATSAPP_MAX_GAP", 16)
    if gap_time is not None and gap_time > 0:
        min_gap = max(8, gap_time - 2)
        max_gap = gap_time + 2

    batch_size = getattr(Config, "WHATSAPP_BATCH_SIZE", 18)
    cooldown_secs = getattr(Config, "WHATSAPP_BATCH_COOLDOWN", 120)
    should_close = tab_close if tab_close is not None else getattr(Config, "WHATSAPP_AUTO_CLOSE_TAB", True)
    post_close_time = close_time if close_time is not None else getattr(Config, "WHATSAPP_CLOSE_TIME", 2)

    total = len(messages_to_send)
    logger.info("Starting WhatsApp send queue for %d messages (mode: %s)...",
                total, "Manual (Press Enter to Send)" if manual_mode else "Automated Anti-Ban")

    batch_sent_count = 0

    for idx, item in enumerate(messages_to_send):
        # 1. Handle user pause (e.g. if WhatsApp Web got logged out)
        if pause_check:
            was_paused = False
            while pause_check():
                if not was_paused:
                    logger.info("Send queue paused at %d/%d. Waiting for user to resume...", idx + 1, total)
                    was_paused = True
                if cancel_check and cancel_check():
                    break
                time.sleep(0.5)
            if was_paused:
                logger.info("Send queue resumed by user at %d/%d.", idx + 1, total)

        # 2. Handle user cancellation
        if cancel_check and cancel_check():
            logger.info("Send queue cancelled by user at %d/%d.", idx + 1, total)
            break

        phone_raw = item.get("phone", "")
        message = item.get("message", "")
        name = item.get("plant_name", "unknown")

        if progress_callback:
            status_text = f"👉 Waiting for ENTER in WhatsApp to send to {name}..." if manual_mode else name
            progress_callback(idx + 1, total, status_text)

        if not phone_raw or not is_valid_sendable_phone(phone_raw):
            results["failed"] += 1
            results["errors"].append(f"{name}: invalid or missing phone ({phone_raw})")
            logger.warning("Skipping '%s' — invalid or missing phone: %s.", name, phone_raw)
            continue

        if not message:
            results["failed"] += 1
            results["errors"].append(f"{name}: empty message")
            logger.warning("Skipping '%s' — empty message.", name)
            continue

        phone = _normalize_phone(phone_raw)
        is_first = (idx == 0)
        current_wait = initial_wait if is_first else int(random.uniform(min_gap, max_gap))

        try:
            action = _send_whatsapp_instantly(
                phone_no=phone,
                message=message,
                wait_time=current_wait,
                tab_close=should_close,
                close_time=post_close_time,
                is_first=is_first,
                gap_time=current_wait,
                manual_mode=manual_mode,
                cancel_check=cancel_check,
                pause_check=pause_check,
                skip_check=skip_check,
                advance_check=advance_check,
            )

            if action == "cancelled":
                logger.info("Send queue cancelled during message dispatch.")
                break
            elif action == "skipped":
                results["skipped"] += 1
                logger.info("Skipped message for %s (%d/%d).", name, idx + 1, total)
                time.sleep(1)
                continue
            else:
                # Sent successfully!
                results["sent"] += 1
                results["sent_plants"].append(name)
                batch_sent_count += 1
                logger.info("Sent successfully to %s (%d/%d).", name, idx + 1, total)

                # Delay between chats:
                if (idx + 1) < total:
                    if manual_mode:
                        # Small comfortable delay so browser tab transitions smoothly
                        time.sleep(2.0)
                    else:
                        # Automated mode cooling pause if batch reached
                        if batch_sent_count >= batch_size:
                            logger.info("Completed batch of %d messages. Pausing for %ds cooling...", batch_sent_count, cooldown_secs)
                            if progress_callback:
                                progress_callback(idx + 1, total, f"Account cooling break ({cooldown_secs}s)...")
                            for _ in range(cooldown_secs):
                                if cancel_check and cancel_check():
                                    break
                                if pause_check and pause_check():
                                    break
                                time.sleep(1)
                            batch_sent_count = 0

        except Exception as exc:
            results["failed"] += 1
            results["errors"].append(f"{name}: {exc}")
            logger.error("Failed to process %s (%s): %s", name, phone, exc)

    return results


