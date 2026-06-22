from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_release_tag.py"
SPEC = importlib.util.spec_from_file_location("check_release_tag", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_release_tag = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_release_tag
SPEC.loader.exec_module(check_release_tag)


def _write_pyproject(path: Path, version: str = "1.2.3") -> None:
    path.write_text(f'[project]\nname = "example"\nversion = "{version}"\n', encoding="utf-8")


def test_release_tag_must_match_package_version(tmp_path: Path, capsys) -> None:
    pyproject = tmp_path / "pyproject.toml"
    _write_pyproject(pyproject)

    assert check_release_tag.expected_tag(pyproject) == "v1.2.3"
    assert check_release_tag.main(["v1.2.3", "--pyproject", str(pyproject)]) == 0
    assert "passed" in capsys.readouterr().out

    assert check_release_tag.main(["v1.2.4", "--pyproject", str(pyproject)]) == 1
    assert "expected v1.2.3" in capsys.readouterr().out


def test_release_tag_rejects_missing_or_invalid_version(tmp_path: Path, capsys) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'example'\n", encoding="utf-8")

    assert check_release_tag.main(["v1.2.3", "--pyproject", str(pyproject)]) == 2
    assert "project.version" in capsys.readouterr().out
