from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "eval" / "results"


@dataclass
class EvalCase:
    name: str
    repo_rel: str
    required_rules: set[str]
    forbidden_rules: set[str]


CASES = [
    EvalCase(
        name="milestone2_fastapi",
        repo_rel="eval/repos/milestone2_fastapi",
        required_rules={"critical_path_no_tests", "missing_transition_handler"},
        forbidden_rules=set(),
    ),
    EvalCase(
        name="milestone5_balanced",
        repo_rel="eval/repos/milestone5_balanced",
        required_rules=set(),
        forbidden_rules={"critical_path_no_tests", "missing_transition_handler"},
    ),
    EvalCase(
        name="milestone5_missing_handler",
        repo_rel="eval/repos/milestone5_missing_handler",
        required_rules={"missing_transition_handler"},
        forbidden_rules={"critical_path_no_tests"},
    ),
]


def run_case(case: EvalCase) -> dict:
    repo_path = REPO_ROOT / case.repo_rel
    out_dir = OUTPUT_ROOT / case.name
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict = {
        "case": case.name,
        "repo": case.repo_rel,
        "exit_code": 0,
        "required_rules": sorted(case.required_rules),
        "forbidden_rules": sorted(case.forbidden_rules),
        "found_rules": [],
        "runs": [],
        "required_missed_count": 0,
        "forbidden_hit_count": 0,
        "precision_proxy": 1.0,
        "recall_proxy": 1.0,
        "flaky": False,
        "status": "failed",
        "errors": [],
    }

    try:
        run_count = int(os.getenv("AIRISK_EVAL_FLAKY_RUNS", "2"))
    except ValueError:
        run_count = 2
    if run_count < 1:
        run_count = 1

    rules_per_run: list[set[str]] = []
    for run_idx in range(run_count):
        cmd = [
            sys.executable,
            "-m",
            "ai_risk_manager.cli",
            "analyze",
            str(repo_path),
            "--mode",
            "full",
            "--no-llm",
            "--output-dir",
            str(out_dir),
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env={**os.environ.copy(), "PYTHONPATH": str(REPO_ROOT / "src")},
            capture_output=True,
            text=True,
        )
        result["runs"].append({"index": run_idx + 1, "exit_code": proc.returncode})
        if proc.returncode != 0:
            result["exit_code"] = proc.returncode
            result["errors"].append(f"analyze command failed on run {run_idx + 1} with exit code {proc.returncode}")
            result["errors"].append((proc.stderr or proc.stdout).strip())
            return result

        findings_file = out_dir / "findings.json"
        if not findings_file.exists():
            result["errors"].append(f"findings.json was not generated on run {run_idx + 1}")
            return result

        data = json.loads(findings_file.read_text(encoding="utf-8"))
        rules = {row["rule_id"] for row in data.get("findings", [])}
        rules_per_run.append(rules)

    if not rules_per_run:
        result["errors"].append("No eval runs were executed.")
        return result

    rules = rules_per_run[0]
    result["found_rules"] = sorted(rules)
    result["flaky"] = any(current != rules_per_run[0] for current in rules_per_run[1:])

    missing_required = case.required_rules - rules
    present_forbidden = case.forbidden_rules & rules
    result["required_missed_count"] = len(missing_required)
    result["forbidden_hit_count"] = len(present_forbidden)
    result["precision_proxy"] = 1.0 - (len(present_forbidden) / max(1, len(rules)))
    result["recall_proxy"] = 1.0 - (len(missing_required) / max(1, len(case.required_rules)))
    if missing_required:
        result["errors"].append(f"missing required rules: {sorted(missing_required)}")
    if present_forbidden:
        result["errors"].append(f"found forbidden rules: {sorted(present_forbidden)}")
    if result["flaky"]:
        result["errors"].append("flaky result: rule set differs across repeated runs")

    if not result["errors"]:
        result["status"] = "passed"

    return result


def write_summary(results: list[dict]) -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    avg_precision = mean(row.get("precision_proxy", 0.0) for row in results) if results else 0.0
    avg_recall = mean(row.get("recall_proxy", 0.0) for row in results) if results else 0.0
    lines = [
        "# Eval Suite Summary",
        "",
        f"- Avg precision proxy: `{avg_precision:.2%}`",
        f"- Avg recall proxy: `{avg_recall:.2%}`",
        f"- Flaky cases: `{sum(1 for row in results if row.get('flaky'))}`",
        "",
    ]
    failures = 0
    for row in results:
        if row["status"] != "passed":
            failures += 1
        lines.append(f"## {row['case']}")
        lines.append(f"- Status: `{row['status']}`")
        lines.append(f"- Exit code: `{row['exit_code']}`")
        lines.append(f"- Found rules: `{', '.join(row['found_rules']) or 'none'}`")
        lines.append(f"- Precision proxy: `{row.get('precision_proxy', 0.0):.2%}`")
        lines.append(f"- Recall proxy: `{row.get('recall_proxy', 0.0):.2%}`")
        lines.append(f"- Flaky: `{row.get('flaky', False)}`")
        if row["errors"]:
            lines.append("- Errors:")
            for err in row["errors"]:
                lines.append(f"  - {err}")
        lines.append("")

    (OUTPUT_ROOT / "summary.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return failures


def main() -> int:
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    results = [run_case(case) for case in CASES]
    failures = write_summary(results)

    print((OUTPUT_ROOT / "summary.md").read_text(encoding="utf-8"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
