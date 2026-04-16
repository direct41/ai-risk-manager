from __future__ import annotations

from pathlib import Path
import shutil

from ai_risk_manager.profiles.ui_flow_smoke import load_ui_smoke_manifest


def _load_example(example_path: Path, tmp_path: Path):
    target = tmp_path / ".riskmap-ui.toml"
    shutil.copyfile(example_path, target)
    manifest, notes = load_ui_smoke_manifest(tmp_path)
    assert manifest is not None, notes
    return manifest


def test_root_ui_smoke_example_is_valid(tmp_path: Path) -> None:
    manifest = _load_example(Path("examples/ui/.riskmap-ui.toml"), tmp_path)

    journey_ids = {journey.id for journey in manifest.journeys}

    assert {"app_shell", "login"} <= journey_ids
    assert all(journey.command for journey in manifest.journeys)


def test_nuxt_ui_smoke_example_is_valid(tmp_path: Path) -> None:
    manifest = _load_example(Path("examples/ui/nuxt/.riskmap-ui.toml"), tmp_path)

    journeys = {journey.id: journey for journey in manifest.journeys}

    assert set(journeys) == {"checkout", "product", "cart"}
    assert "checkout" in journeys["checkout"].match
    assert "product/[slug]" in journeys["product"].match
    assert "cartmodal" in journeys["cart"].match
    assert all(journey.command[:3] == ["pnpm", "exec", "playwright"] for journey in manifest.journeys)
