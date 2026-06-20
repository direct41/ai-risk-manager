# Frozen Holdout Protocol

The project currently has tuning fixtures and a labeled regression corpus. It does not yet have an independent holdout, so general accuracy and calibrated precision claims remain blocked.

## Roles and separation

- Rule authors may use `eval/repos/` and `eval/public_prs.json` for development and regression.
- Holdout cases must come from previously unused public PRs selected without inspecting AI Risk Manager output.
- Case selection, prediction generation, and human labeling are separate phases with SHA-256-pinned artifacts.
- A change range may modify holdout artifacts or analyzer/tuning/regression code, but never both.

The machine-readable state is `eval/dataset_manifest.json`. CI runs `scripts/check_eval_isolation.py` to validate the state and detect mixed changes.

## State machine

1. `not_established`: no holdout files exist; release claims remain blocked.
2. `cases_frozen`: at least 30 case records are frozen under `eval/holdout/`. Records contain identity and provenance only—no expected result, rationale, or label.
3. `predictions_frozen`: predictions for every case are generated from one recorded commit and pinned before labels enter the repository.
4. `evaluated`: labels are bound to both frozen case and prediction hashes. At least two independent pseudonymous reviewers participate, with at least 10 cases double-reviewed.

Advancing a state requires updating paths and SHA-256 values in the dataset manifest. Hash drift fails CI.

Use `scripts/holdout_workflow.py` for state transitions. It writes new frozen artifacts without overwriting existing files and atomically updates the manifest:

```bash
python3 scripts/holdout_workflow.py freeze-cases \
  --input /secure/intake/holdout-candidates.json

python3 scripts/holdout_workflow.py freeze-predictions \
  --results-dir /secure/results \
  --source-commit "$(git rev-parse HEAD)"

python3 scripts/holdout_workflow.py create-label-template \
  --reviewer reviewer-a \
  --output /secure/reviewer-a-labels.json
```

Keep candidate intake, raw result directories, and incomplete reviewer templates outside the repository. Only frozen cases, frozen predictions, and completed combined labels belong under `eval/holdout/`.

## Case selection

Each case contains only:

- stable case ID;
- canonical public GitHub PR URL;
- exact 40-character head SHA;
- stack classification;
- selection date.

Do not include `expected`, `label`, outcome rationale, known analyzer misses, or rule IDs. Cases used in tuning, regression, documentation examples, or prior benchmark analysis are ineligible.

The candidate packet uses `dataset_role=holdout_candidates` and the same five case fields. The freeze command rejects any URL or head SHA already present in `eval/public_prs.json`.

## Blind prediction freeze

Run the selected analyzer commit against every case before importing human labels. Store one prediction row per case with decision, top rules, finding count, execution status, and artifact hash. Record the source commit and bind the file to the frozen cases hash.

If execution fails, retain the failure as a prediction outcome. Do not replace difficult cases after observing results.

Place successful outputs under `<results-dir>/<case-id>/` with `pr_summary.json`, `merge_triage.json`, and `findings.json`. For a failed execution, write only `execution.json` with one of `setup_fail`, `provider_fail`, `tool_fail`, `artifact_fail`, or `timeout`. The freeze command requires one result directory per frozen case and records a deterministic artifact hash.

## Independent labeling

Reviewers evaluate the PR diff and expected review action without seeing analyzer predictions. Use pseudonymous reviewer IDs. At least 10 cases receive labels from two reviewers so agreement can be reported; disagreements stay explicit and require adjudication rather than silent majority replacement.

Labels must not enter the repository before predictions are frozen. The label file is then bound to both the case and prediction hashes.

## Reporting

Report at minimum:

- holdout size and selection period;
- execution failure rate;
- decision confusion matrix;
- useful/noisy/missed-risk outcome counts;
- per-stack breakdown where sample size permits;
- raw and adjudicated inter-rater agreement;
- analyzer commit and all dataset hashes.

Do not merge holdout-driven rule changes into the same evaluation result. Once results are inspected by rule authors, that holdout version becomes regression data and a new independent holdout is required for the next generalization claim.
