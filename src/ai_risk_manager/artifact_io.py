from __future__ import annotations

import errno
import os
from pathlib import Path
import uuid


def write_text_atomic(path: Path, text: str) -> None:
    """Replace a text artifact atomically without exposing a partial target file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as file_handle:
            file_handle.write(text)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_text_new_atomic(path: Path, text: str) -> None:
    """Create a text artifact atomically and fail if the target already exists.

    Uses a hard link to detect if the target already exists. Falls back to an
    O_EXCL create+write when hard links are not supported (cross-device).
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8") as file_handle:
            file_handle.write(text)
        try:
            os.link(temporary_path, path)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise
            if exc.errno != errno.EXDEV:
                raise
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, text.encode("utf-8"))
            finally:
                os.close(fd)
    finally:
        temporary_path.unlink(missing_ok=True)


__all__ = ["write_text_atomic", "write_text_new_atomic"]
