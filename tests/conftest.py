from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def write_file():
    """Return a helper that writes text to *path*, creating parent dirs."""

    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    return _write
