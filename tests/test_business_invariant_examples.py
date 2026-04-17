from __future__ import annotations

from pathlib import Path
import shutil

from ai_risk_manager.profiles.business_invariant import BusinessInvariantProfile


def test_business_invariant_example_enables_profile(tmp_path: Path) -> None:
    shutil.copyfile(Path("examples/business-invariants/.riskmap.yml"), tmp_path / ".riskmap.yml")
    notes: list[str] = []

    profile = BusinessInvariantProfile()
    prepared = profile.prepare(tmp_path, notes)
    assessment = profile.assess_changed_scope(prepared, tmp_path, {"src/checkout/service.py"})

    assert prepared.applicability == "partial"
    assert any("explicit invariant spec" in note for note in notes)
    assert len(assessment.signals.signals) == 1
    assert assessment.signals.signals[0].attributes["flow_id"] == "checkout"
