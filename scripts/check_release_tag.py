from __future__ import annotations

import argparse
from pathlib import Path
import tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]


def expected_tag(pyproject_path: Path) -> str:
    payload = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    version = payload.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject project.version must be a non-empty string")
    return f"v{version}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify that a release tag matches the package version.")
    parser.add_argument("tag")
    parser.add_argument("--pyproject", type=Path, default=REPO_ROOT / "pyproject.toml")
    args = parser.parse_args(argv)
    try:
        expected = expected_tag(args.pyproject)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        print(f"Release tag check failed: {exc}")
        return 2
    if args.tag != expected:
        print(f"Release tag check failed: expected {expected}, got {args.tag}")
        return 1
    print(f"Release tag check passed: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
