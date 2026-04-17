PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_RISKMAP := $(VENV)/bin/riskmap
VENV_RISKMAP_API := $(VENV)/bin/riskmap-api

.PHONY: install install-api test analyze-demo serve-api eval

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

install: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e '.[dev]'

install-api: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e '.[api]'

test: install
	$(VENV_PYTHON) -m pytest --cov=ai_risk_manager --cov-fail-under=80

analyze-demo: install
	$(VENV_RISKMAP) analyze --sample --no-llm --analysis-engine deterministic --output-dir ./.riskmap

serve-api: install-api
	$(VENV_RISKMAP_API)

eval: install
	$(VENV_PYTHON) scripts/run_eval_suite.py
