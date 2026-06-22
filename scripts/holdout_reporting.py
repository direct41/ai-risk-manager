from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from itertools import combinations
import re
from typing import Any


DECISIONS = ("ready", "review_required", "block_recommended")
EXECUTIONS = ("pass", "setup_fail", "provider_fail", "tool_fail", "artifact_fail", "timeout")
OUTCOMES = ("aligned", "overcalled", "undercalled", "execution_failure")
LABEL_FIELD_ORDER = ("id", "reviewer", "expected_decision", "rationale", "reviewed_at")
LABEL_FIELDS = set(LABEL_FIELD_ORDER)
ADJUDICATION_FIELD_ORDER = ("id", "adjudicator", "expected_decision", "rationale", "reviewed_at")
ADJUDICATION_FIELDS = set(ADJUDICATION_FIELD_ORDER)


class HoldoutReportingError(ValueError):
    pass


def _is_iso_date(value: object) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def merge_reviewer_packets(
    packets: list[dict[str, Any]],
    *,
    cases_sha256: str,
    predictions_sha256: str,
    case_ids: set[str],
    minimum_reviewers: int,
    minimum_overlap_cases: int,
) -> list[dict[str, str]]:
    labels: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    reviewers: set[str] = set()
    reviewers_by_case: dict[str, set[str]] = defaultdict(set)

    for packet_index, packet in enumerate(packets):
        if packet.get("version") != 1 or packet.get("dataset_role") != "holdout_label_template":
            raise HoldoutReportingError(f"reviewer packet {packet_index} has an invalid role or version")
        if packet.get("cases_sha256") != cases_sha256 or packet.get("predictions_sha256") != predictions_sha256:
            raise HoldoutReportingError(f"reviewer packet {packet_index} is not bound to frozen artifacts")
        raw_labels = packet.get("labels")
        if not isinstance(raw_labels, list) or not raw_labels:
            raise HoldoutReportingError(f"reviewer packet {packet_index} must contain labels")
        packet_reviewers: set[str] = set()
        for label_index, label in enumerate(raw_labels):
            if not isinstance(label, dict) or set(label) != LABEL_FIELDS:
                raise HoldoutReportingError(
                    f"reviewer packet {packet_index} label {label_index} must contain exactly {sorted(LABEL_FIELDS)}"
                )
            case_id = label.get("id")
            reviewer = label.get("reviewer")
            if not isinstance(case_id, str) or case_id not in case_ids:
                raise HoldoutReportingError(f"reviewer packet {packet_index} references an unknown case")
            if not isinstance(reviewer, str) or not reviewer.strip():
                raise HoldoutReportingError(f"reviewer packet {packet_index} requires a reviewer pseudonym")
            if label.get("expected_decision") not in DECISIONS:
                raise HoldoutReportingError(f"reviewer packet {packet_index} label {label_index} is incomplete")
            if not isinstance(label.get("rationale"), str) or not label["rationale"].strip():
                raise HoldoutReportingError(f"reviewer packet {packet_index} label {label_index} requires rationale")
            if not _is_iso_date(label.get("reviewed_at")):
                raise HoldoutReportingError(
                    f"reviewer packet {packet_index} label {label_index} requires reviewed_at as an ISO date"
                )
            pair = (case_id, reviewer)
            if pair in seen_pairs:
                raise HoldoutReportingError(f"duplicate reviewer label for {case_id}/{reviewer}")
            seen_pairs.add(pair)
            packet_reviewers.add(reviewer)
            reviewers.add(reviewer)
            reviewers_by_case[case_id].add(reviewer)
            labels.append({field: label[field] for field in LABEL_FIELD_ORDER})
        if len(packet_reviewers) != 1:
            raise HoldoutReportingError(f"reviewer packet {packet_index} must contain exactly one reviewer")

    missing_cases = sorted(case_ids - set(reviewers_by_case))
    if missing_cases:
        raise HoldoutReportingError(f"every holdout case requires a label; missing {len(missing_cases)}")
    if len(reviewers) < minimum_reviewers:
        raise HoldoutReportingError(f"holdout requires at least {minimum_reviewers} independent reviewers")
    overlap = sum(1 for case_reviewers in reviewers_by_case.values() if len(case_reviewers) >= 2)
    if overlap < minimum_overlap_cases:
        raise HoldoutReportingError(
            f"holdout requires at least {minimum_overlap_cases} double-reviewed cases; found {overlap}"
        )
    return sorted(labels, key=lambda label: (label["id"], label["reviewer"]))


