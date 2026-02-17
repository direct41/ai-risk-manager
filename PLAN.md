# AI Risk Manager — Working Plan

Этот файл — живой инженерный план проекта. Мы будем улучшать его итеративно.

## 1) Vision

Сделать open-source инструмент, который помогает командам с незрелой QA-культурой:
- строит карту сущностей, состояний, переходов и зависимостей в продукте;
- выявляет слабые места и риски (пропуски в логике, неявные связи, недостающие тесты);
- дает приоритизированные рекомендации по тестированию и качеству;
- умеет анализировать как текущее состояние репозитория, так и PR/MR-изменения.

## 2) MVP Scope (без overengineering)

В MVP делаем только необходимый минимум:
- CLI-инструмент для локального запуска и CI;
- анализ монорепозитория/репозитория целиком;
- анализ PR/MR diff;
- 3 последовательных агента с фиксированными JSON-контрактами;
- Markdown + JSON отчеты;
- интеграция через GitHub Action (как первый target).

Не делаем в MVP:
- микросервисную архитектуру;
- message broker/event bus;
- отдельный веб-интерфейс;
- поддержку множества языков сразу.

## 3) Proposed Architecture (MVP)

Pipeline:
1. Collector
2. Graph Builder
3. Rule Engine
4. Risk Agent (LLM)
5. QA Strategy Agent (LLM)
6. Report Generator

### 3.1 Components

- Collector
  - Вход: путь к репозиторию, режим (`full` | `pr`), diff.
  - Выход: нормализованный набор артефактов (код, тесты, API-спеки, миграции, docs).

- Graph Builder
  - Строит единый граф доменных/технических связей.
  - Формат: `graph.json`.

- Rule Engine (deterministic)
  - Запускает набор явных правил на графе.
  - Формат: `findings.raw.json`.

- Risk Agent
  - Интерпретирует findings и формирует риск-объяснения.
  - Формат: `findings.json`.

- QA Strategy Agent
  - Преобразует риски в тест-стратегию (что покрывать и в каком приоритете).
  - Формат: `test_plan.json`.

- Report Generator
  - Собирает человеко-читаемый отчет и машинные артефакты.
  - Форматы: `report.md`, `findings.json`, `test_plan.json`.

## 4) Agent Contracts (обязательно)

Агенты общаются только через JSON-файлы, без свободного "чата".

- MapperAgent -> `graph.json`
- RiskAgent -> `findings.json`
- QAStrategyAgent -> `test_plan.json`

Плюсы:
- воспроизводимость;
- тестируемость;
- меньше флейков и prompt-drift.

## 5) Minimal Data Model

### 5.1 Node types
- `Entity`
- `State`
- `Transition`
- `API`
- `DBTable`
- `ExternalSystem`
- `TestCase`

### 5.2 Edge types
- `reads`
- `writes`
- `transitions_to`
- `triggers`
- `validated_by`
- `covered_by`

## 6) Initial Risk Rules

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

## 7) PR/MR Analysis (MVP)

- Берем baseline граф из `main` (или пересобираем при первом запуске).
- Строим impacted subgraph по diff.
- Гоняем правила только на затронутых участках.
- Публикуем:
  - короткий summary в комментарий PR;
  - полный отчет как CI artifact.

## 8) Tech Stack (draft)

- Python 3.12
- Typer (CLI)
- Pydantic (схемы)
- NetworkX (граф)
- Tree-sitter (парсинг)
- LiteLLM (адаптер к Codex/Claude)
- GitHub Actions

## 9) Repository Layout (proposed)

```text
ai-risk-manager/
  PLAN.md
  README.md
  pyproject.toml
  src/ai_risk_manager/
    cli.py
    pipeline/
    collectors/
    graph/
    rules/
    agents/
    reports/
    schemas/
  tests/
  .github/workflows/
    risk-analysis.yml
```

## 10) Implementation Milestones

### Milestone 1 — Skeleton
- CLI-команда `riskmap analyze`.
- Пустой pipeline с логированием этапов.
- JSON-схемы `graph/findings/test_plan`.

### Milestone 2 — Graph + Rules
- Базовый Graph Builder (1 язык, 1 экосистема).
- 5 deterministic rules.
- Генерация `findings.raw.json`.

### Milestone 3 — LLM Agents
- RiskAgent и QAStrategyAgent на стабильных контрактах.
- Контроль формата и валидация выходов.

### Milestone 4 — CI Integration
- GitHub Action для PR.
- Комментарий summary + upload artifacts.

## 11) Definition of Done (для MVP)

MVP готов, если:
- запускается локально одной командой;
- анализирует full repo и PR diff;
- стабильно выдает три артефакта (`report.md`, `findings.json`, `test_plan.json`);
- в CI публикует summary в PR;
- есть минимальные автотесты на схемы и rules.

## 12) Open Questions

1. Какой первый язык/стек поддерживаем в MVP (TypeScript или Python)?
2. Что считаем "critical path" по умолчанию?
3. Нужен ли fail CI по threshold рисков в MVP?
4. Нужна ли поддержка GitLab MR в MVP или после GitHub?

## 13) Next Iteration Backlog

- [ ] Зафиксировать язык MVP.
- [ ] Утвердить JSON-схемы для 3 контрактов.
- [ ] Создать скелет проекта и первую CLI-команду.
- [ ] Реализовать 1-2 правила end-to-end как vertical slice.
- [ ] Подключить GitHub Action на тестовом репозитории.

---

Owner: @andry  
Status: Draft v0.1  
Last updated: 2026-02-17
