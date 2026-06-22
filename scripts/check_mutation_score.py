from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ZERO_TOLERANCE_STATUSES = ("no_tests", "suspicious", "timeout", "segfault", "check_was_interrupted_by_user")


def evaluate_stats(payload: object, threshold: float) -> tuple[float | None, list[str]]:
    if not isinstance(payload, dict):
        return None, ["mutation stats must be a JSON object"]
    required = {"killed", "survived", "total", "skipped", *ZERO_TOLERANCE_STATUSES}
    invalid = sorted(
        key
        for key in required
        if not isinstance(payload.get(key), int) or isinstance(payload.get(key), bool) or payload[key] < 0
    )
    if invalid:
        return None, [f"mutation stats require non-negative integer fields: {', '.join(invalid)}"]
    total = payload["total"]
    if total < 1:
        return None, ["mutation stats total must be positive"]
    accounted = payload["killed"] + payload["survived"] + payload["skipped"] + sum(
        payload[status] for status in ZERO_TOLERANCE_STATUSES
    )
    if accounted != total:
        return None, [f"mutation stats do not account for all mutants: total={total}, accounted={accounted}"]

    score = payload["killed"] / total
    errors = [f"mutation score {score:.2%} is below required threshold {threshold:.2%}"] if score < threshold else []
    for status in ZERO_TOLERANCE_STATUSES:
        if payload[status]:
            errors.append(f"mutation run has {payload[status]} {status} mutant(s)")
    return score, errors


def _read_stats(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read mutation stats: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("mutation stats must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce mutation score and mutation-run integrity.")
    parser.add_argument("stats", type=Path)
    parser.add_argument("--threshold", type=float, default=0.75)
    args = parser.parse_args(argv)
    if not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    try:
        payload = _read_stats(args.stats)
    except ValueError as exc:
        print(f"Mutation gate failed: {exc}")
        return 2
    score, errors = evaluate_stats(payload, args.threshold)
    if errors:
        print("Mutation gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    assert score is not None
    print(f"Mutation gate passed: {payload['killed']}/{payload['total']} killed ({score:.2%}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
