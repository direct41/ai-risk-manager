from __future__ import annotations

from pathlib import Path

import pytest

from ai_risk_manager.artifact_io import write_text_atomic, write_text_new_atomic


def test_write_text_atomic_replaces_target_without_leaving_temporary_files(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("old", encoding="utf-8")

    write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_text_atomic_preserves_target_when_replace_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "artifact.json"
    target.write_text("old", encoding="utf-8")

    def fail_replace(self: Path, target_path: Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_text_new_atomic_creates_target_once(tmp_path: Path) -> None:
    target = tmp_path / "frozen.json"

    write_text_new_atomic(target, "first")

    with pytest.raises(FileExistsError):
        write_text_new_atomic(target, "second")
    assert target.read_text(encoding="utf-8") == "first"
    assert list(tmp_path.glob(".*.tmp")) == []
