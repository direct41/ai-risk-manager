# AI Risk Manager: краткий гайд (RU)

AI Risk Manager теперь работает как общий `core pipeline` с двумя входами:

- `CLI` (`riskmap analyze`)
- `HTTP API` (`/v1/analyze`)

Текущий extractor-стек в v0.1.x:

- `fastapi_pytest` (FastAPI + pytest)

Быстрый старт:

```bash
pip install -e '.[dev]'
riskmap analyze --sample --output-dir ./.riskmap
```

Запуск API-сервера:

```bash
riskmap-api
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/healthz
```

Ключевые CLI флаги:

- `--mode pr --base main` для PR-анализа
- `--no-llm` для deterministic режима
- `--provider auto|api|cli` для выбора LLM backend
- `--format md|json|both` для формата артефактов
- `--fail-on-severity high` для blocking поведения по порогу
- `--suppress-file .airiskignore` для suppressions

`POST /v1/analyze` принимает те же поля, что и `RunContext`:

- `path`, `mode`, `base`, `no_llm`, `provider`, `baseline_graph`, `output_dir`, `format`, `fail_on_severity`, `suppress_file`, `sample`

MVP ограничения:

- на этапе v1 поддерживается только FastAPI extractor plugin
- API рассчитан на local/internal usage (без auth/multi-tenant)
- инструмент не является generic SAST
