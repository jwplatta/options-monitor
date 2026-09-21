.PHONY: check lint format typecheck test secrets all dev dev-services dev-stop

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

dev-services:  ## Start MinIO in background (port 9002)
	docker compose up minio minio-init -d

dev-stop:  ## Stop dev services
	docker compose down

dev: dev-services  ## Start MinIO + run Streamlit locally (port 8502)
	MINIO_ENDPOINT=http://localhost:9002 \
	MINIO_BUCKET=tickrake-intraday \
	MINIO_ACCESS_KEY=minioadmin \
	MINIO_SECRET_KEY=minioadmin \
	uv run streamlit run src/options_monitor/app.py --server.port 8502
