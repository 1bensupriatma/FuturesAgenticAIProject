"""Optional ICT level helpers for later project phases."""

import pandas as pd


def compute_previous_day_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Add previous day high and low columns.

    TODO: Improve this for futures sessions that do not align with calendar
    days, such as evening Globex opens.
    """
    daily = df.set_index("datetime").resample("1D").agg({"high": "max", "low": "min"})
    daily["pdh"] = daily["high"].shift(1)
    daily["pdl"] = daily["low"].shift(1)

    result = df.copy()
    result["date"] = result["datetime"].dt.floor("D")
    result = result.merge(daily[["pdh", "pdl"]], left_on="date", right_index=True, how="left")
    return result.drop(columns=["date"])


def compute_previous_week_levels(df: pd.DataFrame) -> pd.DataFrame:
    """Add previous week high and low columns.

    TODO: Define the exact trading week convention for the target futures
    market before using this in serious analysis.
    """
    weekly = df.set_index("datetime").resample("W").agg({"high": "max", "low": "min"})
    weekly["pwh"] = weekly["high"].shift(1)
    weekly["pwl"] = weekly["low"].shift(1)

    result = df.copy()
    result["week"] = result["datetime"].dt.to_period("W").dt.end_time.dt.floor("D")
    weekly_index = weekly.index.floor("D")
    levels = weekly[["pwh", "pwl"]].copy()
    levels.index = weekly_index
    result = result.merge(levels, left_on="week", right_index=True, how="left")
    return result.drop(columns=["week"])
