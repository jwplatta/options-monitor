# Options Monitor

Streamlit options-data and market-monitoring dashboard. Data is sourced from tickrake (Schwab options snapshots + IBKR/Schwab candle history) stored locally at `~/.tickrake/data/`.

## Commands

```bash
# Run the app
uv run streamlit run src/options_monitor/app.py

# Tests
uv run pytest tests/unit/          # unit tests only (fast)
uv run pytest                      # all tests (includes integration)

# Lint / format
uv run ruff check src tests
uv run ruff format src tests

# Type-check
uv run mypy src
```

## Architecture

```
src/options_monitor/
  app.py              # Streamlit entry point
  config.py           # Env-var-backed data paths
  tabs/               # One file per top-level tab (gamma_map, vol, regime, summary)
  calc/               # Pure computation (gex, flow, spread, vol, ma)
  charts/             # Plotly figure builders — take precomputed data, return go.Figure
  data/               # Data loaders (options snapshots, candles)
```

Each tab owns its Streamlit widgets and session-state caching. Calc and chart layers are pure functions with no Streamlit dependency.

## Data paths (env-var overrides)

| Env var | Default |
|---|---|
| `options_monitor_OPTIONS_DIR` | `~/.tickrake/data/options/schwab/` |
| `options_monitor_CANDLE_DIR` | `~/.tickrake/data/history/ibkr-paper/` |
| `options_monitor_SCHWAB_CANDLE_DIR` | `~/.tickrake/data/history/schwab/` |

## Skills

Always invoke the relevant skill before starting work:

- **`python-code-quality`** — run after implementing any new calc, chart, or data module
- **`python-testing`** — run when writing or modifying tests
- **`python-project-setup`** — run when adding dependencies or changing project config
- **`project-backlog`** — create, search, and manage backlog items for this project
- **`explain-diff`** — explain a diff or set of changes in plain language

Use **`skillex`** to browse, pull, or update available skills.

## Gotchas

- Options snapshots are UTC-timestamped on disk; convert to Chicago time before display (see `calc/flow.py`)
- `contract_type` field must be uppercased before comparisons — raw CSV values vary
- Session-state cache keys must include `len(snapshots)` so new data on disk triggers a recompute
- `ruff` is the linter/formatter (not black/flake8); line length is 100
- mypy is strict — all new code needs type annotations
