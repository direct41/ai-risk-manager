from __future__ import annotations

from ai_risk_manager.collectors.plugins.base import ArtifactBundle
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle, SignalKind


def _line_ref(file_path: str, line: int | None) -> str:
    if line is None:
        return file_path
    return f"{file_path}:{line}"


def artifact_bundle_to_signal_bundle(artifacts: ArtifactBundle) -> SignalBundle:
    signals: list[CapabilitySignal] = []
    supported_kinds: set[SignalKind] = set()

    for file_path, endpoint_name, method, route_path, line, snippet in artifacts.write_endpoints:
        supported_kinds.add("http_write_surface")
        signals.append(
            CapabilitySignal(
                id=f"sig:http:{file_path}:{endpoint_name}:{line or 0}",
                kind="http_write_surface",
                source_ref=_line_ref(file_path, line),
                confidence="high",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "endpoint_name": endpoint_name,
                    "method": method.upper(),
                    "path": route_path,
                    "snippet": snippet,
                },
            )
        )

    model_sources = {model_name: model_file for model_file, model_name in artifacts.pydantic_models}
    for file_path, endpoint_name, model_name in artifacts.endpoint_models:
        supported_kinds.add("request_contract_binding")
        evidence = [file_path]
        model_source = model_sources.get(model_name)
        if model_source:
            evidence.append(model_source)
        signals.append(
            CapabilitySignal(
                id=f"sig:contract:{file_path}:{endpoint_name}:{model_name}",
                kind="request_contract_binding",
                source_ref=file_path,
                confidence="medium",
                evidence_refs=evidence,
                attributes={
                    "endpoint_name": endpoint_name,
                    "model_name": model_name,
                    "model_source": model_source,
                },
            )
        )

    for file_path, machine, src, dst, line, snippet in artifacts.declared_transitions:
        supported_kinds.add("state_transition_declared")
        signals.append(
            CapabilitySignal(
                id=f"sig:transition:declared:{file_path}:{machine}:{src}:{dst}:{line or 0}",
                kind="state_transition_declared",
                source_ref=_line_ref(file_path, line),
                confidence="high",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "machine": machine,
                    "source_state": src,
                    "target_state": dst,
                    "snippet": snippet,
                },
            )
        )

    for file_path, machine, src, dst, line, snippet, invariant_guarded in artifacts.handled_transitions:
        supported_kinds.add("state_transition_handled_guarded")
        signals.append(
            CapabilitySignal(
                id=f"sig:transition:handled:{file_path}:{machine}:{src}:{dst}:{line or 0}",
                kind="state_transition_handled_guarded",
                source_ref=_line_ref(file_path, line),
                confidence="high" if invariant_guarded else "medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "machine": machine,
                    "source_state": src,
                    "target_state": dst,
                    "invariant_guarded": invariant_guarded,
                    "snippet": snippet,
                },
            )
        )

    for file_path, test_name, method, route_path, line, snippet in artifacts.test_http_calls:
        supported_kinds.add("test_to_endpoint_coverage")
        signals.append(
            CapabilitySignal(
                id=f"sig:coverage:http:{file_path}:{test_name}:{line or 0}",
                kind="test_to_endpoint_coverage",
                source_ref=_line_ref(file_path, line),
                confidence="high",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "test_name": test_name,
                    "method": method.upper(),
                    "path": route_path,
                    "snippet": snippet,
                },
            )
        )

    for file_path, test_name, line, snippet in artifacts.test_cases:
        supported_kinds.add("test_to_endpoint_coverage")
        signals.append(
            CapabilitySignal(
                id=f"sig:coverage:test:{file_path}:{test_name}:{line or 0}",
                kind="test_to_endpoint_coverage",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "test_name": test_name,
                    "snippet": snippet,
                    "coverage_mode": "name_fallback_candidate",
                },
            )
        )

    for file_path, dep_name, raw_spec, line, policy_violation, scope in artifacts.dependency_specs:
        supported_kinds.add("dependency_version_policy")
        signals.append(
            CapabilitySignal(
                id=f"sig:dependency:{file_path}:{dep_name}:{line or 0}",
                kind="dependency_version_policy",
                source_ref=_line_ref(file_path, line),
                confidence="high",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "dependency_name": dep_name,
                    "spec": raw_spec,
                    "policy_violation": policy_violation,
                    "scope": scope,
                },
            )
        )

    for file_path, endpoint_name, effect_kind, effect_target, line, snippet in artifacts.side_effect_requirements:
        supported_kinds.add("side_effect_emit_contract")
        signals.append(
            CapabilitySignal(
                id=f"sig:side_effect:required:{file_path}:{endpoint_name}:{effect_kind}:{effect_target}:{line or 0}",
                kind="side_effect_emit_contract",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "role": "required",
                    "owner_name": endpoint_name,
                    "effect_kind": effect_kind,
                    "effect_target": effect_target,
                    "snippet": snippet,
                },
            )
        )

    for file_path, emitter_name, effect_kind, effect_target, line, snippet in artifacts.side_effect_emits:
        supported_kinds.add("side_effect_emit_contract")
        signals.append(
            CapabilitySignal(
                id=f"sig:side_effect:emitted:{file_path}:{emitter_name}:{effect_kind}:{effect_target}:{line or 0}",
                kind="side_effect_emit_contract",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "role": "emitted",
                    "owner_name": emitter_name,
                    "effect_kind": effect_kind,
                    "effect_target": effect_target,
                    "snippet": snippet,
                },
            )
        )

    for file_path, endpoint_name, auth_mechanism, auth_subject, line, snippet in artifacts.authorization_boundaries:
        supported_kinds.add("authorization_boundary_enforced")
        signals.append(
            CapabilitySignal(
                id=f"sig:authz:{file_path}:{endpoint_name}:{auth_mechanism}:{auth_subject}:{line or 0}",
                kind="authorization_boundary_enforced",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "owner_name": endpoint_name,
                    "auth_mechanism": auth_mechanism,
                    "auth_subject": auth_subject,
                    "snippet": snippet,
                },
            )
        )

    for file_path, issue_type, owner_name, line, snippet, details in artifacts.write_contract_issues:
        supported_kinds.add("write_contract_integrity")
        signals.append(
            CapabilitySignal(
                id=f"sig:write_contract:{file_path}:{issue_type}:{owner_name}:{line or 0}",
                kind="write_contract_integrity",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "issue_type": issue_type,
                    "owner_name": owner_name,
                    "snippet": snippet,
                    **details,
                },
            )
        )

    for file_path, issue_type, owner_name, line, snippet, details in artifacts.session_lifecycle_issues:
        supported_kinds.add("session_lifecycle_consistency")
        signals.append(
            CapabilitySignal(
                id=f"sig:session:{file_path}:{issue_type}:{owner_name}:{line or 0}",
                kind="session_lifecycle_consistency",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "issue_type": issue_type,
                    "owner_name": owner_name,
                    "snippet": snippet,
                    **details,
                },
            )
        )

    for file_path, issue_type, owner_name, line, snippet, details in artifacts.html_render_issues:
        supported_kinds.add("html_render_safety")
        signals.append(
            CapabilitySignal(
                id=f"sig:html:{file_path}:{issue_type}:{owner_name}:{line or 0}",
                kind="html_render_safety",
                source_ref=_line_ref(file_path, line),
                confidence="high",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "issue_type": issue_type,
                    "owner_name": owner_name,
                    "snippet": snippet,
                    **details,
                },
            )
        )

    for file_path, issue_type, owner_name, line, snippet, details in artifacts.ui_ergonomics_issues:
        supported_kinds.add("ui_ergonomics")
        signals.append(
            CapabilitySignal(
                id=f"sig:ui:{file_path}:{issue_type}:{owner_name}:{line or 0}",
                kind="ui_ergonomics",
                source_ref=_line_ref(file_path, line),
                confidence="medium",
                evidence_refs=[_line_ref(file_path, line)],
                attributes={
                    "issue_type": issue_type,
                    "owner_name": owner_name,
                    "snippet": snippet,
                    **details,
                },
            )
        )

    return SignalBundle(signals=signals, supported_kinds=supported_kinds)
