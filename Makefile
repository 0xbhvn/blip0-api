# Makefile for Blip0 API Project

.PHONY: help
help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: test
test: ## Run all tests
	uv run pytest

.PHONY: test-triggers
test-triggers: ## Run trigger tests only
	uv run pytest tests/api/v1/test_triggers.py -v

.PHONY: test-monitors
test-monitors: ## Run monitor tests only
	uv run pytest tests/api/v1/test_monitors.py -v

.PHONY: coverage
coverage: ## Run tests with coverage report
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

.PHONY: coverage-triggers
coverage-triggers: ## Run trigger tests with coverage
	uv run pytest tests/api/v1/test_triggers.py --cov=src.app.api.v1.triggers --cov-report=term-missing

.PHONY: coverage-monitors
coverage-monitors: ## Run monitor tests with coverage
	uv run pytest tests/api/v1/test_monitors.py --cov=src.app.api.v1.monitors --cov-report=term-missing

.PHONY: coverage-html
coverage-html: ## Generate HTML coverage report
	uv run pytest --cov=src --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

.PHONY: coverage-report
coverage-report: ## Show coverage report in terminal
	uv run coverage report -m

.PHONY: lint
lint: ## Run ruff linter
	uv run ruff check src/

.PHONY: lint-fix
lint-fix: ## Run ruff linter with auto-fix
	uv run ruff check --fix src/

.PHONY: mypy
mypy: ## Run mypy type checker
	uv run mypy src/

.PHONY: format
format: ## Format code with ruff
	uv run ruff format src/

.PHONY: check
check: lint mypy test ## Run all checks (lint, type check, tests)

.PHONY: check-coverage
check-coverage: lint mypy coverage ## Run all checks with coverage

.PHONY: clean
clean: ## Clean up generated files
	rm -rf __pycache__ .pytest_cache htmlcov .coverage coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.PHONY: install
install: ## Install dependencies
	uv pip install -e .

.PHONY: install-dev
install-dev: ## Install development dependencies
	uv pip install -e .[dev]

.PHONY: run
run: ## Run the FastAPI application
	uv run uvicorn src.app.main:app --reload

.PHONY: docker-up
docker-up: ## Start Docker services
	docker compose up -d

.PHONY: docker-down
docker-down: ## Stop Docker services
	docker compose down

.PHONY: docker-logs
docker-logs: ## Show Docker logs
	docker compose logs -f

.PHONY: db-migrate
db-migrate: ## Run database migrations
	uv run alembic upgrade head

.PHONY: db-rollback
db-rollback: ## Rollback last migration
	uv run alembic downgrade -1

.PHONY: db-makemigration
db-makemigration: ## Create a new migration
	uv run alembic revision --autogenerate

.PHONY: create-superuser
create-superuser: ## Create first superuser
	uv run python -m src.scripts.create_first_superuser

.PHONY: create-tier
create-tier: ## Create first tier
	uv run python -m src.scripts.create_first_tier