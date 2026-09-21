"""
services/excel_updater.py

Writes "done" to the Message Status column in the .xlsx file for plants
whose WhatsApp messages were successfully sent.

Design notes:
- Always receives a .xlsx path (parser converts .xls on upload).
- Auto-detects the header row using the same keyword scan as parser.py.
- Creates a Message Status column if one doesn't exist in the file.
- Creates a one-time .backup before the first modification.
- Uses row_index from PlantRecord for direct cell access (no full-file scan).
"""

import logging
import os
import shutil

import openpyxl

from config import Config

logger = logging.getLogger(__name__)


def _find_col_index(sheet, header_row: int, *keywords: str) -> int:
    """
    Return the 1-based column index whose header cell contains ALL keywords,
    or -1 if not found.
    """
    for idx, cell in enumerate(sheet[header_row], start=1):
        if cell.value is None:
            continue
        cell_lower = str(cell.value).strip().lower()
        if all(kw in cell_lower for kw in keywords):
            return idx
    return -1


def update_excel_status(filepath: str, sent_plants: list[tuple[str, int]]) -> bool:
    """
    Mark each plant in sent_plants as "done" in the Message Status column.

    Args:
        filepath:    Path to the .xlsx file (already converted from .xls).
        sent_plants: List of (plant_name, row_index) that were successfully sent.

    Returns:
        True on success, False on any failure.
    """
    if not sent_plants:
        return True  # nothing to do

    if not os.path.exists(filepath):
        logger.error("Excel updater: file not found at %s", filepath)
        return False

    # Create backup before first modification
    backup_path = filepath + ".backup"
    if not os.path.exists(backup_path):
        shutil.copy2(filepath, backup_path)
        logger.info("Excel backup created at %s", backup_path)

    try:
        wb = openpyxl.load_workbook(filepath)

        # Find the Report sheet (or fall back to first sheet)
        sheet = None
        for candidate in ("Report", "Sheet1"):
            if candidate in wb.sheetnames:
                sheet = wb[candidate]
                break
        if sheet is None:
            sheet = wb.active

        # Locate header row and required columns
        header_row = Config.EXCEL_DATA_START_ROW - 1
        plant_col_idx = _find_col_index(sheet, header_row, "plant", "name")
        status_col_idx = _find_col_index(sheet, header_row, "message status")

        if plant_col_idx == -1:
            plant_col_idx = 2  # fallback: column B (common in SolarOn format)
            logger.warning("Plant Name column not found; defaulting to column 2.")

        if status_col_idx == -1:
            # Create the column at the end
            status_col_idx = sheet.max_column + 1
            sheet.cell(row=header_row, column=status_col_idx, value="Message Status")
            logger.info("Created 'Message Status' column at column %d.", status_col_idx)

        # Build lookup set for fast matching (fallback)
        sent_lower = {name.lower() for name, _ in sent_plants}
        plants_to_scan = set(sent_lower)

        updated = 0
        for name, row_index in sent_plants:
            name_lower = name.lower()
            if row_index > 0:
                cell_val = sheet.cell(row=row_index, column=plant_col_idx).value
                if cell_val is not None and str(cell_val).strip().lower() == name_lower:
                    sheet.cell(row=row_index, column=status_col_idx, value="done")
                    updated += 1
                    plants_to_scan.discard(name_lower)
                else:
                    logger.warning("Plant '%s' not found at expected row %d. Will fallback to name scan.", name, row_index)
            else:
                logger.debug("Plant '%s' has row_index=0. Will fallback to name scan.", name)

        if plants_to_scan:
            logger.info("Falling back to name scan for %d plants.", len(plants_to_scan))
            for row_num in range(header_row + 1, sheet.max_row + 1):
                cell_val = sheet.cell(row=row_num, column=plant_col_idx).value
                if cell_val is None:
                    continue
                val_lower = str(cell_val).strip().lower()
                if val_lower in plants_to_scan:
                    sheet.cell(row=row_num, column=status_col_idx, value="done")
                    updated += 1
                    plants_to_scan.discard(val_lower)

        wb.save(filepath)
        wb.close()
        logger.info(
            "Excel updater: marked %d plants as 'done' in %s.", updated, filepath
        )
        return True

    except Exception as exc:
        logger.error("Excel updater failed: %s", exc)
        return False
