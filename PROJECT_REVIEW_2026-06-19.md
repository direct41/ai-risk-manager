# Полное ревью AI Risk Manager

Дата: 2026-06-19  
Commit: `4c5c71641049e28200756e5049f17b4d984d3b1b`  
Версия: `0.2.0`  
Ветка: `main`, рабочее дерево до ревью было чистым  
Режим: evidence-first, без изменений runtime-кода

## Итог

Решение для текущего open-alpha репозитория: **Conditional Go**. Продолжать ограниченную alpha-валидацию можно. Объявлять метрики доказательством общей точности, использовать API как multi-tenant service или считать release pipeline готовым к воспроизводимой публикации пока нельзя.

Решение для следующего публичного package/release: **No-Go до устранения P1-01, P1-02 и P1-03**.

Сильные стороны: чистая dependency direction без циклов, единый pipeline для CLI/API, строгие Pydantic/API contracts, безопасные defaults для LLM и публичного API, SHA-pinned GitHub Actions, высокий обычный coverage, полный корпус с label/head metadata, качественная документация ограничений.

Главный системный риск: тестовые и eval-метрики выглядят сильнее, чем фактическая независимая достоверность. Targeted mutation score составил только 56.5%, public corpus одновременно является tuning/regression dataset, а pinning PR head не гарантирует, что анализируется именно записанный SHA.

## Findings

### P1-01 — `review-pr` не закрепляет checkout на заявленный `head_sha`

- Доказательство: metadata получает `head_sha` в `cli.py:382-386`, но `prepare_github_pr_checkout` вызывается без него в `cli.py:401-408`. Checkout выполняется по mutable `refs/pull/<n>/head` в `integrations/github_pr_review.py:268-285`. Затем `review_pr_metadata.json` записывает ранее полученный API SHA в `cli.py:474-488`, не сверяя его с `git rev-parse HEAD`.
- Влияние: PR может измениться между API lookup и fetch. Анализ будет выполнен над одним commit, а benchmark provenance сообщит другой. Проверка `observed_head_sha` в benchmark доверяет metadata-файлу и не обнаружит race.
- Владелец: CLI/GitHub integration.
- Действие: fetch/checkout exact `metadata.head_sha`, затем сравнить `git rev-parse HEAD`; записывать фактически проверенный SHA. Несовпадение должно быть setup failure.

### P1-02 — scanner анализирует игнорируемые virtualenv и bundled samples

- Доказательство: exclusions сравнивают точные имена `.venv`/`venv` (`fastapi_artifacts.py:24-37`), но не `.venv-min`, `.venv-local` и другие стандартные варианты; traversal не учитывает `.gitignore` (`fastapi_artifacts.py:68-79`, аналогично Django/Express/universal collectors).
- Воспроизведение: self-scan commit `4c5c716` нашёл `.venv-min/lib/python3.13/site-packages/ai_risk_manager/...` и выдал дублированный finding. Он также выдал high finding из `src/ai_risk_manager/samples/milestone2_fastapi`, поэтому собственный репозиторий получил `review_required`, risk score `100`.
- Влияние: ложные findings, неверные risk score/decision, лишние CPU/RAM, анализ vendored/generated code вместо проекта.
- Владелец: collectors/profile discovery.
- Действие: единый walker с git-aware excludes, glob-паттернами virtualenv/build/cache/vendor и явным include/exclude contract. Добавить regression test с `.venv-min` и bundled sample.

### P1-03 — eval не является независимой оценкой точности

- Доказательство: expected rule IDs находятся рядом с синтетическими fixtures в `scripts/run_eval_suite.py`; precision/recall proxy вычисляются только как наличие forbidden/required rules (`scripts/run_eval_suite.py:795-804`). Validation history прямо описывает настройку правил по public cases. Все 49 public labels и expected outcomes находятся в том же tracked corpus, который служит regression contract.
- Влияние: 100% proxy нельзя интерпретировать как precision/recall на новых PR. Существует leakage между corpus labels и эвристиками. Чистого holdout и зафиксированного external consensus нет.
- Владелец: product/eval.
- Действие: разделить tuning/regression и frozen holdout; публиковать confusion matrix по независимой ручной разметке; запретить изменение holdout вместе с rules; хранить judge provenance и inter-rater agreement.

