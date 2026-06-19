from __future__ import annotations

from pathlib import Path
import subprocess

from ai_risk_manager.collectors.file_discovery import iter_project_files


def _relative_paths(repo_path: Path) -> set[str]:
    return {path.relative_to(repo_path).as_posix() for path in iter_project_files(repo_path)}


def test_file_discovery_respects_gitignore_and_standard_generated_trees(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / ".gitignore", "generated/\n")
    write_file(tmp_path / "app" / "main.py", "print('owned')\n")
    write_file(tmp_path / "generated" / "noise.py", "print('ignored')\n")
    write_file(tmp_path / ".venv-min" / "lib" / "noise.py", "print('venv')\n")
    write_file(tmp_path / "samples" / "demo.py", "print('sample')\n")
    write_file(tmp_path / "node_modules" / "noise.js", "console.log('vendor')\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    assert _relative_paths(tmp_path) == {".gitignore", "app/main.py"}


def test_file_discovery_fallback_excludes_virtualenv_variants_and_samples(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "service" / "api.py", "print('owned')\n")
    write_file(tmp_path / ".venv-local" / "api.py", "print('venv')\n")
    write_file(tmp_path / "venv-test" / "api.py", "print('venv')\n")
    write_file(tmp_path / "examples" / "api.py", "print('example')\n")

    assert _relative_paths(tmp_path) == {"service/api.py"}


def test_file_discovery_does_not_follow_symlinks_outside_repo(tmp_path: Path, write_file) -> None:
    repo_path = tmp_path / "repo"
    outside_file = tmp_path / "outside.py"
    write_file(outside_file, "print('outside')\n")
    write_file(repo_path / "app" / "main.py", "print('owned')\n")
    (repo_path / "app" / "outside.py").symlink_to(outside_file)

    assert _relative_paths(repo_path) == {"app/main.py"}


def test_file_discovery_preserves_relative_repo_path_style(tmp_path: Path, write_file, monkeypatch) -> None:
    write_file(tmp_path / "service" / "api.py", "print('owned')\n")
    monkeypatch.chdir(tmp_path)

    discovered = iter_project_files(Path("."))

    assert discovered == [Path("service/api.py")]
    assert _relative_paths(Path(".")) == {"service/api.py"}
