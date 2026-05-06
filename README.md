# FibAgent

FibAgent is an academic web prototype for AI-assisted futures trading analysis.
It analyzes 5-minute Yahoo Finance futures candles with a deterministic Two-Bar
Fibonacci Retracement strategy, then uses an agentic chat layer only to explain
or query the validated result.

FibAgent does not connect to a broker, place trades, or randomly predict market
direction.

## Objective & Design Brief

Problem:
Futures traders and students often want quick setup analysis from candle data,
but a plain LLM can hallucinate prices, invent entries, or present guesses as
trade recommendations.

Objective:
Build FibAgent, a futures-analysis assistant that separates deterministic trade
logic from LLM explanation. Python rules decide whether a valid setup exists.
The agent then explains the validated setup, answers questions about the data,
and returns JSON only when explicitly requested.

Target user:
A student, analyst, or demo reviewer who wants to inspect how an AI-assisted
workflow can analyze market data without letting the LLM invent trades.

Design principle:
The LLM is an explainer and interface layer. It is not the trading engine.

## Agentic Pattern Used

FibAgent uses two agentic workflow patterns:

1. Sequential Workflow
   - Yahoo Finance candles are loaded.
   - The candles are converted into the MVP candle schema.
   - The deterministic strategy engine scans for a setup.
   - The structured result is passed to the explanation/chat layer.
   - The UI displays chart data, JSON, and plain-English explanation.

2. Tool Use
   - The chat agent can call local data tools through `src/futures_tools.py`.
   - Those tools query `src/futures_repository.py`.
   - The agent is grounded by `src/futures_policy.txt` and by setup context
     injected from `src/web_app.py`.

This is intentionally not a fully autonomous trading agent. It does not monitor
markets by itself, place trades, or make broker decisions.

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

## Audit Logging

FibAgent creates a timestamped audit trail for each valid agent chat session.
The active transcript is created in:

```text
src/logs/agent_log_YYYYMMDD_HHMMSS.log
```

The latest active log filename is shown in the website header. It is returned by
`GET /api/health` as `active_log_path` and by each successful `POST /api/chat`
response.

The audit log records:

- backend startup events
- user chat input
- assistant intermediate responses
- tool/function calls
- tool/function results
- malformed tool arguments
- guardrail and no-trade events
- loop termination events
- final agent responses

This gives reviewers a separate persistent transcript for each conversation
with the agent. It also supports the project requirement to document tool use,
guardrails, and final responses rather than only showing the live UI.

## How The Workflow Works

1. `src/live_data.py` loads 5-minute Yahoo Finance candles through `yfinance`.
2. `src/web_app.py` converts those bars into the MVP candle schema.
3. `strategy.py` runs deterministic Two-Bar Fibonacci Retracement rules.
4. `llm_explainer.py` explains the validated result without changing numbers.
5. `src/audit_logging.py` writes terminal output and transcript files.
6. The browser UI in `web/` renders the chart, setup JSON, explanation, and
   active audit log name.
7. The floating chat agent can answer questions using the validated setup and
   market data context.

If Yahoo Finance is unavailable, the MVP endpoint can fall back to
`sample_data.csv`.

## Functional Code Map

- `strategy.py`: deterministic Two-Bar Fibonacci Retracement strategy.
- `data_loader.py`: fallback CSV validation and loading.
- `schemas.py`: required structured output shape.
- `llm_explainer.py`: plain-English explanation of validated results.
- `src/audit_logging.py`: Rich-backed terminal and transcript logging.
- `src/web_app.py`: local backend, API endpoints, and workflow orchestration.
- `src/live_data.py`: Yahoo Finance data provider and live data hub.
- `src/futures_agent.py`: tool-calling chat agent loop.
- `src/futures_tools.py`: callable data tools.
- `src/futures_repository.py`: data-query layer behind the tools.
- `src/futures_policy.txt`: prompt/policy guardrails.
- `web/`: browser UI.

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

## Prompt Iteration Log

Full standalone artifact: [PROMPT_ITERATION_LOG.md](PROMPT_ITERATION_LOG.md)

This section documents the prompt-engineering process used to move from a
generic market-analysis prompt to a safer deterministic-first agent workflow.

