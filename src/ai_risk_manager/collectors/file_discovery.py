from __future__ import annotations

import os
from pathlib import Path
import subprocess  # nosec B404


_EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".riskmap",
    ".ruff_cache",
    ".svn",
    ".tox",
    "__pycache__",
    "__pypackages__",
    "build",
    "coverage",
    "dist",
    "eval",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "htmlcov",
    "node_modules",
    "sample",
    "samples",
    "site-packages",
    "testdata",
    "venv",
}


def _is_virtualenv_dir(name: str) -> bool:
    lowered = name.lower()
    return lowered == ".venv" or lowered.startswith(".venv-") or lowered.startswith("venv-")


def _is_excluded_relative_path(path: Path) -> bool:
    return any(part.lower() in _EXCLUDED_DIR_NAMES or _is_virtualenv_dir(part) for part in path.parts[:-1])


def _is_within_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root)
    except (OSError, ValueError):
        return False
    return True


def _git_visible_paths(repo_root: Path) -> list[Path] | None:
    try:
        proc = subprocess.run(  # nosec B603
            ["git", "-C", str(repo_root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None

    paths: list[Path] = []
    for raw_path in proc.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = Path(os.fsdecode(raw_path))
        if relative_path.is_absolute() or _is_excluded_relative_path(relative_path):
            continue
        candidate = repo_root / relative_path
        if candidate.is_file() and _is_within_repo(candidate, repo_root):
            paths.append(candidate)
    return sorted(set(paths), key=lambda path: path.as_posix())


def _walk_visible_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for root, dirs, filenames in os.walk(repo_root):
        dirs[:] = sorted(
            name
            for name in dirs
            if name.lower() not in _EXCLUDED_DIR_NAMES and not _is_virtualenv_dir(name)
        )
        root_path = Path(root)
        for filename in sorted(filenames):
            candidate = root_path / filename
            if candidate.is_file() and _is_within_repo(candidate, repo_root):
                paths.append(candidate)
    return paths


def iter_project_files(repo_path: Path) -> list[Path]:
    """Return repository-owned files while excluding ignored, generated, and vendored trees."""

    repo_root = repo_path.resolve()
    git_paths = _git_visible_paths(repo_root)
    if git_paths is not None:
        return git_paths
    return _walk_visible_paths(repo_root)


__all__ = ["iter_project_files"]
