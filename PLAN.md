# AI Risk Manager — Working Plan

Этот файл — живой инженерный план проекта. Мы будем улучшать его итеративно.

## 1) Vision

Сделать open-source инструмент, который помогает командам с незрелой QA-культурой:
- строит карту сущностей, состояний, переходов и зависимостей в продукте;
- выявляет слабые места и риски (пропуски в логике, неявные связи, недостающие тесты);
- дает приоритизированные рекомендации по тестированию и качеству;
- умеет анализировать как текущее состояние репозитория, так и PR/MR-изменения.

## 2) MVP Decisions (locked)

Чтобы убрать блокеры и ускорить запуск, для MVP фиксируем:
- первый целевой стек: `Python + FastAPI`;
- первая CI-платформа: `GitHub Actions` (GitLab после MVP);
- режим CI в MVP: `non-blocking` (только report/comment, без fail build);
- терминология: компонент построения графа везде называется `GraphBuilder`;
- архитектура взаимодействия агентов: только JSON-контракты, без agent-to-agent чата;
- core запускается единым пайплайном (`run_pipeline`) с transport adapters: `CLI` и sync `HTTP API`;
- extractor слой плагинный (статический registry), без dynamic plugin loading в MVP.

## 3) MVP Scope (без overengineering)

В MVP делаем только необходимый минимум:
- CLI-инструмент для локального запуска и CI;
- sync HTTP API adapter (`/v1/analyze`) поверх того же pipeline;
- анализ full-repo и PR diff;
- 3 последовательных агента с фиксированными JSON-контрактами;
- Markdown + JSON отчеты;
- интеграция через GitHub Action.
- режим `--no-llm` (deterministic-only: Collector -> GraphBuilder -> Rule Engine -> Report).
- выбор LLM backend: `api` или `cli` (локально), с единым контрактом входов/выходов.

Не делаем в MVP:
- микросервисную архитектуру;
- message broker/event bus;
- отдельный веб-интерфейс;
- multi-language поддержку.

## 4) Proposed Architecture (MVP)

Pipeline:
0. Stack Discovery
1. Collector
2. GraphBuilder
3. Rule Engine
4. Risk Agent (LLM)
5. QA Strategy Agent (LLM)
6. Report Generator

### 4.1 Components

- Collector
  - Выбор extractor plugin выполняется после `Stack Discovery`.
  - Вход: путь к репозиторию, режим (`full` | `pr`), diff.
  - Шаг `pre-flight check`: проверяем, что репозиторий соответствует допущениям MVP (FastAPI/pytest/routers), статус `PASS|WARN|FAIL`.
  - При `FAIL`: анализ пропускается с exit code `2` (unsupported project), с явным сообщением причины.
  - Выход: нормализованные артефакты только для целевого стека (FastAPI/Pydantic/pytest/миграции) + warning при частичном несоответствии допущениям.

- GraphBuilder
  - Строит единый граф доменных, инфраструктурных и QA-связей.
  - Формат: `graph.json`.

- Rule Engine (deterministic)
  - Запускает явные правила на графе.
  - Формат: `findings.raw.json`.

- Risk Agent
  - Интерпретирует findings и формирует риск-объяснения.
  - Формат: `findings.json`.

- QA Strategy Agent
  - Преобразует риски в тест-стратегию (что покрывать и в каком приоритете).
  - Формат: `test_plan.json`.

- Report Generator
  - Собирает человеко-читаемый отчет и машинные артефакты.
  - Добавляет `Data Quality` (доля low-confidence связей) и `analysis_scope` (`impacted` или `full_fallback`).
  - Форматы: `report.md`, `findings.json`, `test_plan.json`.

### 4.2 CLI and Output Contract (MVP)

Команды:
- `riskmap analyze [PATH]` (по умолчанию `PATH="."`, режим `full`)
- `riskmap analyze --mode pr --base main [PATH]`
- `riskmap analyze --no-llm [PATH]`
- `riskmap analyze --provider auto|api|cli [PATH]`
- `riskmap analyze --output-dir ./.riskmap [PATH]`

