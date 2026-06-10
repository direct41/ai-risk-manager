from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from ai_risk_manager.cli import main
from ai_risk_manager.public_pr_benchmark import (
    PublicPRBenchmarkOptions,
    PublicPRBenchmarkResult,
    PublicPRCaseResult,
    ReviewCommandResult,
    inspect_public_pr_corpus,
    load_public_pr_corpus,
    run_public_pr_benchmark,
)


def _write_corpus(path: Path, cases: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "cases": cases}), encoding="utf-8")


def _case(
    expected: dict | None = None,
    *,
    case_id: str = "express-7287",
    url: str = "https://github.com/expressjs/express/pull/7287",
    label: dict | None = None,
) -> dict:
    case = {
        "id": case_id,
        "url": url,
        "stack": "express_node",
        "reason": "regression corpus case",
        "expected": expected or {},
    }
    if label is not None:
        case["label"] = label
    return case


def _output_dir_from_command(command: list[str]) -> Path:
    return Path(command[command.index("--output-dir") + 1])


def _write_review_artifacts(
    output_dir: Path,
    *,
    decision: str = "review_required",
    rule_id: str = "pr_code_change_without_test_delta",
    source_ref: str = "lib/response.js",
    top_findings: list[dict] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    top_finding = {
        "rule_id": rule_id,
        "title": "PR changes code without any test delta",
        "severity": "medium",
        "confidence": "medium",
        "status": "new",
        "source_ref": source_ref,
        "recommendation": "Add a regression test.",
    }
    action = {
        "finding_id": f"{rule_id}:{source_ref}",
        "rule_id": rule_id,
        "title": "PR changes code without any test delta",
        "priority": "medium",
        "confidence": "medium",
        "status": "new",
        "source_ref": source_ref,
        "action": "Add a regression test.",
        "estimated_minutes": 3,
    }
    resolved_top_findings = top_findings or [top_finding]
    (output_dir / "pr_summary.json").write_text(
        json.dumps(
            {
                "decision": decision,
                "risk_score": 38,
                "top_findings": resolved_top_findings,
                "top_actions": [action],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "merge_triage.json").write_text(
        json.dumps({"decision": decision, "risk_score": 38, "actions": [action]}),
        encoding="utf-8",
    )
    (output_dir / "findings.json").write_text(json.dumps({"findings": resolved_top_findings}), encoding="utf-8")


def test_load_public_pr_corpus_reads_expected_fields(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "pass",
                    "product": "useful",
                    "decision": "review_required",
                    "required_rules": ["pr_code_change_without_test_delta"],
                    "required_paths": ["lib/response.js"],
                    "forbidden_top_rules": ["critical_path_no_tests"],
                    "max_top_findings": 1,
                },
                label={
                    "outcome": "good_signal",
                    "rationale": "The report found the expected changed-file risk.",
                    "reviewed_at": "2026-06-10",
                },
            )
        ],
    )

    cases = load_public_pr_corpus(corpus)

    assert cases[0].id == "express-7287"
    assert cases[0].expected.product == "useful"
    assert cases[0].expected.required_paths == ["lib/response.js"]
    assert cases[0].label is not None
    assert cases[0].label.outcome == "good_signal"


def test_inspect_public_pr_corpus_renders_labeling_queue(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {"product": "useful"},
                label={
                    "outcome": "good_signal",
                    "rationale": "The report found the expected risk.",
                    "reviewed_at": "2026-06-10",
                },
            ),
            _case(
                {"product": "needs_human_review"},
                case_id="express-7291",
                url="https://github.com/expressjs/express/pull/7291",
            ),
        ],
    )

    result = inspect_public_pr_corpus(corpus, tmp_path / "status")

    assert result.total_cases == 2
    assert result.labeled_cases == 1
    assert result.pending_cases == 1
    assert result.outcome_counts["good_signal"] == 1
    assert result.pending_case_ids == ["express-7291"]
    assert result.issues == []
    assert (tmp_path / "status" / "corpus_status.json").exists()
    assert "`express-7291`" in (tmp_path / "status" / "corpus_status.md").read_text(encoding="utf-8")


