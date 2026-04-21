# AI Risk Manager: быстрый вход

AI Risk Manager помогает перед merge понять, **что тестировать первым**.

Это CLI-инструмент для release-risk review. Он анализирует репозиторий или PR-ветку, находит рискованные зоны изменений и пишет короткий triage-отчет.

## Попробовать за 1 минуту

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "git+https://github.com/direct41/ai-risk-manager.git"

riskmap analyze --sample --no-llm --analysis-engine deterministic --output-dir ./.riskmap
cat .riskmap/merge_triage.md
cat .riskmap/report.md
```

Вы должны увидеть:

- решение: `ready`, `review_required` или `block_recommended`;
- верхние рискованные места;
- какие тесты или проверки сделать первыми.

## Запустить на своем репозитории

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap
```

Сначала откройте:

```bash
cat .riskmap/merge_triage.md
cat .riskmap/report.md
```

## Запустить на PR-ветке

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --analysis-engine deterministic \
  --no-llm \
  --only-new \
  --output-dir ./.riskmap
```

Для более точного PR-delta создайте baseline на `main`:

```bash
riskmap analyze \
  --mode full \
  --analysis-engine deterministic \
  --no-llm \
  --output-dir ./.riskmap/baseline
```

Потом в feature-ветке:

```bash
riskmap analyze \
  --mode pr \
  --base main \
  --baseline-graph ./.riskmap/baseline/graph.json \
  --only-new \
  --output-dir ./.riskmap
```

Baseline должен содержать `.riskmap/baseline/graph.json` и `.riskmap/baseline/findings.json`.

## Кому подходит сейчас

Лучше всего подходит:

- backend-heavy FastAPI, Django/DRF и Express/Node репозиториям;
- командам, которые ревьюят AI-generated PRs;
- QA leads и engineers, которым нужен test-first список перед merge;
- advisory CI checks до включения blocking gates.

Пока не подходит как:

- generic SAST replacement;
- полная проверка бизнес-логики без `.riskmap.yml`;
- screenshot diff / cross-browser UI test runner;
- автоматическое release approval без human review.

## Что смотреть в output

- `.riskmap/merge_triage.md` - короткое решение по merge и test-first порядок.
- `.riskmap/report.md` - подробнее: findings, reasons, actions.
- `.riskmap/findings.json` - машинный формат.
- `.riskmap/test_plan.json` - приоритизированные тестовые действия.

## Альфа-фидбек

Проект в limited open alpha. Самый полезный фидбек:

- стек и форма репозитория;
- команда, которую запускали;
- top 3 findings;
- что было полезно или шумно;
- какой важный риск инструмент пропустил;
- где setup или wording были непонятны.

Шаблон для фидбека:

```text
https://github.com/direct41/ai-risk-manager/issues/new?template=alpha_feedback.yml
```

## Где смотреть дальше

- `README.md` - основной quickstart на английском.
- `docs/workspaces.md` - workspace/monorepo usage.
- `docs/business-invariants.md` - `.riskmap.yml` critical-flow checks.
- `docs/deployment-hardening.md` - API deployment hardening.
- `docs/compatibility.md` - политика совместимости CLI/API/artifacts.
