from __future__ import annotations

from pathlib import Path
import re


def _template_text(name: str) -> str:
    return (Path(".github/ISSUE_TEMPLATE") / name).read_text(encoding="utf-8")


def _field_ids(template: str) -> set[str]:
    return set(re.findall(r"^\s+id: ([a-z_]+)$", template, flags=re.MULTILINE))


def test_alpha_feedback_template_captures_validation_decision_fields() -> None:
    template = _template_text("alpha_feedback.yml")
    required = {
        "reviewer_role",
        "command",
        "merge_decision",
        "top_findings",
        "review_impact",
        "useful",
        "noisy",
        "setup_friction",
        "preferred_workflow",
        "run_again",
        "privacy_ack",
    }

    assert required <= _field_ids(template)
    assert "This feedback contains no secrets" in template
    assert "required: true" in template


def test_pr_review_request_captures_role_and_response_preference() -> None:
    template = _template_text("pr_review_request.yml")

    assert {
        "pr_url",
        "reviewer_role",
        "stack",
        "why_hard",
        "current_review_question",
        "preferred_response",
        "privacy_ack",
    } <= _field_ids(template)
    assert "This PR URL is public" in template