### P1-04 — policy/trust/triage недостаточно защищены поведенческими тестами

- Доказательство: targeted `mutmut 3.6.0` по `rules/policy.py`, `trust/scoring.py`, `triage/merge.py`, `pr_scope.py`: 875 mutants, 494 killed, 381 survived; mutation score 56.5%.
- Влияние: line coverage 88.34% не фиксирует веса scoring, decision boundaries, malformed policy behavior и budget/ranking semantics. Незаметное изменение числа или comparison может пройти suite и изменить public decision.
- Владелец: QA/core pipeline.
- Действие: добавить table-driven contract tests для всех decision transitions и policy combinations; тестировать точные trust/risk boundary values; затем установить mutation threshold сначала 75%, после стабилизации 85% для этих модулей.

### P2-01 — API допускает конкурентную порчу одного output directory

- Доказательство: request управляет `output_dir` (`api/server.py:550-592`), pipeline запускается без per-output lock, а artifacts последовательно перезаписываются (`pipeline/sinks.py:169-225`).
- Влияние: два одновременных анализа одного repo/output могут смешать `graph`, `findings`, markdown и audit; ответ одного запроса может ссылаться на artifacts другого.
- Владелец: API/runtime.
- Действие: server-generated run ID + isolated directory; atomic writes; reject/serialize explicit collisions. Добавить concurrent integration test.

### P2-02 — `estimated_precision` не является калиброванной precision

- Доказательство: `trust/scoring.py:91-106` складывает ручные веса confidence/support/evidence/history и копирует итоговый score в `estimated_precision`. Статистической калибровки или доверительного интервала нет.
- Влияние: machine contract выглядит как измеренная вероятность и может быть неверно использован downstream.
- Владелец: trust/product contracts.
- Действие: переименовать в `heuristic_trust_score` либо калибровать на frozen holdout и документировать calibration error/version.

### P2-03 — release pipeline не проверяет публикуемые artifacts и provenance

- Доказательство: quality workflow устанавливает `pip install .`, но не строит и не устанавливает wheel/sdist (`.github/workflows/quality.yml:39-63`). Нет checked-in publish workflow, SBOM, attestations или reproducibility check. Локальный `uv build` успешен.
- Влияние: source checkout может быть green, а опубликованный artifact — неполным или отличаться. Нет supply-chain evidence.
- Владелец: release/devops.
- Действие: build wheel+sdist once, `twine check`, install/smoke each artifact, generate hashes/SBOM, publish via trusted OIDC with provenance.

### P2-04 — dependency vulnerability gate отсутствует

- Доказательство: CI имеет Dependabot и CodeQL, но quality workflow не запускает dependency audit. Локальный `pip-audit` нашёл 3 CVE в `pip 26.0.1`; fixed versions начинаются с 26.1/26.1.2. Это toolchain, не runtime dependency, но CI делает непинованный `pip install --upgrade pip`.
- Влияние: результат зависит от текущего индекса; уязвимый installer может использоваться в release job.
- Владелец: devops/release.
- Действие: pin/bootstrap installer безопасной версией, добавить audit gate для runtime и release toolchain отдельно.

### P2-05 — performance readiness не определена

- Доказательство: small sample — 0.09 s/~31 MB RSS; текущий repo — 8.95 s/~432 MB RSS; synthetic 5,381 files — 12.38 s/~561 MB RSS. Основное время уходит в stack detection и collectors. Документированных SLO/CI thresholds нет.
- Влияние: memory уже высока для medium repository; scanner noise из ignored trees ухудшает масштабирование и воспроизводимость.
- Владелец: collectors/performance.
- Действие: после P1-02 профилировать walker/parser, добавить benchmark fixtures по file count/bytes и regression gates по wall time/RSS.

### P2-06 — анонимность автора не обеспечена в Git history

