"""
Solaron Message Sender Abstraction
Supports Console (dry-run), CSV export, Playwright WhatsApp Web, and Cloud API stub.
"""

import os
import csv
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
from config import Config


class MessageSender(ABC):
    @abstractmethod
    def send(self, phone: str, message: str, **kwargs) -> Dict[str, Any]:
        """
        Sends a message to the target phone number.
        Returns:
            {"success": bool, "status": str, "error": Optional[str]}
        """
        pass


class ConsoleSender(MessageSender):
    """Dry-run sender: prints message to console and marks as SIMULATED."""

    def send(self, phone: str, message: str, **kwargs) -> Dict[str, Any]:
        try:
            print(f"\n[DRY RUN] TO: {phone}")
            print(f"{message}")
            print("-" * 40)
        except Exception:
            # Fallback for Windows consoles with non-UTF-8 code pages
            safe_msg = message.encode("ascii", errors="replace").decode("ascii")
            print(f"\n[DRY RUN] TO: {phone}")
            print(f"{safe_msg}")
            print("-" * 40)
        return {"success": True, "status": "SIMULATED", "error": None}


class CSVExportSender(MessageSender):
    """Writes dispatched messages to a CSV export file."""

    def __init__(self, export_path: Optional[str] = None):
        if not export_path:
            date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            exports_dir = os.path.join(Config.DATA_FOLDER, "exports")
            os.makedirs(exports_dir, exist_ok=True)
            self.export_path = os.path.join(exports_dir, f"whatsapp_campaign_{date_str}.csv")
        else:
            self.export_path = export_path
            os.makedirs(os.path.dirname(self.export_path), exist_ok=True)

        # Initialize header if file does not exist
        if not os.path.exists(self.export_path):
            with open(self.export_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["phone_number", "message_text", "timestamp", "customer_name", "plant_name"])

    def send(self, phone: str, message: str, **kwargs) -> Dict[str, Any]:
        try:
            with open(self.export_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    phone,
                    message,
                    datetime.now().isoformat(),
                    kwargs.get("customer_name", ""),
                    kwargs.get("plant_name", "")
                ])
            return {"success": True, "status": "SENT", "error": None, "export_path": self.export_path}
        except Exception as e:
            return {"success": False, "status": "FAILED", "error": str(e)}


class WhatsAppWebSender(MessageSender):
    """
    Playwright automation via WhatsApp Web session.
    Delegates to the existing services.messaging.whatsapp if available.
    """

    def send(self, phone: str, message: str, **kwargs) -> Dict[str, Any]:
        try:
            from services.messaging.whatsapp import WhatsAppService
            svc = WhatsAppService()
            # If WhatsAppService is available
            res = svc.send_single_message(phone, message)
            if res.get("success"):
                return {"success": True, "status": "SENT", "error": None}
            else:
                return {"success": False, "status": "FAILED", "error": res.get("error", "Failed to send via WhatsApp Web")}
        except ImportError:
            return {"success": False, "status": "FAILED", "error": "WhatsAppService not installed or Playwright browser unavailable"}
        except Exception as e:
            return {"success": False, "status": "FAILED", "error": str(e)}


class WhatsAppAPISender(MessageSender):
    """Official WhatsApp Cloud API stub."""

    def send(self, phone: str, message: str, **kwargs) -> Dict[str, Any]:
        return {
            "success": False,
            "status": "FAILED",
            "error": "WhatsApp Cloud API credentials not configured in environment."
        }
