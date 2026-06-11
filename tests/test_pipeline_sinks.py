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


def test_git_diff_uses_resolved_git_and_ref_separator(monkeypatch, tmp_path: Path) -> None:
    captured: list[str] = []

    class _Proc:
        returncode = 0
        stdout = "diff --git a/src/app.py b/src/app.py\n"

    def _fake_run(cmd: list[str], **kwargs) -> _Proc:  # noqa: ANN003
        captured.extend(cmd)
        return _Proc()

    monkeypatch.setattr(sinks_module, "_git_executable", lambda: "/usr/bin/git")
    monkeypatch.setattr(sinks_module.subprocess, "run", _fake_run)

    assert sinks_module.GitDiffSink().resolve(tmp_path, "main") == _Proc.stdout
    assert captured[0] == "/usr/bin/git"
    assert "--unified=0" in captured
    assert captured[-1] == "--"


def test_git_changed_files_falls_back_to_two_dot_for_exact_base_sha(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    class _Proc:
        def __init__(self, returncode: int, stdout: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout

    def _fake_run(cmd: list[str], **kwargs) -> _Proc:  # noqa: ANN003
        commands.append(cmd)
        if "a" * 40 + "..HEAD" in cmd:
            return _Proc(0, "src/app.py\n")
        return _Proc(128)

    monkeypatch.setattr(sinks_module, "_git_executable", lambda: "/usr/bin/git")
    monkeypatch.setattr(sinks_module.subprocess, "run", _fake_run)

    assert sinks_module.GitChangedFilesSink().resolve(tmp_path, "a" * 40) == {"src/app.py"}
    assert ["a" * 40 + "...HEAD", "a" * 40 + "..HEAD"] == [command[-2] for command in commands]


def test_git_changed_files_does_not_use_two_dot_for_branch_base(monkeypatch, tmp_path: Path) -> None:
    refs: list[str] = []

    class _Proc:
        returncode = 128
        stdout = ""

    def _fake_run(cmd: list[str], **kwargs) -> _Proc:  # noqa: ANN003
        refs.append(cmd[-2])
        return _Proc()

    monkeypatch.setattr(sinks_module, "_git_executable", lambda: "/usr/bin/git")
    monkeypatch.setattr(sinks_module.subprocess, "run", _fake_run)

    assert sinks_module.GitChangedFilesSink().resolve(tmp_path, "main") is None
    assert refs == ["main...HEAD", "origin/main...HEAD"]
