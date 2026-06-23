from __future__ import annotations

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "quality.yml"
PUBLISH_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"
RELEASE_REQUIREMENTS_PATH = REPO_ROOT / ".github" / "requirements" / "release.txt"


def test_quality_workflow_pins_external_actions_to_commit_shas() -> None:
    workflow = "\n".join(
        path.read_text(encoding="utf-8") for path in (WORKFLOW_PATH, PUBLISH_WORKFLOW_PATH)
    )
    external_uses = [
        line.strip().split("uses:", 1)[1].strip().split(" #", 1)[0]
        for line in workflow.splitlines()
        if "uses:" in line and "uses: ./" not in line
    ]

    assert external_uses
    for action in external_uses:
        _, separator, revision = action.rpartition("@")
        assert separator == "@"
        assert re.fullmatch(r"[0-9a-f]{40}", revision), action


def test_workflows_use_approved_artifact_action_majors() -> None:
    workflow = "\n".join(
        path.read_text(encoding="utf-8") for path in (WORKFLOW_PATH, PUBLISH_WORKFLOW_PATH)
    )

    assert "actions/upload-artifact@" in workflow
    assert "actions/download-artifact@" in workflow
    assert not re.search(r"actions/(?:upload|download)-artifact@[0-9a-f]{40} # v4(?:\b|\.)", workflow)
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1" in workflow
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1" in workflow


def test_release_toolchain_is_fully_pinned() -> None:
    requirements = RELEASE_REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines()

    assert requirements == [
        "pip==26.1.2",
        "setuptools==82.0.1",
        "wheel==0.47.0",
        "build==1.5.0",
        "twine==6.2.0",
        "pip-audit==2.10.1",
        "cyclonedx-bom==7.3.0",
    ]


def test_release_workflow_builds_once_and_validates_downloaded_artifacts() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert workflow.count("python -m build --no-isolation") == 1
    assert "python -m twine check dist/*.whl dist/*.tar.gz" in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert 'python-version: ["3.11", "3.12", "3.13"]' in workflow
    assert 'pip install --no-build-isolation "$sdist"' in workflow
    assert 'pip install "${wheel}[api]"' in workflow


def test_release_workflow_separates_audits_and_emits_sbom() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "core-runtime-audit.json" in workflow
    assert "api-runtime-audit.json" in workflow
    assert "release-toolchain-audit.json" in workflow
    assert "core-runtime-requirements.txt" in workflow
    assert "api-runtime-requirements.txt" in workflow
    assert "sed '/^ai-risk-manager/d'" in workflow
    assert "runtime-api-sbom.cdx.json" in workflow
    assert "--output-reproducible" in workflow
    assert workflow.count("pip-audit --strict") == 3


def test_quality_workflow_runs_eval_isolation_with_full_history() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "fetch-depth: 0" in workflow
    assert "python scripts/check_eval_isolation.py" in workflow
    assert "AIRISK_EVAL_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow


def test_quality_workflow_enforces_critical_mutation_score() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "critical-mutation:" in workflow
    assert "mutmut run --max-children 4" in workflow
    assert "scripts/check_mutation_score.py mutants/mutmut-cicd-stats.json --threshold 0.75" in workflow
    assert "name: critical-mutation-stats" in workflow
    assert 'mutmut==3.6.0' in pyproject
    for module in ("rules/policy.py", "trust/scoring.py", "triage/merge.py", "pr_scope.py"):
        assert f'"src/ai_risk_manager/{module}"' in pyproject


def test_quality_workflow_enforces_and_preserves_performance_evidence() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "performance-slo:" in workflow
    assert "python scripts/run_performance_suite.py" in workflow
    assert "--repetitions 3" in workflow
    assert "--enforce" in workflow
    assert "--output performance-results.json" in workflow
    assert "name: performance-slo-results" in workflow


def test_release_workflow_uses_tag_bound_oidc_publish_and_provenance() -> None:
    workflow = PUBLISH_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "types: [published]" in workflow
    assert "ref: ${{ github.event.release.tag_name }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert 'test "$(git cat-file -t "$AIRISK_RELEASE_TAG")" = "tag"' in workflow
    assert "git merge-base --is-ancestor HEAD origin/main" in workflow
    assert 'python scripts/check_release_tag.py "$AIRISK_RELEASE_TAG"' in workflow
    assert workflow.count("python -m build --no-isolation") == 1
    assert "python -m twine check packages/*.whl packages/*.tar.gz" in workflow
    assert "--output-reproducible" in workflow
    assert "actions/attest-build-provenance@" in workflow
    assert "attestations: write" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@" in workflow
    assert "password:" not in workflow
