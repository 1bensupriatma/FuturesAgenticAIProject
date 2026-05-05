# FibAgent MVP Website

This folder is a standalone duplicate website for the clean FibAgent MVP.

It uses:

- `core/sample_data.csv`
- `core/data_loader.py`
- `core/strategy.py`
- `core/schemas.py`
- `core/llm_explainer.py`
- `server.py`
- `web/index.html`
- `web/app.js`
- `web/styles.css`

It does not use Yahoo Finance and does not connect to a broker. It runs the
duplicated deterministic MVP strategy against local sample data.

Run it from the repository root:

```bash
./.venv/bin/python fibagent_mvp_site/server.py
```

Then open:

```text
http://127.0.0.1:8010
```