Output:
- директория по умолчанию: `.riskmap/`
- артефакты: `.riskmap/report.md`, `.riskmap/findings.json`, `.riskmap/test_plan.json`, `.riskmap/graph.json`, `.riskmap/findings.raw.json`
- рекомендуем добавить `.riskmap/` в `.gitignore`

LLM configuration:
- default backend: `auto`
- `auto` resolution:
  - local run: `cli -> api -> no-llm`
  - CI run: `api -> no-llm`
- `--provider api`: провайдер и ключ через environment variables (через LiteLLM-совместимые переменные)
- `--provider cli`: вызов установленного AI CLI-адаптера (локальный режим)
- если выбранный backend не сконфигурирован, пользователь получает явную подсказку использовать другой backend или `--no-llm`

### 4.3 API Contract (MVP, local/internal)

Endpoints:
- `GET /healthz` -> `{ \"status\": \"ok\", \"version\": \"...\" }`
- `POST /v1/analyze` (sync run)

`POST /v1/analyze` request fields:
- `path`, `mode`, `base`, `no_llm`, `provider`, `baseline_graph`, `output_dir`, `format`, `fail_on_severity`, `suppress_file`, `sample`

`POST /v1/analyze` response fields:
- `exit_code`
- `notes`
- `output_dir`
- `artifacts`
- `result` (`null` when `exit_code` is `1` or `2`)

Границы MVP:
- без auth/multi-tenant/rate-limits;
- один процесс, sync execution;
- API только adapter, без отдельной бизнес-логики.

## 5) Contracts (обязательно)

LLM-агенты общаются только через JSON-файлы, без свободного "чата".

RiskAgent:
- input: `findings.raw.json` + релевантный subgraph из `graph.json` + `source_ref`
- output: `findings.json`

QAStrategyAgent:
- input: `findings.json` + `TestCase`-ноды и `covered_by` связи из `graph.json`
- output: `test_plan.json`

Pipeline outputs:
- GraphBuilder -> `graph.json`
- Rule Engine -> `findings.raw.json`

Плюсы:
- воспроизводимость;
- тестируемость;
- меньше флейков и prompt-drift.

## 6) De-risking Strategy: Collector + GraphBuilder

Главный риск MVP — извлечение корректных связей из кода. Поэтому начинаем с узкого vertical slice.

### 6.1 Vertical Slice v1 (P0)

В первой итерации поддерживаем только:
- FastAPI endpoints (`@router.get/post/...`);
- Pydantic request/response models;
- явные domain states из `Enum` и проверок статусов;
- pytest-тесты, связанные с endpoint/service.

Не пытаемся сразу полноценно покрывать:
- произвольный plain Python;
- сложную динамику через reflection/metaprogramming;
- все варианты ORM и внешних интеграций.

### 6.2 GraphBuilder Strategy (MVP)

Используем гибридный, но простой подход:
- deterministic extraction по паттернам/конвенциям (основной путь);
- ограниченное LLM-assisted обогащение только для неоднозначных связей;
- каждая извлеченная связь содержит `confidence` (`high|medium|low`) и `evidence`.

## 7) Minimal Data Model

### 7.1 Node schema

Каждая нода содержит:
- `id`, `type`, `name`;
- `layer`: `domain | infrastructure | qa`;
- `source_ref` (файл/строка);
- `confidence`.

### 7.2 Node types
- `Entity`
- `State`
- `Transition`
- `API`
- `DBTable`
- `ExternalSystem`
- `TestCase`

### 7.3 Edge types
- `reads`
- `writes`
- `transitions_to`
- `triggers`
- `validated_by`
- `covered_by`

### 7.4 Edge schema

Каждое ребро содержит:
- `id`
- `source_node_id`
- `target_node_id`
- `type`
- `source_ref` (файл/строка)
- `evidence`
- `confidence`

## 8) Initial Risk Rules

