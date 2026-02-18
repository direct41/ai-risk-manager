# AI Risk Manager: краткий гайд (RU)

AI Risk Manager - CLI-инструмент для анализа QA-рисков в FastAPI репозиториях.

Быстрый старт:

```bash
pip install -e '.[dev]'
riskmap analyze --sample --output-dir ./.riskmap
```

Ключевые флаги:

- `--mode pr --base main` для PR-анализа
- `--no-llm` для deterministic режима
- `--format md|json|both` для формата артефактов
- `--fail-on-severity high` для blocking поведения по порогу
- `--suppress-file .airiskignore` для suppressions

MVP ограничения:

- поддерживается только FastAPI + pytest
- инструмент не является generic SAST
