"""CSV loading and validation for FibAgent candle data."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from schemas import REQUIRED_COLUMNS


def load_candles(csv_path: str | Path) -> list[dict[str, Any]]:
    """Load 5-minute candle data from a CSV file.

    The strategy expects these columns:
    timestamp, open, high, low, close, volume
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        validate_columns(reader.fieldnames)
        rows = [normalize_row(row, line_number=index + 2) for index, row in enumerate(reader)]

    if len(rows) < 3:
        raise ValueError("At least three candles are required for setup detection.")

    return rows


def validate_columns(fieldnames: list[str] | None) -> None:
    """Raise a clear error if the CSV is missing required columns."""
    if fieldnames is None:
        raise ValueError("CSV file has no header row.")

    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")


def normalize_row(row: dict[str, str], line_number: int) -> dict[str, Any]:
    """Convert numeric columns to floats and reject missing values."""
    normalized: dict[str, Any] = {"timestamp": row["timestamp"]}

    if not normalized["timestamp"]:
        raise ValueError(f"Missing timestamp on CSV line {line_number}.")

    for column in ("open", "high", "low", "close", "volume"):
        raw_value = row.get(column)
        if raw_value in (None, ""):
            raise ValueError(f"Missing {column} value on CSV line {line_number}.")
        try:
            normalized[column] = float(raw_value)
        except ValueError as exc:
            raise ValueError(f"Invalid numeric value for {column} on CSV line {line_number}.") from exc

    if normalized["high"] < normalized["low"]:
        raise ValueError(f"High cannot be lower than low on CSV line {line_number}.")
    if normalized["volume"] < 0:
        raise ValueError(f"Volume cannot be negative on CSV line {line_number}.")

    return normalized
