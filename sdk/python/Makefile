.PHONY: test test-unit test-integration examples examples-all lint typecheck format all validate validate-slow validate-judge validate-all

# Use python3 when available, fall back to python (Windows).
PYTHON ?= $(shell python3 --version >/dev/null 2>&1 && echo python3 || echo python)

all: lint typecheck test

test:
	$(PYTHON) -m pytest tests/unit/ -v --cov --cov-report=term-missing

test-unit:
	$(PYTHON) -m pytest tests/unit/ -v

test-integration:
	$(PYTHON) -m pytest tests/integration/ -v

examples:
	@./scripts/run_examples.sh

examples-all:
	@./scripts/run_examples.sh --all

lint:
	ruff check src/

typecheck:
	mypy src/agentspan/agents/ --ignore-missing-imports --no-strict-optional

format:
	ruff format src/ tests/

validate:
	$(PYTHON) -m validation.scripts.run_examples

validate-judge:
	$(PYTHON) -m validation.scripts.judge_results

validate-all: validate validate-judge
