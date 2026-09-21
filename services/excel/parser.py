"""
services/parser.py

Parses the SolarOn Excel report into PlantRecord objects.

Key design decisions:
- Header row is AUTO-DETECTED by scanning for known column keywords.
  This handles the current format (headers at Excel row 6, 5 metadata rows above)
  as well as future formats where headers may be at row 1 or 2.
- .xls files are converted to .xlsx on upload so that openpyxl can write back.
- Month/year are extracted from the filename (SolarOn - YYYY-MM.xls).
"""

import calendar
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PlantRecord:
    plant_name: str
    energy_this_month: float
    energy_this_year: float
    energy_total: float
    income_this_month: float
    income_total: float
    co2_this_month: float
    co2_total: float
    savings: float  # read directly from the Excel file
    message_status: str  # raw value from "message status" column, "" if absent
    nut_bolts: str  # raw value from "nut bolts" column, "" if absent
    row_index: int  # 1-based Excel row number for write-back
    source: str = "excel"  # "growatt" | "isolarcloud" | "suryalog" | "excel"
    capacity_kwp: float = 0.0  # installed capacity kWp
    current_power_kw: float = 0.0  # live output kW
    energy_today: float = 0.0  # daily generation kWh
    plant_status: str = ""  # raw status
    city: str = ""  # location
    yearly_breakdown: dict = field(default_factory=dict)  # e.g. {"01": 120.5, "02": 98.3, ...}
    yearly_history: dict = field(default_factory=dict)    # e.g. {"2026": 1093.6, "2025": 1468.0, ...}
    daily_history: dict = field(default_factory=dict)     # e.g. {"2026-09-05": 14.2, "2026-09-04": 15.1, ...}
    energy_yesterday: float = 0.0                         # yesterday generation kWh
    energy_weekly: float = 0.0                            # rolling 7-day actual generation kWh
    specific_yield: float = 0.0                           # kWh/kWp for active view period
    deviation_pct: float = 0.0                            # % deviation from fleet average specific yield
    z_score: float = 0.0                                  # statistical z-score across fleet
    device_status_code: int = 1                           # 0=offline, 1=online, 2=fault
    fault_code: str = ""                                  # inverter fault code if any
    fault_desc: str = ""                                  # description of fault if any


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------


def _find_col(columns: list[str], *keywords: str) -> Optional[str]:
    """
    Return the first column name whose lowercase form contains ALL the given
    keywords, or None if not found.
    """
    for col in columns:
        col_lower = col.lower()
        if all(kw in col_lower for kw in keywords):
            return col
    return None


