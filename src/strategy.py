"""Deterministic Two-Bar Fibonacci Retrace strategy logic."""

from typing import Any, Literal

import pandas as pd


Direction = Literal["bullish", "bearish"]


def body_percent(bar: pd.Series) -> float:
    """Return candle body as a fraction of total range."""
    candle_range = float(bar["high"] - bar["low"])
    if candle_range <= 0:
        return 0.0
    return abs(float(bar["close"] - bar["open"])) / candle_range


def is_bullish(bar: pd.Series) -> bool:
    """Return True when a candle closes above its open."""
    return float(bar["close"]) > float(bar["open"])


def is_bearish(bar: pd.Series) -> bool:
    """Return True when a candle closes below its open."""
    return float(bar["close"]) < float(bar["open"])


def detect_impulse(bar1: pd.Series, bar2: pd.Series) -> dict[str, Any]:
    """Detect the strict Two-Bar impulse type from the project brief."""
    body1 = body_percent(bar1)
    body2 = body_percent(bar2)
    body_confirmation = body1 >= 0.5 and body2 >= 0.5
    volume_confirmation = float(bar2["volume"]) > float(bar1["volume"])

    result: dict[str, Any] = {
        "valid": False,
        "direction": None,
        "impulse_type": None,
        "body_percent_bar1": body1,
        "body_percent_bar2": body2,
        "body_confirmation": body_confirmation,
        "volume_confirmation": volume_confirmation,
    }

    if not body_confirmation or not volume_confirmation:
        return result

    bar1_bullish = is_bullish(bar1)
    bar2_bullish = is_bullish(bar2)
    bar1_bearish = is_bearish(bar1)
    bar2_bearish = is_bearish(bar2)
    opposite_colors = (bar1_bullish and bar2_bearish) or (bar1_bearish and bar2_bullish)

    if bar1_bullish and bar2_bullish:
        result.update(valid=True, direction="bullish", impulse_type="matched_bullish")
    elif bar1_bearish and bar2_bearish:
        result.update(valid=True, direction="bearish", impulse_type="matched_bearish")
    elif opposite_colors and float(bar2["close"]) > float(bar1["high"]):
        result.update(valid=True, direction="bullish", impulse_type="mixed_bullish")
    elif opposite_colors and float(bar2["close"]) < float(bar1["low"]):
        result.update(valid=True, direction="bearish", impulse_type="mixed_bearish")

    return result


def compute_retrace_zone(bar2: pd.Series, direction: Direction) -> dict[str, float]:
    """Compute the 50% to 61.8% retracement zone from Bar 2 only."""
    high = float(bar2["high"])
    low = float(bar2["low"])
    candle_range = high - low

    if candle_range <= 0:
        raise ValueError("Bar 2 must have high greater than low.")

    if direction == "bullish":
        level_50 = high - candle_range * 0.5
        level_618 = high - candle_range * 0.618
    else:
        level_50 = low + candle_range * 0.5
        level_618 = low + candle_range * 0.618

    return {
        "retrace_low": min(level_50, level_618),
        "retrace_high": max(level_50, level_618),
        "level_50": level_50,
        "level_618": level_618,
    }


def detect_entry_trigger(current_bar: pd.Series, zone: dict[str, float], direction: Direction) -> bool:
    """Return True when the current bar touches the retracement zone."""
    retrace_low = zone["retrace_low"]
    retrace_high = zone["retrace_high"]

    if direction == "bullish":
        current_low = float(current_bar["low"])
        return retrace_low <= current_low <= retrace_high

    current_high = float(current_bar["high"])
    return retrace_low <= current_high <= retrace_high


def calculate_trade_plan(
    bar2: pd.Series,
    current_bar: pd.Series,
    zone: dict[str, float],
    direction: Direction,
    stop_offset: float = 1.0,
    reward_multiple: float = 2.0,
) -> dict[str, float]:
    """Calculate entry, stop, target, and risk/reward values."""
    entry = float(current_bar["close"])

    if direction == "bullish":
        stop = float(bar2["low"]) - stop_offset
        risk = entry - stop
        target = entry + risk * reward_multiple
    else:
        stop = float(bar2["high"]) + stop_offset
        risk = stop - entry
        target = entry - risk * reward_multiple

    if risk <= 0:
        raise ValueError("Trade risk must be positive.")

    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk": risk,
        "risk_reward": reward_multiple,
        "retrace_low": zone["retrace_low"],
        "retrace_high": zone["retrace_high"],
    }


def analyze_three_bar_setup(
    bar1: pd.Series,
    bar2: pd.Series,
    current_bar: pd.Series,
    vwap_value: float | None = None,
    use_vwap_filter: bool = True,
    stop_offset: float = 1.0,
    reward_multiple: float = 2.0,
) -> dict[str, Any]:
    """Analyze Bars 1, 2, and 3 and return a structured setup dictionary."""
    impulse = detect_impulse(bar1, bar2)
    result: dict[str, Any] = {
        "setup_detected": False,
        "direction": impulse["direction"],
        "impulse_type": impulse["impulse_type"],
        "body_percent_bar1": impulse["body_percent_bar1"],
        "body_percent_bar2": impulse["body_percent_bar2"],
        "volume_confirmation": impulse["volume_confirmation"],
        "retrace_zone": None,
        "entry_triggered": False,
        "vwap_alignment": None,
        "entry": None,
        "stop": None,
        "target": None,
        "risk_reward": None,
    }

    if not impulse["valid"]:
        return result

    direction = impulse["direction"]
    zone = compute_retrace_zone(bar2, direction)
    entry_triggered = detect_entry_trigger(current_bar, zone, direction)

    vwap_alignment = True
    if use_vwap_filter and vwap_value is not None:
        current_price = float(current_bar["close"])
        vwap_alignment = bool(current_price > vwap_value if direction == "bullish" else current_price < vwap_value)

    result.update(
        retrace_zone={
            "retrace_low": zone["retrace_low"],
            "retrace_high": zone["retrace_high"],
        },
        entry_triggered=entry_triggered,
        vwap_alignment=vwap_alignment,
    )

    if entry_triggered and vwap_alignment:
        plan = calculate_trade_plan(
            bar2=bar2,
            current_bar=current_bar,
            zone=zone,
            direction=direction,
            stop_offset=stop_offset,
            reward_multiple=reward_multiple,
        )
        result.update(
            setup_detected=True,
            entry=plan["entry"],
            stop=plan["stop"],
            target=plan["target"],
            risk_reward=plan["risk_reward"],
        )

    return result
