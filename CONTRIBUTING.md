# Contributing

## Development setup

1. Install Python 3.11+.
2. Install project dependencies:

```bash
uv sync
```

3. Start the dashboard locally when needed:

```bash
uv run options-monitor
```

## Workflow

1. Start from a focused branch named `feature/...`, `fix/...`, `chore/...`, `docs/...`, or `refactor/...`.
2. Keep changes targeted. Do not mix unrelated cleanup into the same branch.
3. Add or update tests for behavior changes.
4. Run relevant checks before opening a pull request.
5. Use conventional commits, for example `feat: add gex term structure chart` or `fix: handle empty options payload`.
6. Bump the package version only when cutting a release.

## Running checks

Run all checks before committing or opening a pull request:

```bash
make check    # runs lint, format, typecheck, and tests
```

Individual checks:

```bash
make lint       # uv run ruff check src tests
make format     # uv run ruff format --check src tests
make typecheck  # uv run mypy src
make test       # uv run pytest tests/unit/ -q
make fix        # auto-fix lint and format issues
```

If your change affects the dashboard UI, also run the app locally:

```bash
uv run streamlit run src/options_monitor/app.py
```

## Project boundaries

- Keep production code under `src/options_monitor/`.
- Keep automated tests under `tests/`.
- Prefer small, composable calculation and chart modules over large mixed-responsibility files.
- Document user-visible dashboard behavior or workflow changes in `README.md` when needed.
- Avoid adding external services or persistence layers unless they are clearly required by the dashboard.

## Pull requests

- Keep commits focused and intentional.
- Use conventional commit messages.
- Include tests for calculation, data-loading, or UI-gating changes.
- Call out any manual verification steps for dashboard behavior that is difficult to cover with automated tests.
