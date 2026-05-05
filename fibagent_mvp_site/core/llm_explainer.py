"""Plain-English explanation layer for FibAgent.

In a production version, this file could call an LLM. For the MVP, it is a
safe placeholder that explains the deterministic JSON without changing it.
"""

from __future__ import annotations

from schemas import StrategyResult


def explain_result(result: StrategyResult) -> str:
    """Explain the strategy result without modifying numbers or inventing trades."""
    if not result["setup_found"]:
        return (
            "No valid Two-Bar Fibonacci Retracement setup was found. "
            "FibAgent will not produce entry, stop loss, or take profit levels "
            "unless every deterministic rule passes."
        )

    direction = result["direction"]
    return (
        f"FibAgent found a {direction} setup. The entry is {result['entry']}, "
        f"the stop loss is {result['stop_loss']}, and the take profit is "
        f"{result['take_profit']}. The confidence score is "
        f"{result['confidence_score']}. These values come directly from the "
        "deterministic strategy engine, not from an LLM prediction."
    )
