"""
services/excel_writer.py

Generates an Excel file containing fetched Growatt API data in the format
expected by the Solaron parsing engine.
"""

import logging
import os
from datetime import datetime
from typing import List

import pandas as pd

from config import Config
from services.excel import PlantRecord

logger = logging.getLogger(__name__)


def save_fetched_data_to_excel(
    records: List[PlantRecord], month_name: str, year: str
) -> str:
    """
    Save fetched Growatt data to an Excel file matching the SolarOn format.
    Returns the path to the saved file.
    """
    # Create filename based on the pattern expected by the system
    filename = f"SolarOn - {year}-{_month_name_to_number(month_name)}.xlsx"
    filepath = os.path.join(Config.UPLOAD_FOLDER, filename)

    logger.info("Saving fetched data to %s", filepath)

    # Define columns to match SolarOn's expected format (the header row)
    columns = [
        "No.",
        "Plant Name",
        "Energy this month(kWh)",
        "Energy this year(kWh)",
        "Energy Total(kWh)",
        "Income this month",
        "Income total",
        "CO2 emission this month(T)",
        "CO2 emission total(T)",
        "Savings",
        "Message Status",
        "Nut Bolts",
    ]

    data = []
    for i, record in enumerate(records):
        data.append(
            [
                i + 1,
                record.plant_name,
                record.energy_this_month,
                record.energy_this_year,
                record.energy_total,
                record.income_this_month,
                record.income_total,
                record.co2_this_month,
                record.co2_total,
                record.savings,
                record.message_status,
                record.nut_bolts,
            ]
        )

    df = pd.DataFrame(data, columns=columns)

    # Build the output DataFrame in the exact format the SolarOn parser expects:
    #
    #   Row 0        — metadata (e.g. "Report Date: YYYY-MM"), other cells NaN
    #   Rows 1-4     — empty (NaN), giving metadata rows total
    #   Row 5        — the column headers repeated as *data* (not as a DataFrame
    #                  header row).  The parser scans for this row by looking for
    #                  known keywords ("Plant Name", "Energy this month", etc.).
    #   Rows 6+      — actual plant data
    #
    # The file is written with header=False so that pandas does NOT write an
    # extra header line; the header-as-data row (row 5) is our column header.
    # This matches the format of the original hand-crafted SolarOn Excel exports.
    metadata_count = Config.EXCEL_DATA_START_ROW - 2  # 7 - 2 = 5 rows of metadata
    metadata_rows = pd.DataFrame(index=range(metadata_count), columns=columns)

    # Write metadata info if needed (e.g. date string)
    metadata_rows.iloc[0, 0] = (
        f"Report Date: {year}-{_month_name_to_number(month_name)}"
    )

    final_df = pd.concat(
        [metadata_rows, pd.DataFrame([columns], columns=columns), df], ignore_index=True
    )

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        final_df.to_excel(writer, sheet_name="Report", index=False, header=False)

    return filepath


def _month_name_to_number(month_name: str) -> str:
    """Convert a full month name to a 2-digit string (e.g., 'August' -> '08')."""
    try:
        return datetime.strptime(month_name, "%B").strftime("%m")
    except ValueError:
        return "01"
