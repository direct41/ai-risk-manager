from __future__ import annotations

from importlib import resources
import os
from pathlib import Path

_SAMPLE_RELATIVE_PATH = ("eval", "repos", "milestone2_fastapi")
_PACKAGE_SAMPLE_RELATIVE_PATH = ("samples", "milestone2_fastapi")


def _looks_like_sample_repo(candidate: Path) -> bool:
    return (
        candidate.is_dir()
        and (candidate / "app" / "main.py").is_file()
        and (candidate / "tests" / "test_pay_order.py").is_file()
    )


def _resolve_packaged_sample_repo_path() -> Path | None:
    try:
        traversable = resources.files("ai_risk_manager").joinpath(*_PACKAGE_SAMPLE_RELATIVE_PATH)
    except (AttributeError, ModuleNotFoundError):
        return None

    candidate = Path(str(traversable)).resolve()
    if _looks_like_sample_repo(candidate):
        return candidate
    return None


def resolve_sample_repo_path(*, start_path: Path | None = None) -> Path:
    env_repo = os.getenv("AIRISK_SAMPLE_REPO", "").strip()
    if env_repo:
        candidate = Path(env_repo).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"AIRISK_SAMPLE_REPO points to a missing directory: {candidate}")

    anchor = start_path or Path(__file__).resolve()
    for parent in anchor.parents:
        candidate = parent.joinpath(*_SAMPLE_RELATIVE_PATH)
        if _looks_like_sample_repo(candidate):
            return candidate.resolve()

    packaged_sample = _resolve_packaged_sample_repo_path()
    if packaged_sample is not None:
        return packaged_sample

    raise FileNotFoundError(
        "Bundled sample repository is unavailable in this installation. "
        "Set AIRISK_SAMPLE_REPO to a local sample path."
    )
