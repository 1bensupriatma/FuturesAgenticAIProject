"""Sequential workflow orchestration for the class project agent."""

from pathlib import Path
from typing import Any

from .backtest import run_backtest
from .data_loader import load_csv
from .indicators import calculate_vwap
from .strategy import analyze_three_bar_setup


def run_analysis(
    csv_path: str | Path,
    use_vwap_filter: bool = True,
    run_historical_backtest: bool = False,
    stop_offset: float = 1.0,
    reward_multiple: float = 2.0,
) -> dict[str, Any]:
    """Run the deterministic project workflow from CSV to structured output."""
    df = load_csv(csv_path)
    df["vwap"] = calculate_vwap(df)

    if len(df) < 3:
        raise ValueError("At least three bars are required for setup analysis.")

    latest_index = len(df) - 1
    setup = analyze_three_bar_setup(
        bar1=df.iloc[latest_index - 2],
        bar2=df.iloc[latest_index - 1],
        current_bar=df.iloc[latest_index],
        vwap_value=float(df.iloc[latest_index]["vwap"]),
        use_vwap_filter=use_vwap_filter,
        stop_offset=stop_offset,
        reward_multiple=reward_multiple,
    )

    output: dict[str, Any] = {
        "latest_setup": setup,
        "rows_loaded": len(df),
        "llm_payload": {
            "setup_detected": setup["setup_detected"],
            "direction": setup["direction"],
            "impulse_type": setup["impulse_type"],
            "body_percent_bar1": setup["body_percent_bar1"],
            "body_percent_bar2": setup["body_percent_bar2"],
            "volume_confirmation": setup["volume_confirmation"],
            "retrace_zone": setup["retrace_zone"],
            "vwap_alignment": setup["vwap_alignment"],
            "ict_confluence": None,
            "entry": setup["entry"],
            "stop": setup["stop"],
            "target": setup["target"],
            "risk_reward": setup["risk_reward"],
        },
    }

    if run_historical_backtest:
        output["backtest"] = run_backtest(
            df,
            use_vwap_filter=use_vwap_filter,
            stop_offset=stop_offset,
            reward_multiple=reward_multiple,
        )

    return output
