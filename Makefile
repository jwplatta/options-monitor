.PHONY: check lint format typecheck test all

all: check  ## Run all checks (default)

check: lint format typecheck test  ## Run lint, format, typecheck, and tests

lint:  ## Run ruff linter
	uv run ruff check src tests

format:  ## Check formatting (no changes)
	uv run ruff format --check src tests

typecheck:  ## Run mypy type checker
	uv run mypy src

test:  ## Run unit tests
	uv run pytest tests/unit/ -q

fix:  ## Auto-fix lint and format issues
	uv run ruff check --fix src tests
	uv run ruff format src tests
