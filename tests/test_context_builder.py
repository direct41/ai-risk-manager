from __future__ import annotations

from pathlib import Path

import pytest

from ai_risk_manager.pipeline.context_builder import build_run_context


def test_build_run_context_clears_base_for_full_mode(tmp_path: Path) -> None:
    ctx = build_run_context(
        repo_path=tmp_path,
        mode="full",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    assert ctx.mode == "full"
    assert ctx.base is None


def test_build_run_context_keeps_base_for_pr_mode(tmp_path: Path) -> None:
    ctx = build_run_context(
        repo_path=tmp_path,
        mode="pr",
        base="main",
        output_dir=tmp_path / ".riskmap",
        provider="auto",
        no_llm=True,
    )
    assert ctx.mode == "pr"
    assert ctx.base == "main"


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("mode", {"mode": "broken"}),
        ("provider", {"provider": "broken"}),
        ("output_format", {"output_format": "broken"}),
        ("analysis_engine", {"analysis_engine": "broken"}),
        ("min_confidence", {"min_confidence": "broken"}),
        ("ci_mode", {"ci_mode": "broken"}),
        ("support_level", {"support_level": "broken"}),
        ("risk_policy", {"risk_policy": "broken"}),
        ("fail_on_severity", {"fail_on_severity": "broken"}),
    ],
)
def test_build_run_context_rejects_invalid_choices(tmp_path: Path, field: str, kwargs: dict[str, str]) -> None:
    params = {
        "repo_path": tmp_path,
        "mode": "full",
        "base": "main",
        "output_dir": tmp_path / ".riskmap",
        "provider": "auto",
        "no_llm": True,
    }
    params.update(kwargs)

    with pytest.raises(ValueError, match=field):
        build_run_context(**params)
