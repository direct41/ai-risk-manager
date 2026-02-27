# AI Risk Manager: что это для FastAPI-команд (RU)

AI Risk Manager - это инструмент для QA risk mapping в FastAPI-проектах.

Он отвечает на практический вопрос перед merge/release:

- где сейчас самые рискованные места в бэкенде;
- какие тесты стоит добавить в первую очередь.

Внутри работает один общий pipeline (`collector -> graph -> rules -> optional AI enrichment`) с двумя входами:

- `CLI` (`riskmap analyze`)
- `HTTP API` (`POST /v1/analyze`)

## Что именно анализируется

Текущий стек в `v0.1.x`:

- `fastapi_pytest` (FastAPI + pytest)

Extractor в первую очередь собирает:

- write-endpoints (`POST|PUT|PATCH|DELETE`)
- связи endpoint <-> Pydantic models
- declared vs handled state transitions
- pytest тесты и HTTP-вызовы из тестов

Детерминированные правила сейчас:

- `critical_path_no_tests`
- `missing_transition_handler`
- `broken_invariant_on_transition`
- `dependency_risk_policy_violation`

Опционально добавляется semantic AI stage (если включен LLM backend).

## Быстрый старт

```bash
pip install -e '.[dev]'
riskmap analyze --sample --no-llm --output-dir ./.riskmap
cat ./.riskmap/report.md
```

На встроенном примере вы увидите вывод уровня:

- `high`: write-endpoint без тестов
- `medium`: объявлен переход состояний, но не найден handler

## Что вы получаете после запуска

По умолчанию (`--format both`):

- `.riskmap/report.md` - читаемый отчет + top actions
- `.riskmap/findings.json` - findings для автоматизации
- `.riskmap/test_plan.json` - приоритизированный план тестов
- `.riskmap/graph.json` - граф сущностей/связей
- `.riskmap/findings.raw.json` - findings до merge-этапа
- `.riskmap/run_metrics.json` - метрики качества запуска
- `.riskmap/pr_summary.md` - только в PR-режиме

## Практический workflow для реального репозитория

1. На `main` создайте baseline:

```bash
riskmap analyze --no-llm --output-dir ./.riskmap/baseline
```

2. В feature-ветке запустите PR-анализ:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

3. Смотрите `./.riskmap/pr_summary.md` и `./.riskmap/findings.json`.

## Ключевые CLI флаги

- `--mode pr --base main` для PR-анализа
- `--no-llm` для deterministic режима
- `--provider auto|api|cli` для выбора LLM backend
- `--analysis-engine deterministic|hybrid|ai-first` для стратегии анализа
- `--only-new` чтобы в PR summary показывать только новые high/critical риски
- `--min-confidence high|medium|low` для фильтрации low-confidence findings
- `--ci-mode advisory|soft|block-new-critical` для порогов CI
- `--support-level auto|l0|l1|l2` для уровня зрелости stack-поддержки
- `--risk-policy conservative|balanced|aggressive` для профиля триажа рисков
- `--format md|json|both` для формата артефактов
- `--fail-on-severity high` для blocking поведения по порогу
- `--suppress-file .airiskignore` для suppressions

Профили dependency policy:

- `conservative`: только `direct_reference` и `wildcard_version`
- `balanced` (по умолчанию): `conservative` + `range_not_pinned`
- `aggressive`: `balanced` + `unpinned_version`

Trust-first eval gates:

- Пороги качества eval хранятся в `eval/trust_thresholds.json`.
- `make eval` блокирующий по умолчанию (если trust gates не пройдены, команда завершается с ошибкой).
- Для неблокирующего запуска: `AIRISK_EVAL_ENFORCE_THRESHOLDS=0 make eval`.

## Когда инструмент особенно полезен

- FastAPI сервисы, где нужно быстро находить релизные QA-риски.
- PR-процессы, где важны только новые high-signal риски.
- Команды, которым нужен список конкретных тестовых действий, а не просто warnings.

## Когда ожидания лучше ограничить

- Если вам нужен полноценный multi-language SAST.
- Если нужен production-ready hosted API (auth/multi-tenant/RBAC).
- Если проект не похож на FastAPI + pytest паттерны.

## Коды завершения

- `0` - успешно
- `1` - недоступен явно запрошенный provider (`api|cli`)
- `2` - репозиторий не соответствует поддерживаемым stack plugins в строгих уровнях (`--support-level l1|l2`)
- `3` - сработал порог `--fail-on-severity` или `--ci-mode`

## API (sync)

Запуск API-сервера:

```bash
pip install -e '.[api]'
riskmap-api
```

Проверка:

```bash
curl -s http://127.0.0.1:8000/healthz
```

`POST /v1/analyze` принимает те же поля, что и `RunContext`:

- `path`, `mode`, `base`, `no_llm`, `provider`, `baseline_graph`, `output_dir`, `format`, `fail_on_severity`, `suppress_file`, `sample`
- `analysis_engine`, `only_new`, `min_confidence`, `ci_mode`, `support_level`, `risk_policy`

## MVP ограничения

- в `v0.1.x` поддерживается только FastAPI extractor plugin
- API рассчитан на local/internal usage
- инструмент не является generic SAST
