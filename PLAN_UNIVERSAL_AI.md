# Universal AI-First Strategy Plan

Status note (as of 2026-03-10): the shared core and plugin model are now live for `fastapi_pytest`, `django_drf`, and `express_node`. This document remains the target direction for broader universal analysis, but parts of the foundation are already implemented.

## 1. Product Hypothesis

Гипотеза: масштабирование через stack-specific экстракторы неэффективно. Нужен universal AI-подход, где LLM приводит любой код к единому абстрактному представлению (IR/Graph), а risk-анализ выполняется на этом слое.

Ограничение: чистый LLM без валидации будет шумным. Рабочая модель — AI extraction + deterministic verification + graph rules.

## 2. Target Business Outcomes

1. Сократить стоимость production-багов через раннее обнаружение рисков на PR.
2. Сократить время triage и review за счет приоритизированных actionable finding'ов.
3. Снизить зависимость качества от конкретного стека/фреймворка.
4. Дать управляемый CI rollout: advisory -> soft -> block-new-critical.

## 3. North-Star and KPI

1. `Actioned Findings Rate >= 40%` (finding приводит к fix/suppression с reason).
2. `Precision@5 >= 75%` в PR-summary.
3. `PR fallback-to-full <= 15%`.
4. `Median time-to-triage <= 10 min`.
5. `Evidence completeness >= 95%` (finding с валидными evidence_refs).

## 4. AI-First Architecture

### 4.1 Ingestion Layer

Собирает репозиторий, PR-diff, manifests, routes, тесты, зависимости.

### 4.2 Normalization Layer

Приводит источники к унифицированному IR:

- Nodes: `Entity`, `State`, `Transition`, `Endpoint`, `Operation`, `Event`, `ExternalSystem`, `TestCase`
- Edges: `calls`, `reads`, `writes`, `transitions_to`, `emits`, `consumes`, `validated_by`, `covered_by`

### 4.3 AI Extraction Layer

LLM извлекает факты строго в JSON schema:

- обязательно: `source_ref`, `evidence_refs`, `confidence`, `origin`
- без `evidence_refs` факт отбрасывается

### 4.4 Verification Layer (Deterministic)

Проверяет:

- schema validity
- evidence existence (файл/строка реально существуют)
- consistency между узлами/рёбрами
- cross-check с deterministic anchors (routes/tests/transitions)

### 4.5 Graph & Risk Layer

- Строит unified graph
- Запускает deterministic risk rules
- AI используется для semantic enrichment, но не для "истины"

### 4.6 PR Intelligence Layer

- baseline diff: `new/resolved/unchanged`
- fingerprint stability across line shifts
- output only-new mode для PR-комментариев

## 5. Trust and Safety Model

1. Любой finding без evidence -> drop.
2. Blocking-решения принимаются только для `new + high_confidence`.
3. Все risky решения explainable: `why`, `evidence_refs`, `recommended action`.
4. LLM degradation не ломает run: fallback в deterministic mode.

## 6. Support Levels by Stack

Вместо "поддерживаем всё одинаково":

1. `L0 Generic`: базовый AI extraction + advisory only.
2. `L1 Verified`: есть deterministic anchors, можно soft-block.
3. `L2 Strict`: зрелая валидация, разрешен block-new-critical.

Каждый run должен явно показывать уровень поддержки.

## 7. Rollout Plan

### Phase A — Foundation (2-3 weeks)

1. Финализировать IR schema.
2. Ввести evidence discipline (`evidence_refs` required).
3. Внедрить run metrics и quality dashboard.

Exit criteria:

- schema coverage > 90%
- evidence completeness > 95%

### Phase B — Universal Extraction (3-4 weeks)

1. Включить AI extraction для polyglot входа.
2. Добавить deterministic verification и confidence gating.
3. Запустить на mixed-stack design partners.

Exit criteria:

- PR precision@5 >= 65%
- стабильный fallback behavior

### Phase C — Risk Quality (3-4 weeks)

1. Расширить graph rules для transitions/auth/test coverage/coupling.
2. Ввести baseline diff и only-new summaries.
3. Включить ci_mode rollout.

Exit criteria:

- precision@5 >= 75%
- actioned findings >= 40%

### Phase D — Scale and Governance (ongoing)

1. Feedback loop по suppressions и false positives.
2. Автоматическая калибровка confidence thresholds.
3. Регулярный eval-suite на реальных OSS/private репозиториях.

## 8. Operating Model for AI Implementation

Чтобы AI-агенты реализовывали быстро и без неоднозначности:

1. 1 task packet = 1 PR.
2. Каждый packet содержит:
   - exact files
   - contract changes
   - test cases
   - acceptance checks
3. Нет packet без measurable KPI impact.
4. Любое решение, не описанное в packet, считается отклонением.

## 9. Risks and Mitigations

1. Риск: hallucinated relations.
   Митигация: strict schema + evidence verification + drop policy.
2. Риск: high FP on unknown stacks.
   Митигация: support levels + advisory-only default.
3. Риск: performance/cost blow-up.
   Митигация: incremental PR analysis + chunking + caching by file hash.
4. Риск: loss of trust by dev teams.
   Митигация: explainability-first output + suppression hygiene + KPI transparency.

## 10. Definition of Done

Подход считается внедренным, когда:

1. Один pipeline стабильно анализирует mixed-stack репозитории.
2. Все findings имеют traceable evidence.
3. CI rollout работает по режимам without regressions.
4. KPI держатся 4 недели подряд на production-like выборке.
5. Команды используют tool для решений, а не только для отчётности.

---

Owner: @andry
Status: Draft for iteration
