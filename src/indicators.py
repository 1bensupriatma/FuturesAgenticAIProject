"""Indicator calculations used by the Two-Bar Fib workflow."""

import pandas as pd


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate cumulative VWAP using typical price and volume."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cumulative_price_volume = (typical_price * df["volume"]).cumsum()
    cumulative_volume = df["volume"].cumsum()
    return cumulative_price_volume / cumulative_volume
