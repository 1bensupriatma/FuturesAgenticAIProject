"""Simple sequential backtest scaffold for the Two-Bar Fib strategy."""

from typing import Any

import pandas as pd

from .strategy import analyze_three_bar_setup


def run_backtest(
    df: pd.DataFrame,
    use_vwap_filter: bool = True,
    stop_offset: float = 1.0,
    reward_multiple: float = 2.0,
) -> dict[str, Any]:
    """Scan historical bars sequentially and collect starter metrics.

    TODO: Simulate post-entry stop/target resolution bar by bar. This starter
    version detects valid plans without assigning wins or losses.
    """
    trades: list[dict[str, Any]] = []

    for index in range(2, len(df)):
        vwap_value = df.loc[index, "vwap"] if "vwap" in df.columns else None
        setup = analyze_three_bar_setup(
            bar1=df.iloc[index - 2],
            bar2=df.iloc[index - 1],
            current_bar=df.iloc[index],
            vwap_value=vwap_value,
            use_vwap_filter=use_vwap_filter,
            stop_offset=stop_offset,
            reward_multiple=reward_multiple,
        )
        if setup["setup_detected"]:
            trade = {"datetime": df.iloc[index]["datetime"], **setup}
            trades.append(trade)

    return {
        "total_trades": len(trades),
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "average_r": None,
        "cumulative_r": 0.0,
        "expectancy": None,
        "trades": trades,
        "note": "Trade detection is implemented; stop/target outcome simulation is a TODO.",
    }
