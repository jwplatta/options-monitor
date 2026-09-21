.PHONY: check lint format typecheck test secrets all

all: check  ## Run all checks (default)

check: lint format typecheck test secrets  ## Run lint, format, typecheck, tests, and secrets scan

lint:  ## Run ruff linter
	uv run ruff check src tests

format:  ## Check formatting (no changes)
	uv run ruff format --check src tests

typecheck:  ## Run mypy type checker
	uv run mypy src

test:  ## Run unit tests
	uv run pytest tests/unit/ -q

secrets:  ## Scan for leaked secrets
	gitleaks detect --source . -v

fix:  ## Auto-fix lint and format issues
	uv run ruff check --fix src tests
	uv run ruff format src tests
