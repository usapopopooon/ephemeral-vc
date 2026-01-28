.PHONY: setup install dev test test-db test-db-start test-db-stop lint typecheck ci run clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install: setup

dev: setup
	$(PIP) install -e ".[dev]"

test: setup
	$(PYTHON) -m pytest

lint: setup
	$(VENV)/bin/ruff check src tests

typecheck: setup
	$(VENV)/bin/mypy src

run: setup
	$(PYTHON) -m src.main

clean:
	rm -rf $(VENV)
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf *.egg-info
	rm -rf .coverage
	rm -rf htmlcov
	find . -type d -name "__pycache__" -exec rm -rf {} +

# PostgreSQL を使ったテスト
test-db: setup
	./scripts/test-with-db.sh --cov --cov-report=term-missing

test-db-start:
	docker compose -f docker-compose.test.yml up -d
	@echo "Waiting for PostgreSQL..."
	@until docker compose -f docker-compose.test.yml exec -T test-db pg_isready -U test_user -d discord_util_bot_test > /dev/null 2>&1; do sleep 1; done
	@echo "PostgreSQL is ready at localhost:5432"

test-db-stop:
	docker compose -f docker-compose.test.yml down

# CI チェック (GitHub Actions と同じ)
ci: setup
	@echo "=== YAML Lint ==="
	yamllint -s .
	@echo "=== TOML Check ==="
	taplo check pyproject.toml
	@echo "=== Ruff Lint ==="
	$(VENV)/bin/ruff check src tests alembic
	@echo "=== Type Check ==="
	$(VENV)/bin/mypy src
	@echo "=== All CI checks passed! ==="

# CI チェック + DB テスト (完全な CI)
ci-full: ci test-db
