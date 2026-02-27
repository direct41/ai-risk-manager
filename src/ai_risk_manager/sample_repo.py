from __future__ import annotations

import os
from pathlib import Path

_SAMPLE_RELATIVE_PATH = ("eval", "repos", "milestone2_fastapi")


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
        if candidate.is_dir():
            return candidate.resolve()

    raise FileNotFoundError(
        "Bundled sample repository is unavailable in this installation. "
        "Set AIRISK_SAMPLE_REPO to a local sample path."
    )
