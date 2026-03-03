from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
from typing import Literal, cast

from ai_risk_manager.schemas.types import Finding, FindingsReport, Severity

PolicyGate = Literal["default", "never_block"]
_POLICY_VERSION = 1
_SEVERITIES: set[str] = {"critical", "high", "medium", "low"}
_GATES: set[str] = {"default", "never_block"}


@dataclass(frozen=True)
class RulePolicy:
    enabled: bool = True
    severity: Severity | None = None
    gate: PolicyGate = "default"


@dataclass(frozen=True)
class PolicyConfig:
    version: int = _POLICY_VERSION
    rules: dict[str, RulePolicy] = field(default_factory=dict)


def _default_policy() -> PolicyConfig:
    return PolicyConfig()


def load_policy(path: Path | None) -> tuple[PolicyConfig, list[str]]:
    if path is None or not path.is_file():
        return _default_policy(), []

    notes: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        notes.append(f"Ignoring invalid policy file at {path}: {exc.__class__.__name__}.")
        return _default_policy(), notes

    if not isinstance(payload, dict):
        notes.append(f"Ignoring invalid policy file at {path}: top-level object is required.")
        return _default_policy(), notes

    version = payload.get("version", _POLICY_VERSION)
    if not isinstance(version, int) or version != _POLICY_VERSION:
        notes.append(f"Ignoring invalid policy version in {path}: expected version={_POLICY_VERSION}.")
        return _default_policy(), notes

    raw_rules = payload.get("rules", {})
    if not isinstance(raw_rules, dict):
        notes.append(f"Ignoring invalid policy rules section in {path}: object is required.")
        return _default_policy(), notes

    rules: dict[str, RulePolicy] = {}
    for rule_id, raw_rule in raw_rules.items():
        if not isinstance(rule_id, str) or not rule_id.strip():
            notes.append(f"Ignoring policy rule with invalid id in {path}.")
            continue
        if not isinstance(raw_rule, dict):
            notes.append(f"Ignoring policy rule '{rule_id}' in {path}: object is required.")
            continue

        enabled = raw_rule.get("enabled", True)
        if not isinstance(enabled, bool):
            notes.append(f"Ignoring policy field rules.{rule_id}.enabled in {path}: boolean is required.")
            enabled = True

        severity_raw = raw_rule.get("severity")
        severity: Severity | None = None
        if severity_raw is not None:
            if isinstance(severity_raw, str) and severity_raw in _SEVERITIES:
                severity = cast(Severity, severity_raw)
            else:
                notes.append(
                    f"Ignoring policy field rules.{rule_id}.severity in {path}: one of {sorted(_SEVERITIES)} is required."
                )

        gate_raw = raw_rule.get("gate", "default")
        if not isinstance(gate_raw, str) or gate_raw not in _GATES:
            notes.append(f"Ignoring policy field rules.{rule_id}.gate in {path}: one of {sorted(_GATES)} is required.")
            gate_raw = "default"

        rules[rule_id] = RulePolicy(enabled=enabled, severity=severity, gate=cast(PolicyGate, gate_raw))

    if rules:
        notes.append(f"Loaded policy from {path}: {len(rules)} rule override(s).")
    return PolicyConfig(version=version, rules=rules), notes


def apply_policy(findings: FindingsReport, policy: PolicyConfig) -> tuple[FindingsReport, int, int]:
    filtered: list[Finding] = []
    dropped = 0
    severity_overrides = 0
    for finding in findings.findings:
        rule_policy = policy.rules.get(finding.rule_id)
        if rule_policy is not None and not rule_policy.enabled:
            dropped += 1
            continue

        next_finding = finding
        if rule_policy is not None and rule_policy.severity is not None and rule_policy.severity != finding.severity:
            next_finding = replace(finding, severity=rule_policy.severity)
            severity_overrides += 1
        filtered.append(next_finding)

    return FindingsReport(findings=filtered, generated_without_llm=findings.generated_without_llm), dropped, severity_overrides


def is_blocking_enabled_for_finding(policy: PolicyConfig, finding: Finding) -> bool:
    rule_policy = policy.rules.get(finding.rule_id)
    if rule_policy is None:
        return True
    if not rule_policy.enabled:
        return False
    return rule_policy.gate != "never_block"
