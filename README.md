# FibAgent

FibAgent is an academic web prototype for AI-assisted futures trading analysis.
The first website analyzes 5-minute Yahoo Finance futures candles with a
deterministic Two-Bar Fibonacci Retracement strategy, then uses the chat layer
only to explain the validated result.

FibAgent does not connect to a broker, place trades, or randomly predict market
direction.

## Current Website

Run the first website:

```bash
./.venv/bin/python -m src.web_app
```

Open:

```text
http://127.0.0.1:8000
```

Main endpoints:

- `GET /api/health`
- `GET /api/mvp/analyze`
- `POST /api/chat`

## How The Workflow Works

1. `src/live_data.py` loads 5-minute Yahoo Finance candles through `yfinance`.
2. `src/web_app.py` converts those bars into the MVP candle schema.
3. `strategy.py` runs deterministic Two-Bar Fibonacci Retracement rules.
4. `llm_explainer.py` explains the validated result without changing numbers.
5. The browser UI in `web/` renders the chart, setup JSON, and explanation.
6. The floating chat agent can answer questions using the validated setup and
   market data context.

If Yahoo Finance is unavailable, the MVP endpoint can fall back to
`sample_data.csv`.

## Deterministic Strategy Rules

The strategy checks:

- candle body size
- two-bar impulse direction
- volume confirmation
- VWAP condition
- 50% and 61.8% Fibonacci retracement zone
- entry, stop loss, take profit, and confidence score

The strategy engine never outputs a trade if confidence is below 70.

## Output Shape

When a setup is found:

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
    "Two most recent closed candles formed a valid impulse."
  ]
}
```

When no setup is found:

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

## Guardrails

- Deterministic Python rules produce entries, stops, targets, and confidence.
- The LLM/chat layer can explain results, but should not invent trade levels.
- Missing or invalid fallback CSV data raises clear validation errors.
- The app is for academic prototype/demo use only.
- This is not financial advice.
- This is not a trading bot.
- No broker connection or real trade execution is included.
