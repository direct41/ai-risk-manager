from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass(frozen=True)
class TrustOutcomeCounts:
    accepted_count: int = 0
    suppressed_count: int = 0
    actioned_count: int = 0


@dataclass(frozen=True)
class TrustOutcomes:
    by_fingerprint: dict[str, TrustOutcomeCounts] = field(default_factory=dict)
    by_rule_id: dict[str, TrustOutcomeCounts] = field(default_factory=dict)

    def lookup(self, *, fingerprint: str, rule_id: str) -> TrustOutcomeCounts:
        if fingerprint and fingerprint in self.by_fingerprint:
            return self.by_fingerprint[fingerprint]
        return self.by_rule_id.get(rule_id, TrustOutcomeCounts())


def _parse_counts(value: object) -> TrustOutcomeCounts | None:
    if not isinstance(value, dict):
        return None
    accepted = value.get("accepted_count", 0)
    suppressed = value.get("suppressed_count", 0)
    actioned = value.get("actioned_count", 0)
    if not all(isinstance(item, int) and item >= 0 for item in (accepted, suppressed, actioned)):
        return None
    return TrustOutcomeCounts(
        accepted_count=accepted,
        suppressed_count=suppressed,
        actioned_count=actioned,
    )


def load_trust_outcomes(path: Path | None) -> tuple[TrustOutcomes, list[str]]:
    if path is None or not path.is_file():
        return TrustOutcomes(), []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return TrustOutcomes(), [f"Trust outcomes file ignored: could not parse {path.name}."]

    if not isinstance(payload, dict):
        return TrustOutcomes(), [f"Trust outcomes file ignored: invalid payload in {path.name}."]

    by_fingerprint_raw = payload.get("by_fingerprint", {})
    by_rule_id_raw = payload.get("by_rule_id", {})
    if not isinstance(by_fingerprint_raw, dict) or not isinstance(by_rule_id_raw, dict):
        return TrustOutcomes(), [f"Trust outcomes file ignored: invalid maps in {path.name}."]

    by_fingerprint: dict[str, TrustOutcomeCounts] = {}
    for key, value in by_fingerprint_raw.items():
        counts = _parse_counts(value)
        if isinstance(key, str) and counts is not None:
            by_fingerprint[key] = counts

    by_rule_id: dict[str, TrustOutcomeCounts] = {}
    for key, value in by_rule_id_raw.items():
        counts = _parse_counts(value)
        if isinstance(key, str) and counts is not None:
            by_rule_id[key] = counts

    notes = [f"Loaded trust outcomes from {path.name}."] if by_fingerprint or by_rule_id else []
    return TrustOutcomes(by_fingerprint=by_fingerprint, by_rule_id=by_rule_id), notes


__all__ = ["TrustOutcomeCounts", "TrustOutcomes", "load_trust_outcomes"]
