.PHONY: check lint format typecheck test secrets all dev dev-services dev-stop dev-shared dev-shared-stop

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

dev-shared:  ## Run a hot-reloading dev app on port 8502 using the running prod MinIO
	docker compose -f docker-compose.shared-minio.yml -p options-monitor-dev up -d --build

dev-shared-stop:  ## Stop the shared-MinIO dev app only
	docker compose -f docker-compose.shared-minio.yml -p options-monitor-dev down

dev: dev-services  ## Start MinIO + run Streamlit locally (port 8502)
	MINIO_ENDPOINT=http://localhost:9002 \
	MINIO_INTRADAY_BUCKET=tickrake-intraday \
	MINIO_HISTORICAL_BUCKET=tickrake-historical \
	MINIO_ACCESS_KEY=minioadmin \
	MINIO_SECRET_KEY=minioadmin \
	uv run streamlit run src/options_monitor/app.py --server.port 8502
