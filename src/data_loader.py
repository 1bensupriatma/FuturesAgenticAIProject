"""CSV loading and validation utilities for futures bar data."""

from pathlib import Path

import pandas as pd


REQUIRED_COLUMNS = ["datetime", "open", "high", "low", "close", "volume"]


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load futures OHLCV data from CSV and sort it chronologically."""
    df = pd.read_csv(path)
    validate_columns(df)

    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)

    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="raise")

    return df


def validate_columns(df: pd.DataFrame) -> None:
    """Raise a helpful error when required OHLCV columns are missing."""
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
