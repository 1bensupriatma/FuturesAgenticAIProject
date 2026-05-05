"""Command-line entry point for the FibAgent MVP."""

from __future__ import annotations

import argparse
import json

from data_loader import load_candles
from llm_explainer import explain_result
from strategy import analyze_candles


def parse_args() -> argparse.Namespace:
    """Read command-line options."""
    parser = argparse.ArgumentParser(description="Run FibAgent on 5-minute futures candle data.")
    parser.add_argument("--csv", default="sample_data.csv", help="Path to candle CSV file.")
    parser.add_argument("--reward-multiple", type=float, default=2.0, help="Reward multiple for target calculation.")
    parser.add_argument("--stop-buffer", type=float, default=1.0, help="Price buffer beyond impulse high/low for stop loss.")
    parser.add_argument("--explain", action="store_true", help="Print a plain-English explanation after JSON.")
    return parser.parse_args()


def main() -> None:
    """Load data, run deterministic strategy logic, and print JSON."""
    args = parse_args()
    candles = load_candles(args.csv)
    result = analyze_candles(
        candles,
        reward_multiple=args.reward_multiple,
        stop_buffer=args.stop_buffer,
    )

    # The strategy engine output is the source of truth.
    print(json.dumps(result, indent=2))

    if args.explain:
        print()
        print(explain_result(result))


if __name__ == "__main__":
    main()
