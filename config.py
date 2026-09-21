import os
import shutil
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine runtime base directories
_IS_FROZEN = getattr(sys, "frozen", False)
if _IS_FROZEN:
    _BASE_APP = os.path.dirname(sys.executable)
    _BUNDLE_DIR = getattr(sys, "_MEIPASS", _BASE_APP)
else:
    _BASE_APP = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _BASE_APP

_ENV_FILE_PATH = os.path.join(_BASE_APP, ".env")
if not os.path.exists(_ENV_FILE_PATH):
    _PARENT_ENV = os.path.join(os.path.dirname(_BASE_APP), "Message Dashboard.env")
    if os.path.exists(_PARENT_ENV):
        _ENV_FILE_PATH = _PARENT_ENV


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Growatt API ---
    GROWATT_USER: str = ""
    GROWATT_PASSWORD: str = ""
    GROWATT_SERVER_URL: str = "https://server-api.growatt.com/"
    GROWATT_FETCH_DELAY: float = 0.5

    # --- iSolarCloud ---
    ISOLARCLOUD_USER: str = ""
    ISOLARCLOUD_PASSWORD: str = ""
    ISOLARCLOUD_URL: str = "https://web3.isolarcloud.in/"

    # --- SuryaLog ---
    SURYALOG_USER: str = ""
    SURYALOG_PASSWORD: str = ""
    SURYALOG_URL: str = "https://cloud.suryalog.ae/"

    # --- WhatsApp Anti-Ban Configuration ---
    TEST_PHONE_NUMBER: str = ""
    SUPPORT_PHONE: str = ""
    WHATSAPP_WAIT_TIME: int = 12  # Seconds to wait for WhatsApp Web to load on initial launch
    WHATSAPP_MESSAGE_GAP: int = 14  # Safe humanized average gap between messages (seconds)
    WHATSAPP_MIN_GAP: int = 12  # Minimum randomized gap (seconds)
    WHATSAPP_MAX_GAP: int = 16  # Maximum randomized gap (seconds)
    WHATSAPP_BATCH_SIZE: int = 18  # Messages per batch before cooling pause (15-20)
    WHATSAPP_BATCH_COOLDOWN: int = 120  # Cooling pause in seconds (2 minutes)
    WHATSAPP_AUTO_CLOSE_TAB: bool = True  # Safely close WhatsApp tab after sending (protected from dashboard)
    WHATSAPP_CLOSE_TIME: int = 2  # Seconds to wait after message transmission


    # --- Automation & Background Scheduler ---
    AUTO_LOAD_ON_STARTUP: bool = True
    AUTO_FETCH_ON_STARTUP: bool = True
    AUTO_SYNC_ENABLED: bool = True
    AUTO_SYNC_DAILY_HOUR: int = 19  # 7:00 PM IST
    AUTO_SYNC_MONTHLY_DAY: int = 1  # 1st of month
    AUTO_SYNC_MONTHLY_HOUR: int = 1  # 1:00 AM IST

    # --- Business Logic ---
    PRICE_PER_UNIT: float = 14.0  # ₹ per kWh; update if tariff changes


    # --- Messages ---
    MSG_DAILY: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Your solar plant generated {energy} units today ({date}).\n"
        "You have saved approximately ₹{savings}.\n"
        "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
        "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_WEEKLY: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Your solar plant generated approximately {energy} units this week.\n"
        "You have saved approximately ₹{savings}.\n"
        "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
        "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_ACTIVE: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Your solar plant generated {energy} units in the previous month {month_name} {year}\n"
        "You have saved approximately ₹{savings}\n"
        "Kindly ensure regular cleaning of your plant maximizes your savings.\n"
        "If you want to buy cleaning equipment like telescopic poles, or have any other query, please reach out to us.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_YEARLY: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Your solar plant generated {energy} units in the year {year}.\n"
        "You have saved approximately ₹{savings}.\n"
        "Thank you for choosing Solaron as your solar partner!\n"
        "For annual maintenance contracts, panel cleaning, or queries, please reach out to us.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_OFFLINE: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "your solar plant is offline. please check once physically...\n\n"
        "If any queries, please connect with our team at {support_phone}\n\n"
        "Team solaron,\n\n"
        "सोलरॉन होम्स प्राइवेट लिमिटेड की ओर से आपको शुभकामनाएं\n\n"
        "प्रिय महोदय/मैम,\n"
        "आपका सोलर प्लांट ऑफ़लाइन है। कृपया एक बार भौतिक रूप से जाँच लें...\n\n"
        "यदि कोई प्रश्न हैं, तो कृपया हमारी टीम को कॉल कीजिए {support_phone}\n\n"
        "टीम सोलरॉन"
    ).replace("\\n", "\n")

    MSG_NOT_WORKING: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Our telemetry system detected that your solar plant is communicating but is currently NOT generating power (0 kW output / inverter alert).\n\n"
        "Please check if your AC/DC isolator switches or inverter display shows any error code.\n"
        "For immediate technical support, please contact our support team at {support_phone}.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_DEVIATION: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "Our solar analytics system noticed that your plant generation is {deviation_pct}% below benchmark.\n"
        "Dust accumulation, module shading, or string issues can reduce energy savings. We recommend checking panel cleanliness.\n"
        "For maintenance or cleaning service, please connect with us at {support_phone}.\n\n"
        "Thank You,\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    MSG_MONSOON: str = (
        "Greetings From Solaron Homes Pvt Ltd,\n\n"
        "Dear Sir/Madam,\n"
        "The monsoon season is going on and this will result in wind speed going up. We strongly recommend that you’ll carry out the pre monsoon check up for your solar plants. As part of the pre monsoon check up we shall check the overall plant working and also tighten any loose nuts and bolts. Please contact us at {support_phone} for a single visit or for the annual service contracts.\n"
        "Thank You\n"
        "Team Solaron"
    ).replace("\\n", "\n")

    # --- Paths ---
    _BASE: str = _BASE_APP
    _BUNDLE: str = _BUNDLE_DIR
    BASE_DIR: str = _BASE_APP

    STATIC_FOLDER: str = os.path.join(_BUNDLE_DIR, "static")
    TEMPLATES_FOLDER: str = os.path.join(_BUNDLE_DIR, "templates")

    UPLOAD_FOLDER: str = os.path.join(_BASE_APP, "uploads")
    DATA_FOLDER: str = os.path.join(_BASE_APP, "data")
    GROWATT_CACHE_DIR: str = os.path.join(DATA_FOLDER, "growatt_cache")
    ISOLARCLOUD_CACHE_DIR: str = os.path.join(DATA_FOLDER, "isolarcloud_cache")
    SURYALOG_CACHE_DIR: str = os.path.join(DATA_FOLDER, "suryalog_cache")
    HISTORY_DIR: str = os.path.join(DATA_FOLDER, "history")

    # --- Excel format ---
    EXCEL_DATA_START_ROW: int = 7  # 1-based index (5 metadata rows + 1 header row)

    # --- Security ---
    MAX_CONTENT_LENGTH: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: set = {".xls", ".xlsx"}
    ALLOWED_MIMES: set = {
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    }

    # --- CRM Financial Constants & Paths ---
    PRICE_PER_UNIT_INR: float = 14.0
    CO2_FACTOR_KG_PER_KWH: float = 0.82
    AVG_HOUSEHOLD_KWH_PER_DAY: float = 30.0

    CRM_DB_PATH: str = os.path.join(_BASE_APP, "data", "crm_data.db")
    ANALYTICS_DB_PATH: str = os.environ.get(
        "SOLAR_ANALYTICS_DB_PATH",
        os.path.abspath(os.path.join(_BASE_APP, "..", "Backend Dashboard", "data", "solar_analytics.db"))
    )

    API_KEY: str = ""

    @classmethod
    def validate(cls) -> list[str]:
        """Call at startup. Returns list of warnings (not errors — system degrades gracefully)."""
        warnings = []
        analytics_path = os.environ.get(
            "SOLAR_ANALYTICS_DB_PATH",
            os.path.abspath(os.path.join(_BASE_APP, "..", "Backend Dashboard", "data", "solar_analytics.db"))
        )
        if not os.path.exists(analytics_path):
            warnings.append(
                f"SOLAR_ANALYTICS_DB_PATH not found at {analytics_path}. "
                f"CRM statements will show no generation data. "
                f"Set SOLAR_ANALYTICS_DB_PATH env var or run Backend Dashboard seed script."
            )
        return warnings

    def init_app(self) -> None:
        """Create required directories and seed data if they don't exist."""
        os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(self.DATA_FOLDER, exist_ok=True)
        os.makedirs(self.GROWATT_CACHE_DIR, exist_ok=True)
        os.makedirs(self.ISOLARCLOUD_CACHE_DIR, exist_ok=True)
        os.makedirs(self.SURYALOG_CACHE_DIR, exist_ok=True)
        os.makedirs(self.HISTORY_DIR, exist_ok=True)

        # If data files (contacts.csv, Leads.csv) exist in bundle but not in target data folder, copy them
        bundle_data = os.path.join(self._BUNDLE, "data")
        if os.path.exists(bundle_data) and bundle_data != self.DATA_FOLDER:
            for fname in ["contacts.csv", "Leads.csv", "phone_cache.json"]:
                src = os.path.join(bundle_data, fname)
                dst = os.path.join(self.DATA_FOLDER, fname)
                if os.path.exists(src) and not os.path.exists(dst):
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass


Config = AppConfig()
