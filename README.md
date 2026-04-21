# FuturesAgenticAIProject

Educational Agentic AI project for the Two-Bar Fibonacci Retrace strategy in
intraday futures analysis.

This project is not a trading bot. It is a deterministic Python analysis tool
with an optional LLM explanation layer. Trading logic is handled by small,
testable Python functions; the LLM is only used to summarize and interpret the
structured results.

## Project Goals

- Detect valid Two-Bar Fibonacci Retrace impulses.
- Compute Bar 2 retracement zones.
- Check Bar 3 entry triggers.
- Apply an optional VWAP alignment filter.
- Produce a structured trade plan with entry, stop, target, and risk/reward.
- Leave clear extension points for ICT levels and historical backtesting.
- Provide a Jupyter Notebook outline suitable for a class project deliverable.

## Strategy Rules

Impulse detection uses the last two completed bars:

- Each bar body must be at least 50% of its total range.
- Bar 2 volume must be greater than Bar 1 volume.
- Valid impulse types:
  - matched bullish: both bars close above open
  - matched bearish: both bars close below open
  - mixed bullish: opposite colors and Bar 2 closes above Bar 1 high
  - mixed bearish: opposite colors and Bar 2 closes below Bar 1 low

Retracement is based only on Bar 2:

- Bullish setup: retracement zone is the 50% to 61.8% pullback from Bar 2 high
  toward Bar 2 low.
- Bearish setup: retracement zone is the 50% to 61.8% pullback from Bar 2 low
  toward Bar 2 high.

Entry trigger:

- Bullish: current bar low touches the retracement zone.
- Bearish: current bar high touches the retracement zone.

Default stop:

- Bullish: Bar 2 low minus offset.
- Bearish: Bar 2 high plus offset.

## Repository Structure

```text
src/
  agent.py
  backtest.py
  data_loader.py
  ict_levels.py
  indicators.py
  prompts.py
  strategy.py
notebooks/
  TwoBarFibAgent.ipynb
data/
  sample_futures_data.csv
requirements.txt
```

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the analysis workflow from Python:

```python
from src.agent import run_analysis

result = run_analysis("data/sample_futures_data.csv")
print(result)
```

Open `notebooks/TwoBarFibAgent.ipynb` for the class-project outline.

## Safety Note

This repository is for education and strategy analysis only. It does not place
orders, connect to a broker, or provide financial advice.