| Version | Goal | Prompt | Failure / Limitation | Change Made |
|---|---|---|---|---|
| 1 | Get market direction | `Analyze this market data and tell me if it is bullish or bearish.` | The response could be vague, subjective, or unsupported. The LLM could imply a trade without validated entry, stop, or target levels. | Added deterministic setup context and required the model to use validated data. |
| 2 | Force structure | `Return JSON with direction, entry, stop, target, and confidence_score. Use the current setup data.` | The chatbot returned JSON even when the user wanted plain English. It also returned `null` values when no setup existed, which looked like a bug. | Changed default behavior to plain English and made JSON optional only when requested. |
| 3 | Prevent hallucinated trades | `Use only deterministic setup state and tool outputs. Do not invent entry, stop, target, confidence, price, volume, symbol, or date.` | This solved hallucination risk but still needed clearer role separation between Python rules and LLM explanation. | Added explicit role framing: Python validates; LLM explains. |
| 4 | Final optimized prompt | `Answer in plain English by default. Return JSON only when explicitly asked. Explain no-trade cases clearly. Treat tool output and deterministic setup state as source of truth.` | Final behavior matched project goals. | Kept this as the production policy in `src/futures_policy.txt` plus request context in `src/web_app.py`. |

### Iteration 1: Naive Prompt

Initial prompt:

```text
Analyze this market data and tell me if it is bullish or bearish.
```

Failure or limitation:
The answer could be vague, subjective, or unsupported. The LLM might describe a
market direction without citing data or might imply a trade without validated
entry, stop, or target levels.

Example problem:

```text
The market looks bullish and may be a good long opportunity.
```

Why this failed:
The answer sounded like a recommendation, but it did not prove that the
Two-Bar Fibonacci setup rules passed.

### Iteration 2: Structured Setup Prompt

Improved prompt:

```text
Return JSON with direction, entry, stop, target, and confidence_score.
Use the current setup data.
```

Failure or limitation:
The chatbot returned JSON even when the user wanted a normal explanation. It
also returned `null` values for entry, stop, and target when no deterministic
setup existed, which confused the user.

Example problem:

```json
{
  "direction": null,
  "entry": null,
  "stop": null,
  "target": null,
  "confidence_score": 0
}
```

Why this failed:
The JSON was technically valid, but it did not explain why trade levels were
missing. For a user-facing agent, plain English was clearer.

### Iteration 3: Deterministic-First Agent Prompt

Improved prompt:

```text
Use only the deterministic setup state and tool outputs as source of truth.
Do not invent entry, stop, target, confidence, price, volume, symbol, or date.
```

Failure or limitation:
This reduced hallucination, but the agent still needed a clearer rule for when
to answer normally versus when to return machine-readable JSON.

### Iteration 4: Final Optimized Prompt

Final optimized behavior:

```text
Use only the deterministic setup state and tool outputs as source of truth.
Answer in plain English by default.
Return JSON only when the user explicitly asks for JSON or structured output.
Do not invent entry, stop, target, confidence, price, volume, symbol, or date.
If no setup is found, explain that no trade levels are available.
```

Key prompt-engineering techniques used:

- Tool grounding: the agent must use provided tool/context data.
- Structured outputs: JSON is available when explicitly requested.
- Output filtering: plain English by default, JSON on demand.
- Guardrails: no invented trade levels, no broker-like recommendations.
- Role clarity: the LLM explains; Python rules validate.
- Source-of-truth hierarchy: deterministic strategy output overrides the LLM's
  market opinion.

The full policy lives in `src/futures_policy.txt`. The per-request context is
assembled in `src/web_app.py` before calling the agent.

## Example Agent Interaction

User:

```text
Do we have a setup right now?
```

Agent:

```text
Yes, there is a valid bearish setup according to the deterministic setup state.
The entry is 27753.5, stop loss is 27765.75, and take profit is 27729.0.
The confidence score is 100. These values come from the strategy engine, not
from an LLM prediction.
```

User:

```text
Return JSON for the current setup.
```

Agent:

```json
{
  "direction": "bearish",
  "entry": 27753.5,
  "stop": 27765.75,
  "target": 27729.0,
  "confidence_score": 100
}
```

## Evaluation & Ethics

### Evaluation Goal

The goal of evaluation was to confirm that FibAgent behaves like a grounded
agentic workflow, not like an unconstrained prediction chatbot. The system should
load market data, run deterministic strategy logic, produce structured setup
output, and use the LLM only to explain or query validated information.

### Functional Tests

