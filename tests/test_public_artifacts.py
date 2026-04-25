from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_public_artifacts.py"
SPEC = importlib.util.spec_from_file_location("check_public_artifacts", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
check_public_artifacts = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_public_artifacts
SPEC.loader.exec_module(check_public_artifacts)


def _write_guard_files(tmp_path: Path, *, allowlist: str = "docs/architecture.md\n") -> None:
    (tmp_path / ".github").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".github" / "public-artifacts-allowlist.txt").write_text(allowlist, encoding="utf-8")
    (tmp_path / "MANIFEST.in").write_text(
        "\n".join(
            [
                "prune docs",
                "prune eval",
                "prune examples",
                "prune scripts",
                "prune tests",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(
        "\n".join(
            [
                ".riskmap/",
                "eval/results/",
                "eval/.history/",
                "ALPHA.md",
                "RELEASE.md",
                "docs/roadmap.md",
                "docs/ui-flow-pilots.md",
                "docs/launch/",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _configure_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, candidate_paths: list[str]) -> None:
    monkeypatch.setattr(check_public_artifacts, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check_public_artifacts, "ALLOWLIST_PATH", tmp_path / ".github" / "public-artifacts-allowlist.txt")
    monkeypatch.setattr(check_public_artifacts, "MANIFEST_PATH", tmp_path / "MANIFEST.in")
    monkeypatch.setattr(check_public_artifacts, "GITIGNORE_PATH", tmp_path / ".gitignore")
    monkeypatch.setattr(check_public_artifacts, "_candidate_paths", lambda: sorted(candidate_paths))


def test_public_artifact_gate_passes_for_allowlisted_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    _configure_gate(monkeypatch, tmp_path, ["docs/architecture.md"])

    failures = check_public_artifacts.check_public_artifacts()

    assert failures == []


def test_public_artifact_gate_requires_docs_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "new-public-doc.md").write_text("# New Doc\n", encoding="utf-8")
    _configure_gate(monkeypatch, tmp_path, ["docs/new-public-doc.md"])

    failures = check_public_artifacts.check_public_artifacts()

    assert any("docs/new-public-doc.md: public docs file is not listed" in failure for failure in failures)


def test_public_artifact_gate_blocks_generated_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="")
    _configure_gate(
        monkeypatch,
        tmp_path,
        [
            ".riskmap/report.md",
            "eval/results/summary.json",
            "some/nested/findings.json",
        ],
    )

    failures = check_public_artifacts.check_public_artifacts()

    assert ".riskmap/report.md: local-only artifact is tracked" in failures
    assert ".riskmap/report.md: generated risk-analysis artifact is tracked" in failures
    assert "eval/results/summary.json: local-only artifact is tracked" in failures
    assert "some/nested/findings.json: generated risk-analysis artifact is tracked" in failures


def test_public_artifact_gate_blocks_local_only_notes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="")
    _configure_gate(monkeypatch, tmp_path, ["ALPHA.md", "docs/roadmap.md", "docs/launch/private.md"])

    failures = check_public_artifacts.check_public_artifacts()

    assert "ALPHA.md: local-only artifact is tracked" in failures
    assert "docs/roadmap.md: local-only artifact is tracked" in failures
    assert "docs/launch/private.md: local-only artifact is tracked" in failures


def test_public_artifact_gate_detects_secret_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="")
    leak = tmp_path / "src" / "leak.py"
    leak.parent.mkdir(parents=True)
    fake_key = "sk-" + "proj-" + "abcdefghijklmnopqrstuvwxyz123456"
    leak.write_text(f'TOKEN = "{fake_key}"\n', encoding="utf-8")
    _configure_gate(monkeypatch, tmp_path, ["src/leak.py"])

    failures = check_public_artifacts.check_public_artifacts()

    assert any("src/leak.py: contains OpenAI-style API key" == failure for failure in failures)


def test_public_artifact_gate_detects_nested_key_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="")
    key_file = tmp_path / "secrets" / "id_rsa.pem"
    key_file.parent.mkdir(parents=True)
    key_header = "-----BEGIN OPENSSH " + "PRIVATE KEY-----"
    key_file.write_text(f"{key_header}\nfake-key\n", encoding="utf-8")
    _configure_gate(monkeypatch, tmp_path, ["secrets/id_rsa.pem"])

    failures = check_public_artifacts.check_public_artifacts()

    assert "secrets/id_rsa.pem: contains private key block" in failures


def test_public_artifact_gate_requires_manifest_and_gitignore_guards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="")
    (tmp_path / "MANIFEST.in").write_text("prune docs\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".riskmap/\n", encoding="utf-8")
    _configure_gate(monkeypatch, tmp_path, [])

    failures = check_public_artifacts.check_public_artifacts()

    assert any("MANIFEST.in is missing package-prune guard" in failure for failure in failures)
    assert any(".gitignore is missing local/private artifact guard" in failure for failure in failures)


def test_public_artifact_gate_rejects_stale_allowlist_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_guard_files(tmp_path, allowlist="docs/missing.md\n")
    _configure_gate(monkeypatch, tmp_path, [])

    failures = check_public_artifacts.check_public_artifacts()

    assert failures == ["public artifact allowlist contains non-tracked path(s): docs/missing.md"]
