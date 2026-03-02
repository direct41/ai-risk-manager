from __future__ import annotations

import json

from ai_risk_manager.schemas.types import Confidence
from ai_risk_manager.signals.types import CapabilitySignal, SignalBundle, SignalKind

CONFIDENCE_RANK: dict[Confidence, int] = {"low": 1, "medium": 2, "high": 3}


def _signal_key(signal: CapabilitySignal) -> str:
    return "|".join(
        [
            signal.kind,
            signal.source_ref,
            json.dumps(signal.attributes, ensure_ascii=False, sort_keys=True),
        ]
    )


def _meets_min_confidence(confidence: Confidence, min_confidence: Confidence) -> bool:
    return CONFIDENCE_RANK[confidence] >= CONFIDENCE_RANK[min_confidence]


def _merge_signal(existing: CapabilitySignal, incoming: CapabilitySignal) -> CapabilitySignal:
    if CONFIDENCE_RANK[incoming.confidence] > CONFIDENCE_RANK[existing.confidence]:
        winner = incoming
        loser = existing
    else:
        winner = existing
        loser = incoming
    merged_refs = sorted({*winner.evidence_refs, *loser.evidence_refs})
    merged_tags = sorted({*winner.tags, *loser.tags})
    return CapabilitySignal(
        id=winner.id,
        kind=winner.kind,
        source_ref=winner.source_ref,
        confidence=winner.confidence,
        evidence_refs=merged_refs,
        attributes=winner.attributes,
        tags=merged_tags,
        origin=winner.origin,
    )


def merge_signal_bundles(*bundles: SignalBundle, min_confidence: Confidence = "low") -> SignalBundle:
    merged: dict[str, CapabilitySignal] = {}
    supported_kinds: set[SignalKind] = set()

    for bundle in bundles:
        supported_kinds.update(bundle.supported_kinds)
        for signal in bundle.signals:
            if not _meets_min_confidence(signal.confidence, min_confidence):
                continue
            key = _signal_key(signal)
            existing = merged.get(key)
            merged[key] = signal if existing is None else _merge_signal(existing, signal)

    return SignalBundle(signals=list(merged.values()), supported_kinds=supported_kinds)
