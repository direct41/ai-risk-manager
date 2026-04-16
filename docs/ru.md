# AI Risk Manager: быстрый вход

AI Risk Manager помогает перед merge/release ответить на три вопроса:

- где сейчас самые рискованные изменения;
- какие тесты стоит добавить в первую очередь.
- можно ли мержить сейчас или нужен короткий release-risk triage.

Текущий shipped-профиль — `code_risk`.
Лучше всего он работает на backend-heavy репозиториях. Самая сильная поддержка сейчас у `FastAPI`, `Django/DRF` и `Express/Node`, но на неизвестных стеках тоже есть полезный advisory path через universal heuristics.

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

## Что именно анализируется сейчас

Сильнейшие stack plugins:

- `fastapi_pytest`
- `django_drf`
- `express_node`

`code_risk` сейчас покрывает:

- write-endpoints (`POST|PUT|PATCH|DELETE`)
- endpoint <-> Pydantic model связи
- declared vs handled state transitions
- pytest тесты и HTTP-вызовы тестов
- generated test quality
- workflow automation risks
- PR delta heuristics по code/dependencies/contracts/migrations/runtime config/auth/payment/admin paths

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

## Архитектура

Новый канонический подход:

- один общий pipeline
- optional risk profiles
- применимость профиля: `supported`, `partial`, `not_applicable`
- один общий PR/report output contract

Текущий shipped профиль:

- `code_risk`

Текущий profile для UI review:

- `ui_flow_risk`

Текущий profile для business invariants:

- `business_invariant_risk`

Подробно:

- `docs/architecture.md`
- `docs/roadmap.md`
- `docs/workspaces.md`

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

- Полноценным coverage-first профилем остаётся `code_risk`.
- `ui_flow_risk` сейчас shipped как discovery + declared smoke слой: он умеет определить UI surface, подсветить changed journeys и опционально запустить repo-owned smoke-команду из `./.riskmap-ui.toml`.
- Для workspace/monorepo сейчас нужно запускать анализ из package root, который владеет измененным приложением. Например: `shop-frontend`, а не внешний workspace-контейнер. Подробно: `docs/workspaces.md`.
- `business_invariant_risk` сейчас shipped как узкий deterministic слой: без явного `.riskmap.yml` он `not_applicable`, при наличии `.riskmap.yml` / `.riskmap.yaml` он `partial`; сейчас он умеет только PR-сигнал `business_critical_flow_changed_without_check_delta` для declared `critical_flows`, полная проверка бизнес-логики пока не реализована.
- Инструмент не является generic multi-language SAST.
- API имеет базовые сервисные защиты (token auth, rate/payload guardrails, audit/correlation controls).
- Без явных инвариантов репозитория инструмент не является проверкой бизнес-логики.

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
- Архитектурное решение: `docs/architecture.md`
- Roadmap: `docs/roadmap.md`
- Workspace/monorepo usage: `docs/workspaces.md`
- UI flow pilot log: `docs/ui-flow-pilots.md`
- Business invariants: `docs/business-invariants.md`
- Legacy review: `docs/legacy-review.md`
- Совместимость контрактов: `docs/compatibility.md`
- Совместимые legacy surfaces: `docs/capability-signals.md`, `docs/ingress-contract.md`, `docs/plugin-contract.md`
