.DEFAULT_GOAL := help
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy

.PHONY: help
help: ## Отобразить список доступных команд с описанием
	@grep -a -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: venv
venv: ## Инициализировать виртуальное окружение .venv
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(PYTHON) -m ensurepip --upgrade >/dev/null 2>&1 || true
	@$(PIP) install --upgrade pip

.PHONY: deps
deps: venv ## Установить зависимости проекта и инструменты разработки
	@$(PIP) install -e ".[dev]"

.PHONY: deps-browser
deps-browser: ## Подготовить Chromium/Chrome для browser UI-тестов (Debian: apt, иначе проверка)
	@test -x $(PYTHON) || { echo "Нет $(PYTHON): сначала выполните 'make venv' или 'make deps'"; exit 1; }
	@$(PYTHON) -m tests.browser_support; rc=$$?; \
	if [ $$rc -eq 2 ] && [ -z "$$WISHENKA_CHROMIUM_BIN" ] \
	  && [ "$$(. /etc/os-release 2>/dev/null; echo $$ID)" = debian ] \
	  && command -v apt-get >/dev/null 2>&1; then \
	  SUDO=""; [ "$$(id -u)" -eq 0 ] || SUDO=sudo; \
	  $$SUDO apt-get update && $$SUDO apt-get install -y chromium \
	  && $(PYTHON) -m tests.browser_support; \
	else exit $$rc; fi

.PHONY: build
build: deps ## Проверить компилируемость исходного кода и сборку пакета
	@$(PYTHON) -m compileall wishenka tests

.PHONY: analyze
analyze: deps ## Запустить статический анализ кода (Ruff + Mypy)
	@echo "==> Running Ruff linter..."
	@$(RUFF) check wishenka tests
	@echo "==> Running Ruff format check..."
	@$(RUFF) format --check wishenka tests
	@echo "==> Running Mypy type checker..."
	@$(MYPY) wishenka tests

.PHONY: format
format: deps ## Автоматически отформатировать код через Ruff
	@$(RUFF) format wishenka tests
	@$(RUFF) check --fix wishenka tests

.PHONY: test
test: deps ## Запустить полный набор автоматизированных тестов
	@echo "==> Running Pytest test suite..."
	@$(PYTEST)

.PHONY: check
check: analyze test ## Единый Quality Gate (статический анализ + тесты)
	@echo "==> All Quality Gate checks passed successfully!"

.PHONY: run
run: deps ## Запустить сервис локально в режиме разработки
	@$(UVICORN) wishenka.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: clean
clean: ## Очистить кэши и временные артефакты сборки
	@rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ wishenka/__pycache__ tests/__pycache__ *.egg-info build dist .coverage
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "==> Clean completed."
