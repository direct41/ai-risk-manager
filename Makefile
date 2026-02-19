.PHONY: install install-api test analyze-demo serve-api eval

install:
	python -m pip install --upgrade pip
	python -m pip install -e '.[dev]'

install-api:
	python -m pip install --upgrade pip
	python -m pip install -e '.[api]'

test:
	pytest --cov=ai_risk_manager --cov-fail-under=80

analyze-demo:
	riskmap analyze --sample --output-dir ./.riskmap

serve-api:
	riskmap-api

eval:
	python scripts/run_eval_suite.py