def validate_adjudications(
    packet: dict[str, Any] | None,
    *,
    labels: list[dict[str, str]],
    cases_sha256: str,
    predictions_sha256: str,
) -> list[dict[str, str]]:
    values_by_case: dict[str, set[str]] = defaultdict(set)
    reviewers_by_case: dict[str, set[str]] = defaultdict(set)
    for label in labels:
        values_by_case[label["id"]].add(label["expected_decision"])
        reviewers_by_case[label["id"]].add(label["reviewer"])
    disagreement_ids = {case_id for case_id, values in values_by_case.items() if len(values) > 1}
    if packet is None:
        if disagreement_ids:
            raise HoldoutReportingError(f"adjudication is required for {len(disagreement_ids)} disagreement cases")
        return []
    if packet.get("version") != 1 or packet.get("dataset_role") != "holdout_adjudications":
        raise HoldoutReportingError("adjudication packet has an invalid role or version")
    if packet.get("cases_sha256") != cases_sha256 or packet.get("predictions_sha256") != predictions_sha256:
        raise HoldoutReportingError("adjudication packet is not bound to frozen artifacts")
    raw_adjudications = packet.get("adjudications")
    if not isinstance(raw_adjudications, list):
        raise HoldoutReportingError("adjudication packet must contain an adjudications list")
    adjudications: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for index, adjudication in enumerate(raw_adjudications):
        if not isinstance(adjudication, dict) or set(adjudication) != ADJUDICATION_FIELDS:
            raise HoldoutReportingError(f"adjudication {index} has invalid fields")
        case_id = adjudication.get("id")
        if not isinstance(case_id, str) or case_id not in disagreement_ids or case_id in seen_ids:
            raise HoldoutReportingError(f"adjudication {index} must reference one unique disagreement case")
        if adjudication.get("expected_decision") not in DECISIONS:
            raise HoldoutReportingError(f"adjudication {index} is incomplete")
        for field in ("adjudicator", "rationale"):
            if not isinstance(adjudication.get(field), str) or not adjudication[field].strip():
                raise HoldoutReportingError(f"adjudication {index} requires {field}")
        if adjudication["adjudicator"] in reviewers_by_case[case_id]:
            raise HoldoutReportingError(f"adjudication {index} requires a third-party adjudicator")
        if not _is_iso_date(adjudication.get("reviewed_at")):
            raise HoldoutReportingError(f"adjudication {index} requires reviewed_at as an ISO date")
        seen_ids.add(case_id)
        adjudications.append({field: adjudication[field] for field in ADJUDICATION_FIELD_ORDER})
    if seen_ids != disagreement_ids:
        raise HoldoutReportingError("adjudications must match disagreement cases exactly")
    return sorted(adjudications, key=lambda item: item["id"])


def _cohens_kappa(pairs: list[tuple[str, str]], categories: tuple[str, ...]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected = sum(left_counts[category] * right_counts[category] for category in categories) / len(pairs) ** 2
    if expected == 1.0:
        return None
    return round((observed - expected) / (1.0 - expected), 4)


def build_report(
    *,
    cases_packet: dict[str, Any],
    predictions_packet: dict[str, Any],
    labels_packet: dict[str, Any],
    labels_sha256: str,
) -> dict[str, Any]:
    cases = cases_packet["cases"]
    predictions = predictions_packet["predictions"]
    labels = labels_packet["labels"]
    adjudications = labels_packet.get("adjudications", [])
    predictions_by_id = {prediction["id"]: prediction for prediction in predictions}
    labels_by_case: dict[str, list[dict[str, str]]] = defaultdict(list)
    for label in labels:
        labels_by_case[label["id"]].append(label)
    adjudications_by_id = {item["id"]: item for item in adjudications}

    pairwise_decisions: list[tuple[str, str]] = []
    overlap_cases = 0
    final_labels: dict[str, str] = {}
    for case_id, case_labels in labels_by_case.items():
        ordered = sorted(case_labels, key=lambda item: item["reviewer"])
        if len(ordered) >= 2:
            overlap_cases += 1
            for left, right in combinations(ordered, 2):
                pairwise_decisions.append((left["expected_decision"], right["expected_decision"]))
        values = {label["expected_decision"] for label in ordered}
        if len(values) == 1:
            final_labels[case_id] = next(iter(values))
        else:
            adjudication = adjudications_by_id[case_id]
            final_labels[case_id] = adjudication["expected_decision"]

    confusion = {expected: {actual: 0 for actual in DECISIONS} for expected in DECISIONS}
    outcome_counts = {outcome: 0 for outcome in OUTCOMES}
    execution_counts = {execution: 0 for execution in EXECUTIONS}
    stack_rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {"cases": 0, "execution_failures": 0, "decision_matches": 0, "decision_evaluated": 0}
    )
    for case in cases:
        case_id = case["id"]
        stack = case["stack"]
        prediction = predictions_by_id[case_id]
        expected = final_labels[case_id]
        execution = prediction["execution"]
        execution_counts[execution] += 1
        stack_rows[stack]["cases"] += 1
        if execution != "pass":
            outcome_counts["execution_failure"] += 1
            stack_rows[stack]["execution_failures"] += 1
            continue
        actual = prediction["decision"]
        expected_rank = DECISIONS.index(expected)
        actual_rank = DECISIONS.index(actual)
        if actual_rank == expected_rank:
            outcome_counts["aligned"] += 1
        elif actual_rank > expected_rank:
            outcome_counts["overcalled"] += 1
        else:
            outcome_counts["undercalled"] += 1
        confusion[expected][actual] += 1
        stack_rows[stack]["decision_evaluated"] += 1
        if actual == expected:
            stack_rows[stack]["decision_matches"] += 1

    total = len(cases)
    execution_failures = total - execution_counts["pass"]
    decision_evaluated = sum(sum(row.values()) for row in confusion.values())
    decision_matches = sum(confusion[decision][decision] for decision in DECISIONS)
    pair_count = len(pairwise_decisions)
    report = {
        "version": 1,
        "dataset_role": "holdout_evaluation",
        "cases_sha256": labels_packet["cases_sha256"],
        "predictions_sha256": labels_packet["predictions_sha256"],
        "labels_sha256": labels_sha256,
        "analyzer_commit": predictions_packet["generated_from_commit"],
        "claim_status": "blocked_pending_policy_thresholds",
        "totals": {
            "cases": total,
            "raw_labels": len(labels),
            "reviewers": len({label["reviewer"] for label in labels}),
            "overlap_cases": overlap_cases,
            "adjudicated_cases": len(adjudications),
        },
        "execution": {
            "counts": execution_counts,
            "failure_rate": round(execution_failures / total, 4) if total else 0.0,
        },
        "decision": {
            "confusion_matrix": confusion,
            "evaluated": decision_evaluated,
            "matches": decision_matches,
            "exact_match_rate": round(decision_matches / decision_evaluated, 4) if decision_evaluated else None,
        },
        "outcomes": outcome_counts,
        "agreement": {
            "pairwise_comparisons": pair_count,
            "expected_decision_raw_agreement": (
                round(sum(left == right for left, right in pairwise_decisions) / pair_count, 4)
                if pair_count
                else None
            ),
            "expected_decision_cohens_kappa": _cohens_kappa(pairwise_decisions, DECISIONS),
        },
        "stacks": dict(sorted(stack_rows.items())),
    }
    return report


