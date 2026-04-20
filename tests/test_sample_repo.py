from __future__ import annotations

from pathlib import Path

import pytest

from ai_risk_manager.sample_repo import resolve_sample_repo_path


def test_resolve_sample_repo_path_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample_dir = tmp_path / "custom-sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AIRISK_SAMPLE_REPO", str(sample_dir))

    resolved = resolve_sample_repo_path()

    assert resolved == sample_dir.resolve()


def test_resolve_sample_repo_path_raises_for_missing_env_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-sample"
    monkeypatch.setenv("AIRISK_SAMPLE_REPO", str(missing))

    with pytest.raises(FileNotFoundError, match="AIRISK_SAMPLE_REPO points to a missing directory"):
        resolve_sample_repo_path()


def test_resolve_sample_repo_path_finds_bundled_sample_by_parent_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIRISK_SAMPLE_REPO", raising=False)
    sample_dir = tmp_path / "workspace" / "eval" / "repos" / "milestone2_fastapi"
    (sample_dir / "app").mkdir(parents=True, exist_ok=True)
    (sample_dir / "tests").mkdir(parents=True, exist_ok=True)
    (sample_dir / "app" / "main.py").write_text("app = object()\n", encoding="utf-8")
    (sample_dir / "tests" / "test_pay_order.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    anchor = tmp_path / "workspace" / "src" / "ai_risk_manager" / "sample_repo.py"

    resolved = resolve_sample_repo_path(start_path=anchor)

    assert resolved == sample_dir.resolve()


def test_resolve_sample_repo_path_falls_back_to_packaged_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIRISK_SAMPLE_REPO", raising=False)
    anchor = tmp_path / "isolated" / "src" / "ai_risk_manager" / "sample_repo.py"

    resolved = resolve_sample_repo_path(start_path=anchor)

    assert resolved.name == "milestone2_fastapi"
    assert (resolved / "app" / "main.py").is_file()
    assert (resolved / "tests" / "test_pay_order.py").is_file()
