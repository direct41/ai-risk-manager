from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shlex
import subprocess
import tomllib

from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle, SignalKind

_MANIFEST_PATH = ".riskmap-ui.toml"


@dataclass
class UiSmokeJourney:
    id: str
    match: list[str]
    command: list[str]


@dataclass
class UiSmokeManifest:
    path: Path
    journeys: list[UiSmokeJourney] = field(default_factory=list)


@dataclass
class UiSmokeRunResult:
    signals: SignalBundle
    notes: list[str]


def _clean_token(value: str) -> str:
    return value.strip().lower().replace("\\", "/")


def _journey_tokens(journey: str) -> set[str]:
    normalized = _clean_token(journey).replace("/", "_").replace("-", "_")
    return {chunk for chunk in normalized.split("_") if chunk}


def load_ui_smoke_manifest(repo_path: Path) -> tuple[UiSmokeManifest | None, list[str]]:
    path = repo_path / _MANIFEST_PATH
    if not path.is_file():
        return None, []

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None, [f"ui_flow_risk could not parse {_MANIFEST_PATH}; browser smoke skipped."]

    raw_journeys = payload.get("journeys")
    if not isinstance(raw_journeys, list):
        return None, [f"ui_flow_risk found {_MANIFEST_PATH} without [[journeys]] entries; browser smoke skipped."]

    journeys: list[UiSmokeJourney] = []
    for index, raw in enumerate(raw_journeys, start=1):
        if not isinstance(raw, dict):
            continue
        journey_id = str(raw.get("id", "")).strip()
        raw_match = raw.get("match", [])
        raw_command = raw.get("command", [])
        if not journey_id or not isinstance(raw_match, list) or not isinstance(raw_command, list):
            continue
        match = [str(item).strip() for item in raw_match if str(item).strip()]
        command = [str(item) for item in raw_command if str(item)]
        if not command:
            continue
        journeys.append(UiSmokeJourney(id=journey_id, match=match or [journey_id], command=command))

    if not journeys:
        return None, [f"ui_flow_risk found {_MANIFEST_PATH} but no valid journey definitions; browser smoke skipped."]
    return UiSmokeManifest(path=path, journeys=journeys), [f"ui_flow_risk loaded {len(journeys)} declared smoke journey(s)."]


def _select_journeys(manifest: UiSmokeManifest, changed_journeys: list[str]) -> list[tuple[UiSmokeJourney, str]]:
    selected: list[tuple[UiSmokeJourney, str]] = []
    seen: set[tuple[str, str]] = set()
    for changed in changed_journeys:
        changed_tokens = _journey_tokens(changed)
        if not changed_tokens:
            continue
        for journey in manifest.journeys:
            journey_tokens = set()
            for token in journey.match:
                journey_tokens.update(_journey_tokens(token))
            journey_tokens.update(_journey_tokens(journey.id))
            if not journey_tokens or not (changed_tokens & journey_tokens):
                continue
            key = (journey.id, changed)
            if key in seen:
                continue
            selected.append((journey, changed))
            seen.add(key)
    return selected


def _render_command(template: list[str], *, journey_id: str, changed_journey: str) -> list[str]:
    return [
        part.replace("{journey_id}", journey_id).replace("{changed_journey}", changed_journey)
        for part in template
    ]


def _output_excerpt(proc: subprocess.CompletedProcess[str] | None, exc: Exception | None = None) -> str:
    if exc is not None:
        return str(exc).strip()[:240]
    if proc is None:
        return ""
    combined = "\n".join(part.strip() for part in (proc.stdout, proc.stderr) if part and part.strip())
    return combined[:240]


def run_ui_smoke(
    *,
    repo_path: Path,
    manifest: UiSmokeManifest | None,
    changed_journeys: list[str],
    evidence_refs: dict[str, list[str]],
) -> UiSmokeRunResult:
    if manifest is None or not changed_journeys:
        return UiSmokeRunResult(signals=SignalBundle(), notes=[])

    selected = _select_journeys(manifest, changed_journeys)
    if not selected:
        return UiSmokeRunResult(
            signals=SignalBundle(),
            notes=["ui_flow_risk found no declared browser smoke mapped to changed journeys."],
        )

    notes: list[str] = []
    signals: list[CapabilitySignal] = []
    supported_kinds: set[SignalKind] = {"ui_journey_smoke"}
    for journey, changed_journey in selected:
        command = _render_command(journey.command, journey_id=journey.id, changed_journey=changed_journey)
        command_display = " ".join(shlex.quote(part) for part in command)
        proc: subprocess.CompletedProcess[str] | None = None
        exc: Exception | None = None
        try:
            proc = subprocess.run(
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as err:
            exc = err

        if exc is None and proc is not None and proc.returncode == 0:
            notes.append(f"ui_flow_risk smoke passed for journey '{journey.id}' via `{command_display}`.")
            continue

        refs = list(evidence_refs.get(changed_journey, []))
        if str(manifest.path.relative_to(repo_path)) not in refs:
            refs.append(str(manifest.path.relative_to(repo_path)))
        source_ref = refs[0] if refs else str(manifest.path.relative_to(repo_path))
        exit_code = None if exc is not None else proc.returncode if proc is not None else None
        notes.append(f"ui_flow_risk smoke failed for journey '{journey.id}' via `{command_display}`.")
        signals.append(
            CapabilitySignal(
                id=f"sig:ui-smoke:{journey.id}:{changed_journey}",
                kind="ui_journey_smoke",
                source_ref=source_ref,
                confidence="high" if exit_code not in {None, 0} else "medium",
                evidence_refs=refs,
                attributes={
                    "issue_type": "journey_smoke_failed",
                    "journey_id": journey.id,
                    "changed_journey": changed_journey,
                    "command": command_display,
                    "exit_code": exit_code,
                    "output_excerpt": _output_excerpt(proc, exc),
                },
            )
        )

    return UiSmokeRunResult(
        signals=SignalBundle(signals=signals, supported_kinds=supported_kinds if signals else set()),
        notes=notes,
    )


__all__ = ["UiSmokeJourney", "UiSmokeManifest", "UiSmokeRunResult", "load_ui_smoke_manifest", "run_ui_smoke"]
