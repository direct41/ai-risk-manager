.PHONY: install test analyze-demo eval

install:
	python -m pip install --upgrade pip
	python -m pip install -e '.[dev]'

test:
	pytest --cov=ai_risk_manager --cov-fail-under=80

analyze-demo:
	riskmap analyze --sample --output-dir ./.riskmap

eval:
	python scripts/run_eval_suite.py