- Доказательство: commit metadata содержит реальное имя `Andrey Harlamov` и личный email `directand@mail.ru`; публичные package metadata и LICENSE используют project-scoped attribution.
- Влияние: если цель — pseudonymous publication, существующая история уже деанонимизирует владельца. Public-artifact gate не сканирует Git metadata.
- Владелец: release/privacy.
- Действие: сначала принять явное решение, требуется ли анонимность. Если да — rotate email to noreply, переписать историю только с отдельным migration plan, заменить tags/releases и предупредить consumers. Если нет — документировать accepted risk.

### P2-07 — API audit записывает неверный default analysis engine

- Доказательство: request model default — `deterministic` (`api/models.py:35`), но audit fallback — `ai_first` (`api/server.py:366-372`) для payload без поля.
- Влияние: forensic/audit trail неверно описывает privacy-sensitive LLM behavior.
- Владелец: API.
- Действие: строить audit request view из validated model или синхронизировать defaults; добавить тест omitted-field audit.

### P3-01 — крупные modules увеличивают change risk, но не являются мёртвым кодом

- Доказательство: `express_artifacts.py` ~1,100 LOC, `scripts/run_eval_suite.py` ~1,250 LOC, `pipeline/run.py` ~900 LOC, `rules/engine.py` ~880 LOC. Import graph: 75 modules, 171 internal edges, 0 cycles. `vulture --min-confidence 80` не нашёл dead symbols.
- Влияние: сложнее локализовать изменения и mutation gaps, но массовое разбиение сейчас не оправдано.
- Владелец: architecture.
- Действие: только extraction по cohesive capabilities при следующем изменении; не делать standalone refactor.

### P3-02 — compatibility layer имеет реальных consumers

- Доказательство: `stacks.discovery`, plugin contract v1, repository support fields и profiles участвуют в pipeline, tests, docs и CI gates; import cycles отсутствуют.
- Решение: оставить. Удаление возможно только в major release с contract migration. Не считать этот слой dead code.

## Архитектурная карта

```text
CLI / API / GitHub PR
        |
        v
RunContext + preflight
        |
        v
profile registry -> code_risk / ui_flow_risk / business_invariant_risk
        |
        v
collectors/plugins -> ArtifactBundle -> CapabilitySignal bundle
        |
        v
graph + PR scope/diff signals
        |
        v
deterministic rules -> suppressions -> optional AI -> merge/policy/trust
        |
        v
test plan -> merge triage -> report/JSON/GitHub artifacts
```

Границы в целом честные: CLI/API нормализуют вход в `RunContext`, GitHub и LLM находятся в integrations/agents, core не импортирует FastAPI/Pydantic vendor types. Главные протечки — filesystem traversal policy и shared mutable output directory.

## Контрактная матрица

| Обещание | Реализация | Тест/доказательство | Статус |
|---|---|---|---|
| Deterministic/no-LLM default | CLI/API defaults + provider resolution | API/pipeline tests, smoke | Pass |
| `ready/review_required/block_recommended` | `triage/merge.py` | unit/eval; mutation weak | Conditional |
| FastAPI/Django/Express strongest support | plugins + support matrix | synthetic eval + public corpus | Conditional; no holdout |
| Public PR pinned provenance | corpus head SHA + metadata | corpus strict gate | Fail: checkout not pinned |
| API path containment | resolved workspace/output roots | API negative tests | Pass |
| Optional command execution only for trusted repos | env gate + argv subprocess | UI smoke tests | Pass with documented trust assumption |
| Wheel/sample usability | package data + entrypoints | local build/smoke | Pass locally; absent artifact CI |
| Open-source hygiene | MIT, public gate, docs allowlist | gate passes | Pass, except Git anonymity if required |

## Threat model summary

Assets: repository source, GitHub/LLM tokens, artifact integrity, PR decision integrity, audit logs, runner CPU/RAM.  
Trust boundaries: HTTP API, local repo filesystem, GitHub API/git transport, optional LLM endpoint/CLI, repo-owned UI smoke manifest, CI PR code, artifact publication.

