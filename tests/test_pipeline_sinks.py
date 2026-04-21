from __future__ import annotations

from pathlib import Path

from ai_risk_manager.pipeline import sinks as sinks_module


def test_git_changed_files_rejects_option_like_base(monkeypatch, tmp_path: Path) -> None:
    called = False

    def _fake_run(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal called
        called = True
        raise AssertionError("git should not run for option-like refs")

    monkeypatch.setattr(sinks_module, "_git_executable", lambda: "/usr/bin/git")
    monkeypatch.setattr(sinks_module.subprocess, "run", _fake_run)

    assert sinks_module.GitChangedFilesSink().resolve(tmp_path, "--help") is None
    assert called is False


def test_git_changed_files_uses_resolved_git_and_ref_separator(monkeypatch, tmp_path: Path) -> None:
    captured: list[str] = []

    class _Proc:
        returncode = 0
        stdout = "src/app.py\n"

    def _fake_run(cmd: list[str], **kwargs) -> _Proc:  # noqa: ANN003
        captured.extend(cmd)
        return _Proc()

    monkeypatch.setattr(sinks_module, "_git_executable", lambda: "/usr/bin/git")
    monkeypatch.setattr(sinks_module.subprocess, "run", _fake_run)

    assert sinks_module.GitChangedFilesSink().resolve(tmp_path, "main") == {"src/app.py"}
    assert captured[0] == "/usr/bin/git"
    assert captured[-1] == "--"