def render_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Independent Holdout Evaluation",
        "",
        f"- Analyzer commit: `{report['analyzer_commit']}`",
        f"- Cases: `{report['totals']['cases']}`",
        f"- Reviewers: `{report['totals']['reviewers']}`",
        f"- Overlap cases: `{report['totals']['overlap_cases']}`",
        f"- Adjudicated cases: `{report['totals']['adjudicated_cases']}`",
        f"- Claim status: `{report['claim_status']}`",
        "",
        "## Execution",
        "",
        f"- Failure rate: `{report['execution']['failure_rate']:.2%}`",
    ]
    for execution, count in report["execution"]["counts"].items():
        lines.append(f"- {execution}: `{count}`")
    exact_match_rate = report["decision"]["exact_match_rate"]
    lines.extend(
        [
            "",
            "## Decision agreement",
            "",
            f"- Evaluated: `{report['decision']['evaluated']}`",
            f"- Exact match rate: `{exact_match_rate:.2%}`" if exact_match_rate is not None else "- Exact match rate: `n/a`",
            "",
            "| Expected / Actual | ready | review_required | block_recommended |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for expected in DECISIONS:
        row = report["decision"]["confusion_matrix"][expected]
        lines.append(
            f"| {expected} | {row['ready']} | {row['review_required']} | {row['block_recommended']} |"
        )
    lines.extend(["", "## Reviewer agreement", ""])
    for key, value in report["agreement"].items():
        rendered = "n/a" if value is None else f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"- {key}: `{rendered}`")
    lines.extend(["", "## Outcomes", ""])
    for outcome, count in report["outcomes"].items():
        lines.append(f"- {outcome}: `{count}`")
    lines.extend(["", "## Stacks", "", "| Stack | Cases | Failures | Decision matches | Evaluated |", "| --- | ---: | ---: | ---: | ---: |"])
    for stack, row in report["stacks"].items():
        lines.append(
            f"| {stack} | {row['cases']} | {row['execution_failures']} | "
            f"{row['decision_matches']} | {row['decision_evaluated']} |"
        )
    lines.extend(
        [
            "",
            "This report does not unblock accuracy claims. Release thresholds and confidence requirements must be approved separately.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "ADJUDICATION_FIELDS",
    "DECISIONS",
    "EXECUTIONS",
    "HoldoutReportingError",
    "LABEL_FIELDS",
    "OUTCOMES",
    "build_report",
    "merge_reviewer_packets",
    "render_report_markdown",
    "validate_adjudications",
]
