# AI Risk Manager: быстрый вход для FastAPI и Django/DRF команд

AI Risk Manager помогает перед merge/release ответить на три вопроса:

- где сейчас рискованные backend-потоки;
- какие тесты стоит добавить в первую очередь.
- можно ли мержить сейчас или нужен короткий release-risk triage.

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
cat ./.riskmap/merge_triage.md
```

Если нужно, можно переопределить sample:

```bash
AIRISK_SAMPLE_REPO=/path/to/local/sample riskmap analyze --sample --no-llm
```

3. Что смотреть в первую очередь:

- `.riskmap/report.md` — понятный summary + top actions.
- `.riskmap/merge_triage.md` — короткое решение по merge: `ready`, `review_required` или `block_recommended`.
- `.riskmap/pr_summary.md` — короткая PR-выжимка (только PR-режим).
- `.riskmap/graph.json` и `.riskmap/graph.analysis.json` — граф, по которому считались findings.
- `.riskmap/graph.deterministic.json` — детерминированный граф до semantic-обогащения.
- `.riskmap/findings.json` — машинный формат findings.
- `.riskmap/test_plan.json` — приоритизированные тестовые действия.
- `.riskmap/merge_triage.json` — машинный формат решения по merge и 10-минутного test-first порядка.
- В summary/report также смотрите `repository_support_state`: `supported`, `partial` или `unsupported`.

## Запуск на реальном репозитории

1. На `main` создайте baseline:

```bash
riskmap analyze \
  --mode full \
  --no-llm \
  --analysis-engine deterministic \
  --output-dir ./.riskmap/baseline
```

Для корректного PR-delta baseline должен содержать оба файла:
- `.riskmap/baseline/graph.json`
- `.riskmap/baseline/findings.json`

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
- `express_node`

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
- `missing_required_side_effect`
- `critical_write_missing_authz`
- `input_normalization_char_split`
- `response_field_contract_mismatch`
- `db_insert_binding_mismatch`
- `critical_write_scope_missing_entity_filter`
- `stale_write_without_conflict_guard`
- `session_token_key_mismatch`
- `stored_xss_unsafe_innerhtml`
- `reading_time_round_down_to_zero`
- `priority_formula_precedence_risk`
- `overdue_date_string_comparison`
- `pagination_page_not_normalized`
- `save_button_partial_form_enabled`
- `mobile_layout_min_width_overflow`

Опционально добавляется semantic AI stage (если включен LLM backend).

## Для кого это полезно сейчас

- FastAPI-команды, где нужен быстрый release-risk скан.
- Команды, где важна PR-видимость только новых high-signal рисков.
- Команды, которым нужны конкретные test actions.
- Команды, где AI быстро генерирует код, а review должен быстро понять, что тестировать первым.

## Merge risk triage

Новый triage-слой не ищет новые findings. Он берет уже проверенные findings и test plan, затем собирает короткий decision package:

- `ready` — активных release-risk действий в текущем scope нет.
- `review_required` — перед merge стоит пройти короткий список test-first действий.
- `block_recommended` — PR лучше не мержить до обработки верхнего риска.

Цель — не заменить QA или release approval, а сократить путь от "нашли риск" до "поняли, какой тест добавить первым".

## Ограничения текущей версии

- В `v0.1.x` поддерживаются extractor plugins `fastapi_pytest`, `django_drf`, `express_node`.
- Инструмент не является generic multi-language SAST.
- API имеет базовые сервисные защиты (token auth, rate/payload guardrails, audit/correlation controls).
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
- Для generic/advisory запусков summary явно показывает `repository_support_state`, чтобы partial/unsupported режим не выглядел как полноценная deterministic parity.

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
- Артефакты: `trust_gate.json`, `trust_history.jsonl`, `trust_trend.json`, `trust_trend.md`, `expansion_gate.json`
- Гейт расширения стека использует последовательные trust-pass прогоны (`AIRISK_EXPANSION_GATE_CONSECUTIVE_RUNS`, по умолчанию `4`).

## Где смотреть дальше

- Полная англ. документация: `README.md`
- Архитектура triage-слоя: `docs/merge-risk-triage-architecture.md`
- Совместимость контрактов: `docs/compatibility.md`
- План развития: `ROADMAP.md`, `BACKLOG_TRUST_FIRST.md`