def test_inspect_public_pr_corpus_reports_inconsistent_labels(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case({"product": "useful"}),
            _case(
                {"product": "useful"},
                case_id="express-7291",
                url="https://github.com/expressjs/express/pull/7291",
                label={
                    "outcome": "false_positive",
                    "rationale": "The surfaced finding was incorrect.",
                    "reviewed_at": "2026-06-10",
                },
            ),
        ],
    )

    result = inspect_public_pr_corpus(corpus, tmp_path / "status")

    assert result.pending_cases == 1
    assert len(result.issues) == 2
    assert "no label metadata" in result.issues[0]
    assert "requires product `not_useful`" in result.issues[1]


def test_load_public_pr_corpus_rejects_invalid_label_date(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {"product": "useful"},
                label={
                    "outcome": "good_signal",
                    "rationale": "The report found the expected risk.",
                    "reviewed_at": "10/06/2026",
                },
            )
        ],
    )

    try:
        load_public_pr_corpus(corpus)
    except ValueError as exc:
        assert "label.reviewed_at must be an ISO date" in str(exc)
    else:
        raise AssertionError("Expected invalid label date to be rejected")


def test_run_public_pr_benchmark_passes_when_expectations_match(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "pass",
                    "product": "useful",
                    "decision": "review_required",
                    "required_rules": ["pr_code_change_without_test_delta"],
                    "required_paths": ["lib/response.js"],
                    "max_top_findings": 1,
                }
            )
        ],
    )
    commands: list[list[str]] = []

    def _fake_runner(command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
        commands.append(command)
        assert Path(env["PYTHONPATH"].split(os.pathsep)[0]).name == "src"
        _write_review_artifacts(_output_dir_from_command(command))
        return ReviewCommandResult(returncode=0, stdout="ok")

    result = run_public_pr_benchmark(
        corpus,
        tmp_path / "out",
        options=PublicPRBenchmarkOptions(skip_baseline=True),
        command_runner=_fake_runner,
    )

    assert result.passed_cases == 1
    assert result.failed_cases == 0
    assert result.cases[0].evaluation_status == "passed"
    assert "--skip-baseline" in commands[0]
    assert (tmp_path / "out" / "benchmark_summary.json").exists()
    assert (tmp_path / "out" / "benchmark_summary.md").exists()


def test_run_public_pr_benchmark_fails_when_required_rule_is_not_surfaced(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "pass",
                    "product": "useful",
                    "required_rules": ["critical_write_missing_authz"],
                }
            )
        ],
    )

    def _fake_runner(command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
        _write_review_artifacts(_output_dir_from_command(command))
        return ReviewCommandResult(returncode=0)

    result = run_public_pr_benchmark(corpus, tmp_path / "out", command_runner=_fake_runner)

    assert result.failed_cases == 1
    assert result.cases[0].evaluation_status == "failed"
    assert "missing required surfaced rule" in result.cases[0].errors[0]


def test_run_public_pr_benchmark_can_expect_setup_failure(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "setup_fail",
                    "product": "not_useful",
                }
            )
        ],
    )

    def _fake_runner(command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
        return ReviewCommandResult(returncode=2, stdout="setup failed")

    result = run_public_pr_benchmark(corpus, tmp_path / "out", command_runner=_fake_runner)

    assert result.passed_cases == 1
    assert result.cases[0].execution_status == "setup_fail"
    assert result.cases[0].evaluation_status == "passed"


def test_run_public_pr_benchmark_can_expect_timeout(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "timeout",
                    "product": "not_useful",
                }
            )
        ],
    )

    def _fake_runner(command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
        raise subprocess.TimeoutExpired(cmd=command, timeout=timeout_seconds)

    result = run_public_pr_benchmark(corpus, tmp_path / "out", command_runner=_fake_runner)

    assert result.passed_cases == 1
    assert result.cases[0].execution_status == "timeout"
    assert result.cases[0].evaluation_status == "passed"


def test_run_public_pr_benchmark_counts_top_finding_entries_not_unique_rules(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(
        corpus,
        [
            _case(
                {
                    "execution": "pass",
                    "product": "useful",
                    "required_rules": ["pr_code_change_without_test_delta"],
                    "max_top_findings": 1,
                }
            )
        ],
    )
    duplicate_rule_findings = [
        {
            "rule_id": "pr_code_change_without_test_delta",
            "title": "first",
            "severity": "medium",
            "confidence": "medium",
            "status": "new",
            "source_ref": "lib/response.js",
            "recommendation": "Add a regression test.",
        },
        {
            "rule_id": "pr_code_change_without_test_delta",
            "title": "second",
            "severity": "medium",
            "confidence": "medium",
            "status": "new",
            "source_ref": "lib/request.js",
            "recommendation": "Add a regression test.",
        },
    ]

    def _fake_runner(command: list[str], cwd: Path, env: dict[str, str], timeout_seconds: int) -> ReviewCommandResult:
        _write_review_artifacts(_output_dir_from_command(command), top_findings=duplicate_rule_findings)
        return ReviewCommandResult(returncode=0)

    result = run_public_pr_benchmark(corpus, tmp_path / "out", command_runner=_fake_runner)

    assert result.failed_cases == 1
    assert result.cases[0].top_rules == ["pr_code_change_without_test_delta"]
    assert result.cases[0].top_finding_count == 2
    assert "expected at most 1 top finding(s), got 2" in result.cases[0].errors


def test_cli_benchmark_prs_wires_options(tmp_path: Path, monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def _fake_run(
        corpus_path: Path,
        output_dir: Path,
        *,
        options: PublicPRBenchmarkOptions,
    ) -> PublicPRBenchmarkResult:
        captured["corpus_path"] = corpus_path
        captured["output_dir"] = output_dir
        captured["options"] = options
        return PublicPRBenchmarkResult(
            generated_at_utc="2026-06-09T00:00:00Z",
            corpus_path=str(corpus_path),
            output_dir=str(output_dir),
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            needs_human_review_cases=0,
            execution_passed_cases=1,
            cases=[
                PublicPRCaseResult(
                    id="express-7287",
                    url="https://github.com/expressjs/express/pull/7287",
                    stack="express_node",
                    reason="test",
                    output_dir=str(output_dir / "express-7287"),
                    command=[],
                    returncode=0,
                    execution_status="pass",
                    expected_execution="pass",
                    product_verdict="useful",
                    evaluation_status="passed",
                )
            ],
        )

    corpus = tmp_path / "public_prs.json"
    corpus.write_text('{"version":1,"cases":[]}', encoding="utf-8")
    monkeypatch.setattr("ai_risk_manager.cli.run_public_pr_benchmark", _fake_run)

    code = main(
        [
            "benchmark-prs",
            str(corpus),
            "--output-dir",
            str(tmp_path / "out"),
            "--case-id",
            "express-7287",
            "--skip-baseline",
            "--timeout-seconds",
            "123",
        ]
    )

    assert code == 0
    options = captured["options"]
    assert isinstance(options, PublicPRBenchmarkOptions)
    assert options.case_ids == ["express-7287"]
    assert options.skip_baseline is True
    assert options.timeout_seconds == 123
    assert "Public PR benchmark completed" in capsys.readouterr().out


def test_cli_corpus_status_strict_fails_on_labeling_issues(tmp_path: Path, capsys) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(corpus, [_case({"product": "useful"})])

    code = main(
        [
            "corpus-status",
            str(corpus),
            "--output-dir",
            str(tmp_path / "status"),
            "--strict",
        ]
    )

    assert code == 3
    assert "labeled=0 pending=1 issues=1" in capsys.readouterr().out


def test_cli_corpus_status_strict_allows_pending_review_queue(tmp_path: Path, capsys) -> None:
    corpus = tmp_path / "public_prs.json"
    _write_corpus(corpus, [_case({"product": "needs_human_review"})])

    code = main(
        [
            "corpus-status",
            str(corpus),
            "--output-dir",
            str(tmp_path / "status"),
            "--strict",
        ]
    )

    assert code == 0
    assert "labeled=0 pending=1 issues=0" in capsys.readouterr().out
