from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import subprocess

import ai_risk_manager.external_judge as external_judge
from ai_risk_manager.cli import main
from ai_risk_manager.external_judge import (
    JudgeAssessment,
    JudgeRunOptions,
    build_judge_consensus,
    build_judge_packet,
    parse_judge_assessment,
    run_external_judge,
)
from ai_risk_manager.integrations.github_pr_review import GitHubPREvidence, GitHubPRFilePatch
from ai_risk_manager.public_pr_benchmark import PublicPRCase, PublicPRExpectation, PublicPRLabel


def _case() -> PublicPRCase:
    return PublicPRCase(
        id="fastapi-15676",
        url="https://github.com/fastapi/fastapi/pull/15676",
        stack="fastapi_pytest",
        reason="Expected product behavior must stay hidden from the judge.",
        expected=PublicPRExpectation(product="needs_human_review"),
    )


def _evidence() -> GitHubPREvidence:
    return GitHubPREvidence(
        title="Fix encoder recursion",
        body="Fixes recursive serialization.",
        state="open",
        base_ref="master",
        head_sha="abcdef",
        files=[
            GitHubPRFilePatch(
                filename="fastapi/encoders.py",
                status="modified",
                additions=5,
                deletions=1,
                patch="@@ -1 +1 @@\n-old\n+new",
            )
        ],
        files_truncated=False,
        patches_truncated=False,
    )


def _write_benchmark_artifacts(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "pr_summary.json").write_text(
        json.dumps(
            {
                "decision": "ready",
                "headline": "Optional cleanup remains.",
                "risk_score": 24,
                "changed_files": ["fastapi/encoders.py"],
                "top_findings": [{"rule_id": "test_quality", "source_ref": "tests/test_encoder.py:10"}],
                "top_actions": [{"rule_id": "test_quality", "action": "Stabilize test."}],
                "review_focus": ["Review test reliability."],
            }
        ),
        encoding="utf-8",
    )
    (path / "merge_triage.json").write_text(
        json.dumps({"actions": [{"rule_id": "test_quality", "action": "Stabilize test."}]}),
        encoding="utf-8",
    )
    (path / "review_pr_metadata.json").write_text(
        json.dumps({"schema_version": "1.0", "head_sha": "abcdef"}),
        encoding="utf-8",
    )


def _assessment(
    *,
    judge: str,
    packet_hash: str,
    outcome: str = "good_signal",
    case_id: str = "fastapi-15676",
) -> dict:
    return asdict(
        JudgeAssessment(
            schema_version="1.0",
            case_id=case_id,
            packet_hash=packet_hash,
            judge=judge,
            model=f"{judge}-model",
            outcome=outcome,  # type: ignore[arg-type]
            confidence="high",
            correct_signals=["Useful warning."],
            false_positives=[],
            missed_risks=[],
            rationale="The report matches the visible change risk.",
            generated_at_utc="2026-06-10T00:00:00Z",
        )
    )


def test_build_judge_packet_excludes_corpus_label_and_expectations(tmp_path: Path) -> None:
    case = PublicPRCase(
        **{
            **asdict(_case()),
            "expected": PublicPRExpectation(product="useful"),
            "label": PublicPRLabel(
                outcome="good_signal",
                rationale="Existing label must stay hidden.",
                reviewed_at="2026-06-10",
            ),
        }
    )
    benchmark_dir = tmp_path / "benchmark"
    _write_benchmark_artifacts(benchmark_dir)

    packet = build_judge_packet(case, _evidence(), benchmark_dir)
    serialized = json.dumps(asdict(packet))

    assert packet.case_id == "fastapi-15676"
    assert "Existing label must stay hidden" not in serialized
    assert "Expected product behavior must stay hidden" not in serialized
    assert '"expected"' not in serialized
    assert packet.product_report["decision"] == "ready"
    assert len(packet.packet_hash) == 64


def test_parse_judge_assessment_accepts_claude_structured_output() -> None:
    assessment = parse_judge_assessment(
        {
            "structured_output": {
                "outcome": "noisy",
                "confidence": "medium",
                "correct_signals": ["The report mentions test reliability."],
                "false_positives": ["The reported test is unrelated to the patch."],
                "missed_risks": [],
                "rationale": "Partly relevant but distracting.",
            }
        },
        case_id="fastapi-15676",
        packet_hash="abc",
        judge="claude",
        model="claude-sonnet-4-6",
    )

    assert assessment.outcome == "noisy"
    assert assessment.confidence == "medium"
    assert assessment.judge == "claude"


