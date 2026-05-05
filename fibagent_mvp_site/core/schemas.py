"""Shared schemas and constants for FibAgent.

This project keeps the schema simple so beginners can see exactly what the
strategy engine is allowed to return.
"""

from __future__ import annotations

from typing import Any, TypedDict


REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


class EntryZone(TypedDict):
    fib_50: float
    fib_618: float


class StrategyResult(TypedDict):
    setup_found: bool
    direction: str
    entry_zone: EntryZone | None
    entry: float | None
    stop_loss: float | None
    take_profit: float | None
    confidence_score: int
    reasoning: list[str]


def no_trade_result(reason: str = "No valid setup found.") -> StrategyResult:
    """Return the required no-trade fallback structure."""
    return {
        "setup_found": False,
        "direction": "neutral",
        "entry_zone": None,
        "entry": None,
        "stop_loss": None,
        "take_profit": None,
        "confidence_score": 0,
        "reasoning": [reason],
    }


def round_result_numbers(result: StrategyResult, decimals: int = 2) -> StrategyResult:
    """Round numeric output fields for cleaner JSON display."""
    rounded: dict[str, Any] = dict(result)

    if result["entry_zone"] is not None:
        rounded["entry_zone"] = {
            "fib_50": round(result["entry_zone"]["fib_50"], decimals),
            "fib_618": round(result["entry_zone"]["fib_618"], decimals),
        }

    for key in ("entry", "stop_loss", "take_profit"):
        if result[key] is not None:
            rounded[key] = round(result[key], decimals)

    return rounded  # type: ignore[return-value]
