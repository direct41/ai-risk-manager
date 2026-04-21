# Product Hunt Launch Kit

Use this page when preparing a Product Hunt or similar community launch.

## Positioning

Product name:

```text
AI Risk Manager
```

Tagline:

```text
Know what to test before merging AI-generated PRs
```

Short description:

```text
AI Risk Manager is a PR-native release-risk assistant for engineering and QA teams. It scans a repository or PR branch, highlights risky changed areas, and writes a short test-first triage package before merge.
```

Best launch category:

```text
Open-source developer tool / QA automation / AI code review workflow
```

## Audience

Lead with these users:

- engineering leads reviewing fast-moving PRs
- QA leads deciding what to test first
- teams adopting AI-generated code
- backend teams using FastAPI, Django/DRF, or Express/Node

Avoid broad claims such as:

- "replaces QA"
- "approves releases automatically"
- "SAST replacement"
- "finds every business-logic bug"

## Gallery Storyboard

Recommended Product Hunt gallery:

1. Product card: name, tagline, and "test-first PR risk review".
2. Terminal: install and run `riskmap analyze --sample`.
3. Report: `merge_triage.md` with decision and risk score.
4. PR comment: top risks and test-first actions.
5. Scope: best-fit stacks and current alpha limits.

Keep each image focused on one idea. Do not screenshot the full README.

## Maker Comment

```text
Hey Product Hunt,

I built AI Risk Manager because teams are merging more AI-generated code, but review bottlenecks are shifting from "can it compile?" to "what should we test before this ships?"

AI Risk Manager is a PR-native release-risk assistant. It looks at changed code, test coverage signals, workflows, contracts, dependencies, and critical paths, then writes a short triage package:

- top risky changed areas
- test-first actions
- merge decision: ready, review_required, or block_recommended
- machine-readable artifacts for CI

It is an open alpha. It works best today on backend-heavy FastAPI, Django/DRF, and Express/Node repos. It is not a SAST replacement and not a full business-logic verifier.

I am looking for feedback from engineers, QA leads, and CTOs reviewing fast-moving or AI-generated PRs:

1. Were the top findings useful?
2. What was noisy?
3. What important release risk did it miss?

The repo has a 60-second sample run in the README. Thanks for taking a look.
```

## Launch Day Checklist

Before launch:

- create a GitHub release tag
- confirm README quickstart works from a clean environment
- confirm `riskmap analyze --sample` produces `merge_triage.md`
- prepare 3-5 focused gallery images
- prepare one short demo GIF or video
- open 2-3 real alpha feedback issues or examples if available

On launch day:

- ask people to try it and comment, not to upvote
- reply quickly to setup problems
- direct detailed feedback to the alpha feedback issue template
- pin a short example command in comments or social posts

After launch:

- collect repeated setup blockers
- label false positives and missed risks
- update README only for issues that blocked multiple users