def _safe_float(val) -> float:
    """Convert a value to float, returning 0.0 on failure or NaN."""
    try:
        f = float(val)
        return 0.0 if np.isnan(f) else f
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val) -> str:
    """Convert a value to string, returning '' on NaN/None."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    return str(val).strip()


# ---------------------------------------------------------------------------
# Month / Year extraction
# ---------------------------------------------------------------------------


def _extract_month_year(
    filepath: str, df_raw: Optional[pd.DataFrame] = None
) -> tuple[str, str]:
    """
    Extract (month_name, year) from:
    1. Filename pattern  YYYY-MM   e.g. SolarOn - 2026-07.xls → July, 2026
    2. Metadata rows above the header in the raw DataFrame
    3. Fallback: empty strings
    """
    # 1. Filename
    basename = os.path.basename(filepath)
    m = re.search(r"(\d{4})-(\d{2})", basename)
    if m:
        year_str = m.group(1)
        month_num = int(m.group(2))
        if 1 <= month_num <= 12:
            return calendar.month_name[month_num], year_str

    # 2. Scan metadata rows
    if df_raw is not None and not df_raw.empty:
        header_row = min(Config.EXCEL_DATA_START_ROW - 2, len(df_raw))
        for row_idx in range(header_row):
            for val in df_raw.iloc[row_idx].values:
                if pd.isna(val):
                    continue
                m2 = re.search(r"(\d{4})-(\d{2})", str(val))
                if m2:
                    year_str = m2.group(1)
                    month_num = int(m2.group(2))
                    if 1 <= month_num <= 12:
                        return calendar.month_name[month_num], year_str

    return "", ""


# ---------------------------------------------------------------------------
# .xls → .xlsx conversion
# ---------------------------------------------------------------------------


def _convert_xls_to_xlsx(xls_path: str) -> str:
    """
    Convert a .xls file to .xlsx using xlrd + openpyxl.
    Returns the path to the new .xlsx file.
    The .xls original is kept intact (not deleted).
    """
    xlsx_path = xls_path + "x"  # SolarOn - 2026-07.xls → SolarOn - 2026-07.xlsx

    if os.path.exists(xlsx_path):
        logger.debug("Removing stale converted file at %s before re-converting", xlsx_path)
        os.remove(xlsx_path)

    logger.info("Converting %s → %s", xls_path, xlsx_path)
    all_sheets = pd.read_excel(xls_path, sheet_name=None, header=None, engine="xlrd")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for sheet_name, df in all_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

    return xlsx_path


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------


def parse_solaron_file(filepath: str) -> tuple[list[PlantRecord], str, str, str]:
    """
    Parse the SolarOn Excel report.

    Returns:
        records    — list of PlantRecord
        month_name — e.g. "July"
        year       — e.g. "2026"
        out_path   — path to the working .xlsx file (converted if input was .xls)
    """
    # 1. Convert .xls → .xlsx if needed
    if filepath.lower().endswith(".xls"):
        out_path = _convert_xls_to_xlsx(filepath)
    else:
        out_path = filepath

    # 2. Read raw (no header) to detect header row and extract month/year
    try:
        df_raw = pd.read_excel(
            out_path, sheet_name="Report", header=None, engine="openpyxl"
        )
    except Exception:
        try:
            df_raw = pd.read_excel(
                out_path, sheet_name=0, header=None, engine="openpyxl"
            )
        except Exception as exc:
            raise ValueError(f"Cannot read Excel file: {exc}") from exc

    month_name, year = _extract_month_year(filepath, df_raw)

    # 3. Detect header row
    header_row_idx = Config.EXCEL_DATA_START_ROW - 2

    # 4. Re-read with header at detected row
    try:
        df = pd.read_excel(
            out_path,
            sheet_name="Report",
            header=header_row_idx,
            engine="openpyxl",
        )
    except Exception:
        df = pd.read_excel(
            out_path,
            sheet_name=0,
            header=header_row_idx,
            engine="openpyxl",
        )

    # Clean column names
    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    # 5. Map columns by keyword
    plant_col = (
        _find_col(cols, "plant", "name")
        or _find_col(cols, "plant")
        or (cols[1] if len(cols) > 1 else cols[0])
    )
    month_energy_col = _find_col(cols, "energy this month") or _find_col(
        cols, "energy", "month"
    )
    year_energy_col = _find_col(cols, "energy this year") or _find_col(
        cols, "energy", "year"
    )
    total_energy_col = _find_col(cols, "energy total")
    income_month_col = _find_col(cols, "income this month") or _find_col(
        cols, "income", "month"
    )
    income_total_col = _find_col(cols, "income total")
    co2_month_col = _find_col(cols, "co2", "month") or _find_col(
        cols, "emission", "month"
    )
    co2_total_col = _find_col(cols, "co2", "total") or _find_col(
        cols, "emission", "total"
    )
    savings_col = _find_col(cols, "savings")
    status_col = _find_col(cols, "message status")
    nut_col = _find_col(cols, "nut")

    logger.debug(
        "Column mapping — plant: %s | month_energy: %s | total_energy: %s | status: %s",
        plant_col,
        month_energy_col,
        total_energy_col,
        status_col,
    )

    # 6. Parse rows
    records: list[PlantRecord] = []

    # header_row_idx is 0-based in df_raw; Excel rows are 1-based.
    # After pd.read_excel with header=header_row_idx, df.index starts at 0 for the first data row.
    # Excel row of first data row = header_row_idx + 1 (header) + 1 (first data) = header_row_idx + 2
    excel_data_start = header_row_idx + 2  # 1-based Excel row of df.iloc[0]

    for df_idx, row in df.iterrows():
        plant_name = _safe_str(row.get(plant_col) if plant_col else None)
        if not plant_name or plant_name.lower() in ("nan", "no.", "plant name"):
            continue  # skip empty rows and accidental re-reads of the header

        records.append(
            PlantRecord(
                plant_name=plant_name,
                energy_this_month=_safe_float(
                    row.get(month_energy_col) if month_energy_col else None
                ),
                energy_this_year=_safe_float(
                    row.get(year_energy_col) if year_energy_col else None
                ),
                energy_total=_safe_float(
                    row.get(total_energy_col) if total_energy_col else None
                ),
                income_this_month=_safe_float(
                    row.get(income_month_col) if income_month_col else None
                ),
                income_total=_safe_float(
                    row.get(income_total_col) if income_total_col else None
                ),
                co2_this_month=_safe_float(
                    row.get(co2_month_col) if co2_month_col else None
                ),
                co2_total=_safe_float(
                    row.get(co2_total_col) if co2_total_col else None
                ),
                savings=_safe_float(row.get(savings_col) if savings_col else None),
                message_status=_safe_str(row.get(status_col) if status_col else None),
                nut_bolts=_safe_str(row.get(nut_col) if nut_col else None),
                row_index=excel_data_start + int(df_idx),  # 1-based Excel row
            )
        )

    logger.info(
        "Parsed %d plant records from %s (month: %s %s)",
        len(records),
        os.path.basename(out_path),
        month_name,
        year,
    )
    return records, month_name, year, out_path
