import pandas as pd
import numpy as np
import pytest

from services.excel.parser import (
    _find_col,
    _safe_float,
    _safe_str,
    _extract_month_year,
    PlantRecord
)

from config import Config

def test_safe_float():
    assert _safe_float("123.4") == 123.4
    assert _safe_float(123) == 123.0
    assert _safe_float("abc") == 0.0
    assert _safe_float(None) == 0.0
    assert _safe_float(np.nan) == 0.0

def test_safe_str():
    assert _safe_str(" abc ") == "abc"
    assert _safe_str(None) == ""
    assert _safe_str(np.nan) == ""
    assert _safe_str(123.4) == "123.4"

def test_find_col():
    cols = ["Plant Name", "Energy This Month", "Total Energy", "Unknown"]
    
    assert _find_col(cols, "plant") == "Plant Name"
    assert _find_col(cols, "plant", "name") == "Plant Name"
    assert _find_col(cols, "energy", "month") == "Energy This Month"
    assert _find_col(cols, "energy", "total") == "Total Energy"
    assert _find_col(cols, "savings") is None

def test_extract_month_year():
    # 1. Test extraction from filename
    month, year = _extract_month_year("SolarOn - 2026-07.xls")
    assert month == "July"
    assert year == "2026"
    
    # 2. Test extraction from df metadata
    Config.EXCEL_DATA_START_ROW = 4
    data = {
        0: ["SolarOn Report", "Date:", "Plant Name"],
        1: [np.nan, "2026-08", "Energy This Month"],
    }
    df = pd.DataFrame(data)
    month, year = _extract_month_year("unknown_file.xlsx", df)
    assert month == "August"
    assert year == "2026"
    
    # 3. Test fallback
    month, year = _extract_month_year("unknown.xlsx", pd.DataFrame())
    assert month == ""
    assert year == ""
