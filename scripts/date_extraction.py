"""
Date extraction module for ETL processes.

Automatically extracts effective dates from Excel files or filenames.
Issue: #81
"""
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl

logger = logging.getLogger(__name__)


def extract_date_from_excel(
        file_path: str,
        cell: str = "A1",
        fallback_cells: Optional[list[str]] = None
) -> Optional[date]:
    """
    Extract date from Excel cell.

    Supports formats:
    - "Прайс-лист от 20.01.2025"
    - "20.01.2025"
    - "2025-01-20"
    - "20/01/2025"

    Args:
        file_path: Path to Excel file
        cell: Primary cell to check (default: A1)
        fallback_cells: Additional cells to check if primary is empty

    Returns:
        Extracted date or None

    Example:
        >>> date = extract_date_from_excel("Price_List.xlsx", "A1")
        >>> print(date)
        2025-01-20
    """
    if fallback_cells is None:
        fallback_cells = ["B1", "A2", "B2"]

    cells_to_check = [cell] + fallback_cells

    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True,
                                          read_only=True)
        sheet = workbook.active

        for check_cell in cells_to_check:
            cell_value = sheet[check_cell].value

            if not cell_value:
                continue

            # Try to parse date from cell value
            extracted_date = _parse_date_from_text(str(cell_value))

            if extracted_date:
                logger.info(
                    f"Date extracted from Excel cell {check_cell}",
                    extra={
                        "file": file_path,
                        "cell": check_cell,
                        "cell_value": str(cell_value),
                        "extracted_date": extracted_date.isoformat()
                    }
                )
                workbook.close()
                return extracted_date

        workbook.close()
        logger.debug(f"No date found in Excel cells: {cells_to_check}")
        return None

    except Exception as e:
        logger.warning(f"Error reading Excel file for date extraction: {e}")
        return None


def extract_date_from_filename(file_path: str) -> Optional[date]:
    """
    Extract date from filename.

    Supports patterns:
    - "Прайс_2025_01_20.xlsx" -> 2025-01-20
    - "Price_20250120.xlsx" -> 2025-01-20
    - "2025-01-20_price.csv" -> 2025-01-20

    Args:
        file_path: Path to file

    Returns:
        Extracted date or None

    Example:
        >>> date = extract_date_from_filename("Price_2025_01_20.xlsx")
        >>> print(date)
        2025-01-20
    """
    filename = Path(file_path).name

    # Pattern 1: YYYY_MM_DD or YYYY-MM-DD
    patterns = [
        r'(\d{4})[_-](\d{2})[_-](\d{2})',  # 2025_01_20 or 2025-01-20
        r'(\d{4})(\d{2})(\d{2})',  # 20250120
        r'(\d{2})[._-](\d{2})[._-](\d{4})',  # 20.01.2025 or 20-01-2025
    ]

    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()

            # Determine format based on pattern
            if len(groups[0]) == 4:  # YYYY format
                year, month, day = int(groups[0]), int(groups[1]), int(
                    groups[2])
            else:  # DD format
                day, month, year = int(groups[0]), int(groups[1]), int(
                    groups[2])

            try:
                extracted_date = date(year, month, day)
                logger.info(
                    f"Date extracted from filename",
                    extra={
                        "filename": filename,
                        "pattern": pattern,
                        "extracted_date": extracted_date.isoformat()
                    }
                )
                return extracted_date
            except ValueError:
                continue

    logger.debug(f"No date found in filename: {filename}")
    return None


def _parse_date_from_text(text: str) -> Optional[date]:
    """
    Parse date from arbitrary text.

    Internal helper function that tries multiple date formats.
    """
    # Date patterns to try
    patterns = [
        (r'(\d{2})\.(\d{2})\.(\d{4})', '%d.%m.%Y'),  # 20.01.2025
        (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),  # 2025-01-20
        (r'(\d{2})/(\d{2})/(\d{4})', '%d/%m/%Y'),  # 20/01/2025
        (r'(\d{2})-(\d{2})-(\d{4})', '%d-%m-%Y'),  # 20-01-2025
    ]

    for pattern, date_format in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(0)
            try:
                parsed_date = datetime.strptime(date_str, date_format).date()
                return parsed_date
            except ValueError:
                continue

    return None


def validate_date(extracted_date: date) -> bool:
    """
    Validate that extracted date is reasonable.

    Rules:
    - Not in the future
    - Not before 2000-01-01

    Args:
        extracted_date: Date to validate

    Returns:
        True if valid, raises ValueError if invalid

    Raises:
        ValueError: If date is invalid
    """
    today = date.today()

    # Check 1: Not in future
    if extracted_date > today:
        raise ValueError(
            f"Date {extracted_date} is in the future! "
            f"Today is {today}."
        )

    # Check 2: Not too old (after 2000)
    if extracted_date.year < 2000:
        raise ValueError(
            f"Date {extracted_date} is too old (before 2000)!"
        )

    return True


def get_effective_date(
        file_path: str,
        asof_override: Optional[date] = None,
        date_cell: str = "A1"
) -> date:
    """
    Get effective date with priority system.

    Priority:
    1. --asof override (if provided explicitly)
    2. Excel cell (A1 or B1)
    3. Filename
    4. Today (fallback)

    Args:
        file_path: Path to the file
        asof_override: Explicit date override from --asof parameter
        date_cell: Excel cell to check (default: A1)

    Returns:
        Effective date

    Raises:
        ValueError: If extracted date fails validation

    Example:
        >>> date = get_effective_date("Price_2025_01_20.xlsx")
        >>> print(date)
        2025-01-20
    """
    # Priority 1: Explicit override
    if asof_override:
        validate_date(asof_override)
        logger.info(
            "Using date from --asof override",
            extra={"date": asof_override.isoformat()}
        )
        return asof_override

    # Priority 2: Excel cell (for .xlsx, .xls files)
    if file_path.endswith(('.xlsx', '.xls', '.xlsm')):
        date_from_excel = extract_date_from_excel(file_path, date_cell)
        if date_from_excel:
            validate_date(date_from_excel)
            return date_from_excel

    # Priority 3: Filename
    date_from_filename = extract_date_from_filename(file_path)
    if date_from_filename:
        validate_date(date_from_filename)
        return date_from_filename

    # Priority 4: Fallback to today
    today = date.today()
    logger.warning(
        "Could not extract date from file. Using today as fallback.",
        extra={
            "file": file_path,
            "fallback_date": today.isoformat()
        }
    )
    return today
