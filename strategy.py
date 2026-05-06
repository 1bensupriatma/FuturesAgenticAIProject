"""Deterministic Two-Bar Fibonacci Retracement strategy engine.

The LLM never decides whether a trade exists. This file owns all calculations.
"""

from __future__ import annotations

from typing import Any, Literal

from schemas import StrategyResult, no_trade_result, round_result_numbers


Direction = Literal["bullish", "bearish"]


def calculate_vwap(candles: list[dict[str, Any]]) -> list[float]:
    """Calculate cumulative VWAP for each candle."""
    vwaps: list[float] = []
    cumulative_price_volume = 0.0
    cumulative_volume = 0.0

    for candle in candles:
        typical_price = (candle["high"] + candle["low"] + candle["close"]) / 3
        cumulative_price_volume += typical_price * candle["volume"]
        cumulative_volume += candle["volume"]
        vwaps.append(typical_price if cumulative_volume == 0 else cumulative_price_volume / cumulative_volume)

    return vwaps


def candle_body_percent(candle: dict[str, Any]) -> float:
    """Return candle body size as a fraction of the full high-low range."""
    candle_range = candle["high"] - candle["low"]
    if candle_range <= 0:
        return 0.0
    return abs(candle["close"] - candle["open"]) / candle_range


def is_bullish(candle: dict[str, Any]) -> bool:
    return candle["close"] > candle["open"]


def is_bearish(candle: dict[str, Any]) -> bool:
    return candle["close"] < candle["open"]


def impulse_direction(first: dict[str, Any], second: dict[str, Any]) -> Direction | None:
    """Validate that two candles form a simple directional impulse."""
    if is_bullish(first) and is_bullish(second) and second["close"] > first["close"]:
        return "bullish"
    if is_bearish(first) and is_bearish(second) and second["close"] < first["close"]:
        return "bearish"
    return None


def fibonacci_zone(impulse_low: float, impulse_high: float, direction: Direction) -> dict[str, float]:
    """Calculate the 50% and 61.8% retracement prices."""
    impulse_range = impulse_high - impulse_low
    if direction == "bullish":
        return {
            "fib_50": impulse_high - impulse_range * 0.5,
            "fib_618": impulse_high - impulse_range * 0.618,
        }
    return {
        "fib_50": impulse_low + impulse_range * 0.5,
        "fib_618": impulse_low + impulse_range * 0.618,
    }


def touches_entry_zone(current: dict[str, Any], zone: dict[str, float], direction: Direction) -> bool:
    """Check whether the current candle has retraced into the Fib zone."""
    zone_low = min(zone["fib_50"], zone["fib_618"])
    zone_high = max(zone["fib_50"], zone["fib_618"])
    if direction == "bullish":
        return current["low"] <= zone_high and current["low"] >= zone_low
    return current["high"] >= zone_low and current["high"] <= zone_high


def confidence_score(
    first: dict[str, Any],
    second: dict[str, Any],
    current: dict[str, Any],
    current_vwap: float,
    direction: Direction,
) -> int:
    """Score only validated evidence. This is deterministic, not predictive."""
    score = 70

    avg_body = (candle_body_percent(first) + candle_body_percent(second)) / 2
    if avg_body >= 0.65:
        score += 10

    if second["volume"] >= first["volume"] * 1.25:
        score += 10

    if direction == "bullish" and current["close"] > current_vwap:
        score += 10
    elif direction == "bearish" and current["close"] < current_vwap:
        score += 10

    return min(score, 100)