Определение `critical path` в MVP:
- любой путь, содержащий `API` с write-операцией (`POST|PUT|PATCH|DELETE`) или `Transition`.

Каждое срабатывание правила содержит:
- `severity`: `critical | high | medium | low`;
- `confidence`;
- `evidence`;
- `suppression_key`.
- `recommendation` (конкретное действие для инженера).

Стартовый набор правил:
1. `orphan_entity`
- Сущность не участвует в критических сценариях.

2. `missing_transition_handler`
- Переход состояния заявлен, но обработка отсутствует.

3. `implicit_coupling`
- Неявная межмодульная зависимость.

4. `unprotected_transition`
- Переход без валидации/авторизации/инвариантов.

5. `critical_path_no_tests`
- Критичный путь без тестового покрытия.

Suppress в MVP:
- файл `.airiskignore` с `suppression_key` и короткой причиной.
- минимальный формат:
  - `key: "<suppression_key>"`, `reason: "<text>"`
  - или `rule: "<rule_id>"`, `file: "<path>"`, `reason: "<text>"`
- формат файла: YAML (`.airiskignore`).

## 9) LLM Reliability and Token Budget

Для MVP фиксируем простую стратегию:
- строгая валидация JSON-ответов по схемам;
- retry до 2 раз при невалидном ответе;
- при повторном сбое: graceful degradation (частичный результат + `confidence=low`);
- chunking: единица чанка = модуль (верхнеуровневая директория), если модуль > 80K токенов, дробим по файлам;
- в PR-режиме в LLM передается только impacted subgraph, не весь репозиторий.
- если запущено без LLM (`--no-llm`), `findings.json` и `test_plan.json` формируются в deterministic-режиме с пометкой `generated_without_llm=true`.
- backend `api|cli` не меняет контракты агентов и формат артефактов.
- для `cli` backend: при невалидном stdout после 2 retry делаем fallback по цепочке `auto` (или предлагаем `--provider api` / `--no-llm`).

## 10) PR Analysis and Baseline Cache

- baseline `graph.json` для `main` храним как CI artifact последнего merge/run.
- если baseline отсутствует или устарел, выполняем full rebuild.
- impacted subgraph строим из changed files + ближайших зависимостей.
- fallback: если затронута слишком большая часть графа, запускаем full rules scan.
- публикуем:
  - короткий summary в комментарий PR;
  - полный отчет как CI artifact.
- формат комментария: один upsert-комментарий с маркером `<!-- ai-risk-manager -->`, top-5 findings (severity, source_ref, next action), ссылка на artifact.
- для fork PR по умолчанию используем `--no-llm` (без секретов).
- в CI для стабильности используем только `--provider api` или `--no-llm`; `--provider cli` только для локального режима.

## 11) Assumptions (MVP)

- анализируемый репозиторий использует FastAPI и pytest;
- маршруты/API объявлены через стандартные паттерны FastAPI;
- хотя бы часть доменной логики выражена явно (enum/status checks);
- проект можно анализировать статически без выполнения кода;
- пользователи готовы сначала получать рекомендации, а не CI-блокировки.

## 12) Tech Stack (current)

- Python 3.12
- `argparse` (CLI)
- `dataclasses` + JSON (схемы/контракты)
- `ast` (парсинг Python)
- `urllib` + `subprocess` (LLM runtime transport)
- GitHub Actions

## 13) Repository Layout (proposed)

```text
ai-risk-manager/
  PLAN.md
  README.md
  pyproject.toml
  src/ai_risk_manager/
    cli.py
    api/
    pipeline/
    collectors/
      plugins/
    graph/
    rules/
    agents/
    reports/
    schemas/
    stacks/
  tests/
  eval/
    repos/
  .github/workflows/
    risk-analysis.yml
```

## 14) Implementation Milestones

