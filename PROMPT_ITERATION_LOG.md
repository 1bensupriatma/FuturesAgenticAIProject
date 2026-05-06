# FibAgent Prompt Iteration Log

This document records the prompt-engineering process used to develop FibAgent's
agentic chat behavior. The goal was to move from a vague market-analysis prompt
to a grounded, deterministic-first agent workflow.

## Summary

| Version | Goal | Prompt | Observed Problem | Fix |
|---|---|---|---|---|
| 1 | Get market direction | `Analyze this market data and tell me if it is bullish or bearish.` | The response could be vague, subjective, or sound like a trade recommendation. | Added deterministic setup context. |
| 2 | Force structure | `Return JSON with direction, entry, stop, target, and confidence_score.` | JSON appeared even when the user wanted plain English; null values looked confusing. | Made plain English the default. |
| 3 | Reduce hallucination | `Use only deterministic setup state and tool outputs. Do not invent trade levels.` | Safer, but still needed clearer output rules. | Added explicit JSON-only-when-requested rule. |
| 4 | Final behavior | `Answer in plain English by default. Return JSON only when explicitly asked. Treat deterministic output as source of truth.` | Meets project goals. | Used in `src/futures_policy.txt` and request context from `src/web_app.py`. |

## Iteration 1: Naive Market Direction Prompt

### Prompt

```text
Analyze this market data and tell me if it is bullish or bearish.
```

### Failure / Limitation

This prompt asked the LLM for a market opinion without grounding it in validated
strategy rules. The answer could sound confident even when no valid setup had
been detected.

### Example Bad Output

```text
The market looks bullish and may be a good long opportunity.
```

### Why This Failed

The response sounded like a trade recommendation. It did not prove that the
Two-Bar Fibonacci setup rules passed, and it did not identify entry, stop loss,
or take profit from deterministic calculations.

## Iteration 2: Structured JSON Prompt

### Prompt

```text
Return JSON with direction, entry, stop, target, and confidence_score.
Use the current setup data.
```

### Failure / Limitation

The response became more structured, but the chatbot returned JSON even when the
user expected a normal explanation. When no setup existed, the output looked like
a broken result instead of an understandable no-trade explanation.

### Example Problem Output

```json
{
  "direction": null,
  "entry": null,
  "stop": null,
  "target": null,
  "confidence_score": 0
}
```

### Why This Failed

The JSON was technically valid, but it did not explain why entry, stop, and
target were unavailable. For a user-facing agent, plain English was clearer.

## Iteration 3: Deterministic-First Prompt

### Prompt

```text
Use only the deterministic setup state and tool outputs as source of truth.
Do not invent entry, stop, target, confidence, price, volume, symbol, or date.
```

### Improvement

This reduced hallucination risk by making the deterministic strategy output the
source of truth.

### Remaining Problem

The prompt still needed clearer rules for when to return plain English versus
when to return JSON.

## Iteration 4: Final Optimized Prompt

### Prompt

```text
Use only the deterministic setup state and tool outputs as source of truth.
Answer in plain English by default.
Return JSON only when the user explicitly asks for JSON or structured output.
Do not invent entry, stop, target, confidence, price, volume, symbol, or date.
If no setup is found, explain that no trade levels are available.
```

### Final Behavior

- Normal questions receive plain-English explanations.
- JSON is returned only when the user explicitly asks for JSON.
- Entry, stop loss, take profit, and confidence come from deterministic Python
  strategy output.
- The LLM explains the setup but does not create the setup.
- If no setup exists, the agent explains why trade levels are unavailable.

## Techniques Used

- **Tool grounding:** The agent uses tool/context outputs instead of inventing
  market values.
- **Structured outputs:** JSON is available for machine-readable responses.
- **Output filtering:** Plain English is the default; JSON is opt-in.
- **Guardrails:** The prompt forbids invented trade levels and broker-like
  recommendations.
- **Role clarity:** Python validates; the LLM explains.
- **Source-of-truth hierarchy:** Deterministic strategy output overrides any
  model-generated market opinion.

## Production Prompt Location

The final policy lives in:

```text
src/futures_policy.txt
```

The dynamic request context is assembled in:

```text
src/web_app.py
```

Together, these tell the agent what market data and validated setup state it is
allowed to use when answering a user question.