def confidence_breakdown(
    first: dict[str, Any],
    second: dict[str, Any],
    current: dict[str, Any],
    current_vwap: float,
    direction: Direction,
) -> list[str]:
    """Explain the deterministic confidence-score components."""
    avg_body = (candle_body_percent(first) + candle_body_percent(second)) / 2
    volume_ratio = 0.0 if first["volume"] == 0 else second["volume"] / first["volume"]
    vwap_aligned = (
        current["close"] > current_vwap
        if direction == "bullish"
        else current["close"] < current_vwap
    )

    breakdown = [
        "Confidence starts at 70 after all required setup rules pass.",
        f"Average impulse candle body was {avg_body:.1%}; +10 if it is at least 65%.",
        f"Second candle volume was {volume_ratio:.2f}x the first candle volume; +10 if it is at least 1.25x.",
        (
            f"Current close was {'above' if direction == 'bullish' else 'below'} VWAP; +10 applied."
            if vwap_aligned
            else f"Current close was not {'above' if direction == 'bullish' else 'below'} VWAP; +0 applied."
        ),
        "The score is capped at 100 and measures setup quality, not win probability.",
    ]
    return breakdown


def build_trade_result(
    first: dict[str, Any],
    second: dict[str, Any],
    current: dict[str, Any],
    current_vwap: float,
    direction: Direction,
    reward_multiple: float,
    stop_buffer: float,
) -> StrategyResult:
    """Build the final JSON-safe trade setup."""
    impulse_low = min(first["low"], second["low"])
    impulse_high = max(first["high"], second["high"])
    zone = fibonacci_zone(impulse_low, impulse_high, direction)
    entry = current["close"]

    if direction == "bullish":
        stop_loss = impulse_low - stop_buffer
        risk = entry - stop_loss
        take_profit = entry + risk * reward_multiple
    else:
        stop_loss = impulse_high + stop_buffer
        risk = stop_loss - entry
        take_profit = entry - risk * reward_multiple

    if risk <= 0:
        return no_trade_result("No valid setup found.")

    score = confidence_score(first, second, current, current_vwap, direction)
    if score < 70:
        return no_trade_result("No trade: confidence score is below 70.")

    result: StrategyResult = {
        "setup_found": True,
        "direction": direction,
        "entry_zone": {"fib_50": zone["fib_50"], "fib_618": zone["fib_618"]},
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "confidence_score": score,
        "reasoning": [
            "Two most recent closed candles formed a valid impulse.",
            "Each impulse candle body was at least 50% of its full range.",
            "Second impulse candle volume was greater than first candle volume.",
            f"Price was {'above' if direction == 'bullish' else 'below'} VWAP.",
            "Current candle retraced into the 50% to 61.8% Fibonacci entry zone.",
            *confidence_breakdown(first, second, current, current_vwap, direction),
        ],
    }
    return round_result_numbers(result)


def analyze_candles(
    candles: list[dict[str, Any]],
    reward_multiple: float = 2.0,
    stop_buffer: float = 1.0,
) -> StrategyResult:
    """Scan candle data and return the most recent valid setup.

    The scan walks backward so the latest valid setup is returned first.
    """
    if len(candles) < 3:
        return no_trade_result("No valid setup found.")

    vwaps = calculate_vwap(candles)

    for index in range(len(candles) - 1, 1, -1):
        first = candles[index - 2]
        second = candles[index - 1]
        current = candles[index]

        first_body = candle_body_percent(first)
        second_body = candle_body_percent(second)
        if first_body < 0.5 or second_body < 0.5:
            continue

        if second["volume"] <= first["volume"]:
            continue

        direction = impulse_direction(first, second)
        if direction is None:
            continue

        current_vwap = vwaps[index]
        if direction == "bullish" and current["close"] <= current_vwap:
            continue
        if direction == "bearish" and current["close"] >= current_vwap:
            continue

        impulse_low = min(first["low"], second["low"])
        impulse_high = max(first["high"], second["high"])
        zone = fibonacci_zone(impulse_low, impulse_high, direction)
        if not touches_entry_zone(current, zone, direction):
            continue

        result = build_trade_result(
            first=first,
            second=second,
            current=current,
            current_vwap=current_vwap,
            direction=direction,
            reward_multiple=reward_multiple,
            stop_buffer=stop_buffer,
        )
        if result["setup_found"]:
            return result

    return no_trade_result()