### Milestone 0 — Decisions + Contracts (completed)
- Зафиксировать стек (`Python + FastAPI`) и границы MVP.
- Утвердить JSON-схемы `graph/findings/test_plan`.
- Добавить `.airiskignore` формат.
- Зафиксировать CLI API, output-dir и exit codes.
- Зафиксировать LLM backend selection (`auto|api|cli`) и fallback-поведение.
- Зафиксировать `provider=auto` (локально `cli -> api -> no-llm`, в CI `api -> no-llm`).

### Milestone 1 — Skeleton (completed)
- CLI-команда `riskmap analyze`.
- Пустой pipeline с user-facing прогрессом этапов (`[1/6] ... done (Xs)`).
- Базовые тесты на схемы.
- Прототип extraction: найти FastAPI write-endpoints (`@router.post/put/patch/delete`).
- Создать 1 минимальный eval-репозиторий с заранее известным риском.

### Milestone 2 — Vertical Slice (Collector + GraphBuilder + Rules) (completed)
- Реализовать FastAPI/Pydantic/pytest extraction.
- Построить граф для vertical slice.
- Реализовать минимум 2 правила end-to-end.
- Валидировать результат на eval-репозитории из Milestone 1.

### Milestone 3 — LLM Agents (completed)
- RiskAgent и QAStrategyAgent на стабильных контрактах.
- Retry/validation/degrade flow.
- Реализован runtime для `api|cli` провайдеров с JSON extraction и retry.
- Добавлены unit-тесты на runtime/agents.

### Milestone 4 — CI + PR Mode (completed)
- GitHub Action для PR.
- Baseline cache для `main`.
- Комментарий summary (top-5 findings: severity, source_ref, next action) + upload artifacts.
- Реализован реальный impacted subgraph filtering для PR режима.
- Добавлен upsert PR-comment с маркером `<!-- ai-risk-manager -->`.

### Milestone 5 — Evaluation Expansion (post-MVP hardening) (completed)
- Расширен набор до 3 эталонных репозиториев с заранее известными рисками.
- Добавлен `scripts/run_eval_suite.py` для прогонов и проверки ожидаемых правил.
- Добавлен регулярный CI прогон (`.github/workflows/eval-suite.yml`) по расписанию и вручную.

### Milestone 6 — Core + Plugin + API Adapter (completed)
- FastAPI extraction перенесен в `collectors/plugins/fastapi.py`.
- Добавлены `CollectorPlugin` protocol и статический registry плагинов.
- Добавлен `Stack Discovery` слой с выбором extractor plugin.
- Добавлен sync HTTP API adapter (`/healthz`, `/v1/analyze`) поверх `run_pipeline`.
- Сохранена совместимость CLI/exit codes/JSON artifacts (additive changes only).

## 15) Definition of Done (для MVP)

MVP готов, если:
- запускается локально одной командой;
- поддерживает запуск через CLI и через sync API adapter;
- анализирует full repo и PR diff;
- стабильно выдает `report.md`, `findings.json`, `test_plan.json`;
- в CI публикует summary в PR без блокировки пайплайна;
- поддерживает suppress через `.airiskignore`;
- проходит базовый eval-прогон на эталонных репозиториях.

## 16) Open Questions (non-blocking)

1. Как расширять extractor после FastAPI: Django или TypeScript?
2. Когда включать optional CI-fail режим (после каких метрик качества)?
3. Нужен ли UI после MVP или достаточно CLI + PR comments?

## 17) Next Iteration Backlog

- [ ] Добавить в `.airiskignore` опциональное поле `expires_at` и отчет по активным/истекшим suppressions.
- [ ] Добавить валидацию LLM-выхода: рекомендация без `finding_id/source_ref` отбрасывается.
- [ ] Ввести optional CI-fail mode по порогам severity после калибровки качества.
- [ ] Расширить extractor после FastAPI (Django или TypeScript по решению).
- [ ] Добавить второй extractor plugin после стабилизации FastAPI plugin (Django или Flask).
- [ ] Ввести hardening API режима при переходе от local/internal к service deployment (auth/rate limits).

---

Owner: @andry  
Status: Draft v0.7  
Last updated: 2026-02-19
