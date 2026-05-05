# FibAgent

FibAgent is an academic Python MVP for AI-assisted futures trading analysis. It
analyzes 5-minute futures candle data and detects a deterministic Two-Bar
Fibonacci Retracement setup.

FibAgent does not connect to a broker, place trades, or randomly predict market
direction. The strategy engine calculates the result first. The LLM layer is
only allowed to explain the validated JSON output.

## Why Deterministic Rules Come First

Trading analysis needs repeatable rules. If an LLM is allowed to invent entries,
stops, or targets, the result can become inconsistent and unsafe.

FibAgent avoids that by using Python functions for:

- candle body-size validation
- two-bar impulse detection
- volume confirmation
- VWAP validation
- Fibonacci retracement-zone calculation
- entry, stop loss, take profit, and confidence score

The LLM explainer can describe the result, but it cannot change any numbers.

## Agentic Workflow

1. `data_loader.py` loads and validates the CSV file.
2. `strategy.py` scans candle data using deterministic rules.
3. `schemas.py` defines the exact JSON structure.
4. `llm_explainer.py` explains the strategy result in plain English.
5. `main.py` runs the full workflow from the command line.

## CSV Format

Use a CSV file with this header:

```csv
timestamp,open,high,low,close,volume
```

The included `sample_data.csv` contains a small demo dataset.

## How To Run

From the project root:

```bash
python main.py
```

To include the plain-English explanation:

```bash
python main.py --explain
```

To use another CSV file:

```bash
python main.py --csv path/to/your_data.csv
```

If your environment only has `python3`, use:

```bash
python3 main.py --explain
```

## Example Output

```json
{
  "setup_found": true,
  "direction": "bullish",
  "entry_zone": {
    "fib_50": 104.75,
    "fib_618": 103.98
  },
  "entry": 105.6,
  "stop_loss": 100.5,
  "take_profit": 115.8,
  "confidence_score": 100,
  "reasoning": [
    "Two most recent closed candles formed a valid impulse.",
    "Each impulse candle body was at least 50% of its full range.",
    "Second impulse candle volume was greater than first candle volume.",
    "Price was above VWAP.",
    "Current candle retraced into the 50% to 61.8% Fibonacci entry zone."
  ]
}
```

If no setup is found, FibAgent returns:

```json
{
  "setup_found": false,
  "direction": "neutral",
  "entry_zone": null,
  "entry": null,
  "stop_loss": null,
  "take_profit": null,
  "confidence_score": 0,
  "reasoning": [
    "No valid setup found."
  ]
}
```

## Reliability And Ethics Guardrails

- Required CSV columns are validated before analysis.
- Missing or invalid candle values raise clear errors.
- The strategy engine never outputs a trade if confidence is below 70.
- If rules do not pass, the system returns a no-trade fallback.
- All calculations are deterministic and inspectable.
- The LLM explainer cannot change entries, stops, targets, or confidence.
- This project is for academic prototype/demo use only.
- This is not financial advice.
- This is not a trading bot.
- No broker connection or real trade execution is included.