| Threat | Existing control | Residual risk |
|---|---|---|
| Arbitrary host path read/write through API | resolved roots; public host requires roots/token | symlink/TOCTOU and output collision need operational containment |
| Untrusted command execution | off by default; explicit env opt-in; argv no shell | trusted-repo assumption is mandatory |
| Token/code exfiltration to LLM | deterministic default; explicit provider | custom API base is trusted configuration; no DLP |
| Malicious PR code execution | analysis is static by default; smoke disabled | future command-enabled CI must never run untrusted forks |
| Benchmark provenance spoof/race | recorded head SHA | actual checkout SHA not verified (P1-01) |
| Resource exhaustion | optional body/rate limits | filesystem size/concurrency limits absent |

## YAGNI / hygiene decisions

- **Удалить сейчас:** ничего. Доказанного runtime-dead tracked кода нет.
- **Упростить:** centralize walkers/excludes; isolate API run outputs; split eval dataset roles. Не создавать новый framework.
- **Оставить:** profile registry, plugin contract v1, stack discovery, signals/adapters, report variants — у них есть текущие consumers и compatibility obligations.
- **Исследовать:** необходимость одновременно `graph.json` и `graph.analysis.json`; судьбу `competitive_mode`/repository-wide compatibility fields в следующем major; ценность external judge без committed assessments.

## Baseline и воспроизводимость

| Проверка | Результат |
|---|---|
| Tracked files | 258; полный manifest рядом с отчётом |
| Классы | runtime 75, test 58, fixture 69, docs 25, example 13, CI 6, config/package 5, eval 4, scripts 3 |
| Pytest | 367 passed, 23.28 s |
| Coverage | 88.34% total |
| Ruff | pass |
| Mypy | pass, 75 source files |
| Build | wheel 161 KiB, sdist 137 KiB; both clean-installed and sample-smoked on Python 3.13 |
| Minimal deterministic smoke | pass |
| Synthetic eval gate | pass; 100% proxy metrics; 0 flaky |
| Corpus metadata gate | 49 labeled, 0 pending, 0 issues |
| Full public PR benchmark | 49/49 passed, 0 failed; 676.69 s wall time |
| Mutation | 494 killed / 381 survived / 875 total = 56.5% |
| Dependency compatibility | `uv pip check`: pass |
| Dependency audit | 3 pip toolchain CVEs; runtime libraries clean in current environment |
| Import graph | 75 modules, 171 edges, 0 cycles |
| Dead-code static scan | no findings at vulture confidence >=80 |
| Remote CI on reviewed SHA | Quality, AI Risk Analysis, CodeQL: success |
| Open issues/PRs | 1 open alpha-feedback issue, 0 open PRs |

Не выполнено как release evidence: clean artifact install на Linux, reproducible build hash comparison, full OS matrix outside GitHub evidence, long soak/concurrency API test, external-judge consensus, formal legal review.

## Приоритетный план небольших задач

1. Pin and verify actual PR head SHA; add race/provenance test.
2. Introduce one shared git-aware filesystem walker and exclude regression suite.
3. Split eval into tuning/regression/holdout and correct metric naming.
4. Add mutation contract tests for decision/policy/trust boundaries.
5. Isolate API output per run and test concurrency.
6. Build/test release artifacts in CI; add audit/SBOM/provenance.
7. Define performance SLO after traversal fix.
8. Resolve anonymity policy explicitly.

## Compliance & Anonymity Release Note

- License/attribution: MIT, project-scoped `AI Risk Manager contributors`.
- Third-party licenses: reviewed installed environment; permissive licenses plus MPL-licensed CA bundle; no incompatible runtime copyleft identified. Formal legal advice not performed.
- External services: GitHub API/git and optional configured LLM/judge providers; repository snippets leave the machine only when AI is explicitly enabled.
- Data collection: local artifacts and optional audit log; project does not define a hosted retention/deletion policy because no hosted service is shipped.
- Anonymity audit: package/docs pass project-scoped attribution; Git history fails pseudonymous threshold due real name/personal email.
- Recommendation: Conditional for existing public alpha; Block a claim of anonymous publication until identity exposure is explicitly accepted or remediated.

## Decision

**Conditional Go for open alpha. No-Go for a stronger accuracy/release-readiness claim.**

Top 3 actions: enforce exact PR SHA, exclude non-project trees, establish a frozen independent holdout with mutation-backed decision contracts.
