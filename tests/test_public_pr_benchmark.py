from __future__ import annotations

import json
import os
from pathlib import Path

from ai_risk_manager.cli import main
from ai_risk_manager.public_pr_benchmark import (
    PublicPRBenchmarkOptions,
    PublicPRBenchmarkResult,
    PublicPRCaseResult,
    ReviewCommandResult,
    load_public_pr_corpus,
    run_public_pr_benchmark,
)


def _write_corpus(path: Path, cases: list[dict]) -> None:
    path.write_text(json.dumps({"version": 1, "cases": cases}), encoding="utf-8")


def _case(expected: dict | None = None) -> dict:
    return {
        "id": "express-7287",
        "url": "https://github.com/expressjs/express/pull/7287",
        "stack": "express_node",
        "reason": "regression corpus case",
        "expected": expected or {},
    }


def _output_dir_from_command(command: list[str]) -> Path:
    return Path(command[command.index("--output-dir") + 1])


def _write_review_artifacts(
    output_dir: Path,
    *,
    decision: str = "review_required",
    rule_id: str = "pr_code_change_without_test_delta",
    source_ref: str = "lib/response.js",
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
    (output_dir / "pr_summary.json").write_text(
        json.dumps(
            {
                "decision": decision,
                "risk_score": 38,
                "top_findings": [top_finding],
                "top_actions": [action],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "merge_triage.json").write_text(
        json.dumps({"decision": decision, "risk_score": 38, "actions": [action]}),
        encoding="utf-8",
    )
    (output_dir / "findings.json").write_text(json.dumps({"findings": [top_finding]}), encoding="utf-8")


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
                }
            )
        ],
    )

    cases = load_public_pr_corpus(corpus)

    assert cases[0].id == "express-7287"
    assert cases[0].expected.product == "useful"
    assert cases[0].expected.required_paths == ["lib/response.js"]


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