def test_build_judge_packet_rejects_stale_benchmark_head(tmp_path: Path) -> None:
    benchmark_dir = tmp_path / "benchmark"
    _write_benchmark_artifacts(benchmark_dir)
    (benchmark_dir / "review_pr_metadata.json").write_text(
        json.dumps({"schema_version": "1.0", "head_sha": "stale"}),
        encoding="utf-8",
    )

    try:
        build_judge_packet(_case(), _evidence(), benchmark_dir)
    except ValueError as exc:
        assert "does not match current GitHub head" in str(exc)
    else:
        raise AssertionError("Expected stale benchmark head to be rejected")


def test_run_external_judge_writes_blind_packet_raw_response_and_assessment(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    corpus.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "fastapi-15676",
                        "url": "https://github.com/fastapi/fastapi/pull/15676",
                        "stack": "fastapi_pytest",
                        "reason": "encoder regression",
                        "expected": {"product": "needs_human_review"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    benchmark_dir = tmp_path / "benchmark"
    _write_benchmark_artifacts(benchmark_dir / "fastapi-15676")
    runner_calls: list[tuple[str, str, int, float]] = []

    def _fake_fetch(*args, **kwargs) -> GitHubPREvidence:
        return _evidence()

    def _fake_runner(prompt: str, model: str, timeout_seconds: int, max_budget_usd: float) -> object:
        runner_calls.append((prompt, model, timeout_seconds, max_budget_usd))
        return {
            "structured_output": {
                "outcome": "good_signal",
                "confidence": "high",
                "correct_signals": ["Correctly identifies test risk."],
                "false_positives": [],
                "missed_risks": [],
                "rationale": "Useful and tied to the changed code.",
            }
        }

    output_dir = tmp_path / "judge"
    assessments = run_external_judge(
        corpus,
        benchmark_dir,
        output_dir,
        options=JudgeRunOptions(case_ids=["fastapi-15676"], max_budget_usd=0.5),
        judge_runner=_fake_runner,
        evidence_fetcher=_fake_fetch,
    )

    assert assessments[0].outcome == "good_signal"
    assert runner_calls[0][3] == 0.5
    assert (output_dir / "fastapi-15676" / "packet.json").exists()
    assert (output_dir / "fastapi-15676" / "raw" / "claude.json").exists()
    assert (output_dir / "fastapi-15676" / "assessments" / "claude.json").exists()


def test_run_external_judge_uses_gemini_default_model(tmp_path: Path) -> None:
    corpus = tmp_path / "public_prs.json"
    corpus.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {
                        "id": "fastapi-15676",
                        "url": "https://github.com/fastapi/fastapi/pull/15676",
                        "stack": "fastapi_pytest",
                        "reason": "encoder regression",
                        "expected": {"product": "needs_human_review"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    benchmark_dir = tmp_path / "benchmark"
    _write_benchmark_artifacts(benchmark_dir / "fastapi-15676")
    models: list[str] = []

    def _fake_fetch(*args, **kwargs) -> GitHubPREvidence:
        return _evidence()

    def _fake_runner(prompt: str, model: str, timeout_seconds: int, max_budget_usd: float) -> object:
        models.append(model)
        return {
            "outcome": "good_signal",
            "confidence": "high",
            "correct_signals": ["Useful."],
            "false_positives": [],
            "missed_risks": [],
            "rationale": "The report is useful.",
        }

    assessments = run_external_judge(
        corpus,
        benchmark_dir,
        tmp_path / "judge",
        options=JudgeRunOptions(case_ids=["fastapi-15676"], judge="gemini"),
        judge_runner=_fake_runner,
        evidence_fetcher=_fake_fetch,
    )

    assert models == ["gemini-2.5-pro"]
    assert assessments[0].judge == "gemini"
    assert assessments[0].model == "gemini-2.5-pro"


def test_gemini_judge_normalizes_json_wrapper(monkeypatch) -> None:
    def _fake_run(*args, **kwargs):
        command = args[0]
        policy_path = Path(command[command.index("--admin-policy") + 1])
        assert 'toolName = "read_file"' in policy_path.read_text(encoding="utf-8")
        assert 'decision = "ask_user"' in policy_path.read_text(encoding="utf-8")
        settings_path = Path(kwargs["env"]["GEMINI_CLI_SYSTEM_SETTINGS_PATH"])
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        assert settings["tools"]["core"] == ["read_file"]
        assert settings["admin"]["extensions"]["enabled"] is False
        assert settings["admin"]["mcp"]["enabled"] is False
        assert settings["admin"]["skills"]["enabled"] is False
        assert "--skip-trust" in command
        assert '"outcome"' in kwargs["input"]
        assert '"confidence"' in kwargs["input"]
        assert "OUTPUT_JSON_SCHEMA:" in kwargs["input"]
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=json.dumps(
                {
                    "response": (
                        "```json\n"
                        '{"outcome":"noisy","confidence":"high","correct_signals":[],'
                        '"false_positives":[],"missed_risks":[],"rationale":"Weak signal."}'
                        "\n```"
                    )
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("ai_risk_manager.external_judge.subprocess.run", _fake_run)

    payload = external_judge._run_gemini_judge("prompt", "gemini-2.5-pro", 30, 1.0)

    assert payload["outcome"] == "noisy"
    assert payload["rationale"] == "Weak signal."


def test_gemini_judge_explains_unsupported_location(monkeypatch) -> None:
    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=55,
            stdout="",
            stderr="IneligibleTierError: UNSUPPORTED_LOCATION not currently available in your location",
        )

    monkeypatch.setattr("ai_risk_manager.external_judge.subprocess.run", _fake_run)

    try:
        external_judge._run_gemini_judge("prompt", "gemini-2.5-pro", 30, 1.0)
    except ValueError as exc:
        assert "Gemini CLI OAuth is unavailable" in str(exc)
        assert "GEMINI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected unsupported Gemini location to be reported")


def test_build_judge_consensus_confirms_matching_assessments(tmp_path: Path) -> None:
    case_dir = tmp_path / "fastapi-15676"
    assessment_dir = case_dir / "assessments"
    assessment_dir.mkdir(parents=True)
    (case_dir / "packet.json").write_text(json.dumps({"packet_hash": "packet-1"}), encoding="utf-8")
    for judge in ("claude", "human"):
        (assessment_dir / f"{judge}.json").write_text(
            json.dumps(_assessment(judge=judge, packet_hash="packet-1")),
            encoding="utf-8",
        )

    result = build_judge_consensus(tmp_path)

    assert result.confirmed_cases == 1
    assert result.cases[0].status == "confirmed"
    assert result.cases[0].outcome == "good_signal"
    assert (tmp_path / "consensus.md").exists()


def test_build_judge_consensus_rejects_stale_packet_hash(tmp_path: Path) -> None:
    case_dir = tmp_path / "fastapi-15676"
    assessment_dir = case_dir / "assessments"
    assessment_dir.mkdir(parents=True)
    (case_dir / "packet.json").write_text(json.dumps({"packet_hash": "current"}), encoding="utf-8")
    (assessment_dir / "claude.json").write_text(
        json.dumps(_assessment(judge="claude", packet_hash="stale")),
        encoding="utf-8",
    )
    (assessment_dir / "human.json").write_text(
        json.dumps(_assessment(judge="human", packet_hash="current")),
        encoding="utf-8",
    )

    result = build_judge_consensus(tmp_path)

    assert result.invalid_cases == 1
    assert result.cases[0].status == "invalid_assessments"


def test_build_judge_consensus_rejects_incomplete_imported_assessment(tmp_path: Path) -> None:
    case_dir = tmp_path / "fastapi-15676"
    assessment_dir = case_dir / "assessments"
    assessment_dir.mkdir(parents=True)
    (case_dir / "packet.json").write_text(json.dumps({"packet_hash": "packet-1"}), encoding="utf-8")
    imported = _assessment(judge="human", packet_hash="packet-1")
    imported["rationale"] = ""
    (assessment_dir / "human.json").write_text(json.dumps(imported), encoding="utf-8")

    result = build_judge_consensus(tmp_path)

    assert result.invalid_cases == 1
    assert result.cases[0].status == "invalid_assessments"


def test_cli_judge_prs_requires_explicit_case_selection(capsys) -> None:
    code = main(["judge-prs", "--benchmark-dir", "/tmp/benchmark"])

    assert code == 2
    assert "--case-id or explicitly use --all-pending" in capsys.readouterr().out


def test_cli_judge_consensus_returns_nonzero_when_second_assessment_is_missing(
    tmp_path: Path,
    capsys,
) -> None:
    case_dir = tmp_path / "fastapi-15676"
    assessment_dir = case_dir / "assessments"
    assessment_dir.mkdir(parents=True)
    (case_dir / "packet.json").write_text(json.dumps({"packet_hash": "packet-1"}), encoding="utf-8")
    (assessment_dir / "claude.json").write_text(
        json.dumps(_assessment(judge="claude", packet_hash="packet-1")),
        encoding="utf-8",
    )

    code = main(["judge-consensus", str(tmp_path)])

    assert code == 3
    assert "insufficient=1" in capsys.readouterr().out
