# AI Risk Manager: быстрый вход для FastAPI и Django/DRF команд

AI Risk Manager помогает перед merge/release ответить на два вопроса:

- где сейчас рискованные backend-потоки;
- какие тесты стоит добавить в первую очередь.

Текущий `v0.1.x` сфокусирован на FastAPI + pytest и Django/DRF.

## Быстрый старт (5 минут)

1. Установка:

```bash
pip install -e '.[dev]'
```

2. Запуск на встроенном примере:

```bash
riskmap analyze --sample --no-llm --output-dir ./.riskmap
cat ./.riskmap/report.md
```

Если нужно, можно переопределить sample:

```bash
AIRISK_SAMPLE_REPO=/path/to/local/sample riskmap analyze --sample --no-llm
```

3. Что смотреть в первую очередь:

- `.riskmap/report.md` — понятный summary + top actions.
- `.riskmap/pr_summary.md` — короткая PR-выжимка (только PR-режим).
- `.riskmap/findings.json` — машинный формат findings.
- `.riskmap/test_plan.json` — приоритизированные тестовые действия.

## Запуск на реальном репозитории

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

## Что именно анализируется

Текущие stack plugins:

- `fastapi_pytest`
- `django_drf`

Extractor собирает:

- write-endpoints (`POST|PUT|PATCH|DELETE`)
- endpoint <-> Pydantic model связи
- declared vs handled state transitions
- pytest тесты и HTTP-вызовы тестов

Детерминированные правила:

- `critical_path_no_tests`
- `missing_transition_handler`
- `broken_invariant_on_transition`
- `dependency_risk_policy_violation`

Опционально добавляется semantic AI stage (если включен LLM backend).

## Для кого это полезно сейчас

- FastAPI-команды, где нужен быстрый release-risk скан.
- Команды, где важна PR-видимость только новых high-signal рисков.
- Команды, которым нужны конкретные test actions.

## Ограничения текущей версии

- В `v0.1.x` поддерживаются extractor plugins `fastapi_pytest` и `django_drf`.
- Инструмент не является generic multi-language SAST.
- API рассчитан на local/internal usage.
- Universal/mixed-stack стратегия пока в roadmap, это не текущий shipped scope.

## Ключевые CLI флаги

- `--mode pr --base main`
- `--only-new`
- `--ci-mode advisory|soft|block-new-critical`
- `--support-level auto|l0|l1|l2`
- `--risk-policy conservative|balanced|aggressive`
- `--analysis-engine deterministic|hybrid|ai-first`
- `--provider auto|api|cli`
- `--no-llm`
- `--fail-on-severity high`
- `--suppress-file .airiskignore`

## CI-режимы (кратко)

- `advisory`: не блокирует merge по findings.
- `soft`: блокирует при новых `high|critical` findings.
- `block-new-critical`: блокирует только при `new + critical + high confidence + verified evidence`.
- Для `--support-level auto` предупреждения preflight понижают уровень поддержки на один шаг (`l2 -> l1`, `l1 -> l0`).

## API (sync)

```bash
pip install -e '.[api]'
riskmap-api
curl -s http://127.0.0.1:8000/healthz
```

## Коды завершения

- `0` — успех
- `1` — выбранный provider недоступен
- `2` — неподдерживаемый репозиторий для текущих plugins
- `3` — сработал `fail-on-severity` или `ci-mode` порог

## Trust-first eval

- Пороги: `eval/trust_thresholds.json`
- Артефакты: `trust_gate.json`, `trust_history.jsonl`, `trust_trend.json`, `trust_trend.md`

## Где смотреть дальше

- Полная англ. документация: `README.md`
- Совместимость контрактов: `docs/compatibility.md`
- План развития: `ROADMAP.md`, `BACKLOG_TRUST_FIRST.md`