| Test | Method | Expected Result | Status |
|---|---|---|---|
| Backend starts | Run `./.venv/bin/python -m src.web_app` | Local server starts on port `8000` | Passed |
| Health endpoint | `GET /api/health` | Returns `ok: true` and data-provider status | Passed |
| Strategy endpoint | `GET /api/mvp/analyze` | Returns setup JSON from Yahoo Finance-backed candles | Passed |
| Chat endpoint | `POST /api/chat` | Agent answers using current deterministic setup context | Passed |
| Frontend syntax | `node --check web/app.js` | JavaScript parses without syntax errors | Passed |
| Python syntax | `py_compile` on Python source files | Python files compile successfully | Passed |
| No-trade fallback | Strategy rules fail or confidence is below threshold | Returns `setup_found: false` and null trade levels | Passed |

### Manual Demo Checks

The following workflow was tested manually:

1. Opened `http://127.0.0.1:8000`.
2. Confirmed the chart renders recent Yahoo Finance candle data.
3. Clicked **Run Analysis**.
4. Confirmed the setup panel displays deterministic strategy output:
   - setup status
   - direction
   - entry zone
   - entry
   - stop loss
   - take profit
   - confidence/setup quality score
5. Asked the chat agent: `Do we have a setup right now?`
6. Confirmed the response explained the validated setup in plain English.
7. Asked for JSON explicitly.
8. Confirmed the agent returned JSON only when requested.

### Evaluation Criteria

FibAgent was evaluated against these criteria:

- **Grounding:** The agent should use setup context and tool outputs instead of
  inventing values.
- **Determinism:** Entry, stop loss, take profit, and confidence must come from
  Python strategy logic.
- **Usability:** The website should make the result understandable through both
  structured JSON and plain-English explanation.
- **Safety:** The app should avoid broker-like language, forced trades, or
  unsupported financial claims.
- **Fallback behavior:** If a setup is not valid, the system should return a
  no-trade result instead of forcing a bullish or bearish trade.

### Known Limitations

- Yahoo Finance data can be delayed, incomplete, or temporarily unavailable.
- The strategy is a simplified academic Two-Bar Fibonacci Retracement model.
- The confidence score measures setup quality, not probability of profit.
- The current implementation does not include historical win/loss backtesting.
- The app does not account for commissions, slippage, spreads, market regime, or
  macroeconomic events.
- The LLM explanation may sound persuasive, even though it is only summarizing
  deterministic output.

### Ethics & Safety Note

Financial data and trading setups are high-risk domains. FibAgent is designed
for academic demonstration only. A valid setup does not guarantee profit, and
`confidence_score` means setup quality, not probability of winning.

Potential risks:

- A user may misinterpret a setup as financial advice.
- A user may mistake the confidence score for a win probability.
- Yahoo Finance data quality issues may affect the analysis.
- The deterministic strategy may identify setups that still lose money.
- The LLM explanation may make the output feel more certain than it really is.

Mitigations:

- No broker integration is included.
- No trade execution is possible.
- The strategy engine returns a no-trade fallback when rules fail.
- The LLM is instructed not to invent entry, stop, target, price, volume, or
  confidence values.
- The agent explains validated setup output instead of generating trades from
  intuition.
- The README and UI frame the project as an academic prototype, not financial
  advice.

### Responsible Use Statement

FibAgent should be used only for education, prototyping, and demonstrating
agentic AI design patterns. It should not be used to make live trading decisions
without independent validation, robust backtesting, risk management, and
professional review.

## Guardrails

- Deterministic Python rules produce entries, stops, targets, and confidence.
- The LLM/chat layer can explain results, but should not invent trade levels.
- Missing or invalid fallback CSV data raises clear validation errors.
- The app is for academic prototype/demo use only.
- This is not financial advice.
- This is not a trading bot.
- No broker connection or real trade execution is included.

## Safety Note

Financial data and trading setups are high-risk domains. FibAgent is designed
for academic demonstration only. A valid setup does not guarantee profit, and
`confidence_score` means setup quality, not probability of winning.

Potential risks:

- Users may misinterpret setup quality as financial certainty.
- Yahoo Finance data can be delayed, incomplete, or temporarily unavailable.
- A deterministic strategy can still produce losing setups.
- An LLM explanation can sound more authoritative than it should.

Mitigations:

- No broker integration is included.
- No trade execution is possible.
- The LLM is instructed not to invent trade levels.
- The strategy returns a no-trade fallback when rules fail.
- The UI and README state that this is not financial advice.

## Submission Summary

This project satisfies the baseline requirements:

- Objective and design brief: documented above.
- Agentic pattern: Sequential Workflow plus Tool Use.
- Prompt iteration log: documented above.
- Functional code: `src/web_app.py`, `strategy.py`, and the `web/` UI.
- Agent interaction: chat agent receives setup context and can use local tools.
- Evaluation and ethics: documented above.
- Extension path: Prototyper UI path with a browser-based interface.
