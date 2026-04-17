from __future__ import annotations

from pathlib import Path

from ai_risk_manager.profiles.registry import get_profile, list_profile_ids
from ai_risk_manager.schemas.types import RunContext
from ai_risk_manager.stacks.discovery import StackDetectionResult, detect_stack


def test_profile_registry_lists_code_risk_only() -> None:
    assert list_profile_ids() == ("code_risk", "ui_flow_risk", "business_invariant_risk")


def test_code_risk_prepare_supported_repo(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "app" / "api.py",
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.post('/orders')\n"
        "def create_order():\n"
        "    return {'ok': True}\n",
    )

    profile = get_profile("code_risk")
    assert profile is not None

    prepared, exit_code = profile.prepare(
        RunContext(
            repo_path=tmp_path,
            mode="full",
            base=None,
            output_dir=tmp_path / ".riskmap",
            provider="auto",
            no_llm=True,
        ),
        [],
        detection=detect_stack(tmp_path),
    )

    assert exit_code is None
    assert prepared is not None
    assert prepared.profile_id == "code_risk"
    assert prepared.applicability == "supported"
    assert prepared.detection.stack_id == "fastapi_pytest"
    assert prepared.plugin is not None


def test_code_risk_prepare_unknown_repo_falls_back_to_partial(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "def hello():\n    return 'ok'\n")

    profile = get_profile("code_risk")
    assert profile is not None

    prepared, exit_code = profile.prepare(
        RunContext(
            repo_path=tmp_path,
            mode="full",
            base=None,
            output_dir=tmp_path / ".riskmap",
            provider="auto",
            no_llm=True,
            support_level="auto",
        ),
        [],
        detection=StackDetectionResult(stack_id="unknown", confidence="low", reasons=["unknown stack"]),
    )

    assert exit_code is None
    assert prepared is not None
    assert prepared.profile_id == "code_risk"
    assert prepared.applicability == "partial"
    assert prepared.detection.stack_id == "unknown"
    assert prepared.plugin is None
    assert prepared.preflight.status == "WARN"
    assert prepared.support_level_applied == "l0"


def test_ui_flow_prepare_marks_api_only_repo_not_applicable(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "app.py", "def hello():\n    return 'ok'\n")

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)

    assert prepared.profile_id == "ui_flow_risk"
    assert prepared.applicability == "not_applicable"
    assert prepared.framework is None


def test_ui_flow_prepare_detects_web_ui_surface(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / "package.json",
        '{"dependencies":{"react":"18.0.0","react-dom":"18.0.0"},"devDependencies":{"vite":"5.0.0"}}',
    )
    write_file(tmp_path / "src" / "pages" / "checkout.tsx", "export default function CheckoutPage() { return null; }\n")

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)
    focus, notes = profile.describe_changed_scope(prepared, tmp_path, {"src/pages/checkout.tsx"})

    assert prepared.applicability == "partial"
    assert prepared.framework in {"react", "frontend"}
    assert any("changed UI journeys" in item for item in focus)
    assert any("ui_flow_risk detected" in note for note in notes)


def test_ui_flow_prepare_detects_vanilla_public_ui_surface(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "package.json", '{"dependencies":{"express":"4.19.2"}}')
    write_file(tmp_path / "public" / "index.html", "<!doctype html><div id=\"app\"></div>\n")
    write_file(tmp_path / "public" / "app.js", "document.getElementById('app').textContent = 'ok';\n")
    write_file(tmp_path / "public" / "styles.css", "body { font-family: sans-serif; }\n")

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)
    assessment = profile.assess_changed_scope(
        prepared,
        tmp_path,
        {"public/index.html", "public/app.js", "public/styles.css"},
    )

    assert prepared.applicability == "partial"
    assert prepared.framework == "vanilla"
    assert "app_shell" in assessment.changed_journeys
    assert any("Review changed UI journeys: `app_shell`." == item for item in assessment.review_focus)


def test_ui_flow_prepare_ignores_lone_static_asset_without_shell(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "package.json", '{"dependencies":{"express":"4.19.2"}}')
    write_file(tmp_path / "public" / "app.js", "console.log('asset only');\n")

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)

    assert prepared.applicability == "not_applicable"


def test_business_invariant_profile_is_not_applicable_without_spec(tmp_path: Path) -> None:
    profile = get_profile("business_invariant_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path, [])

    assert prepared.profile_id == "business_invariant_risk"
    assert prepared.applicability == "not_applicable"


def test_business_invariant_profile_detects_explicit_spec(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / ".riskmap.yml",
        "critical_flows:\n"
        "  - id: checkout\n"
        "state_invariants:\n"
        "  - id: paid_orders_are_immutable\n",
    )
    notes: list[str] = []

    profile = get_profile("business_invariant_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path, notes)

    assert prepared.applicability == "partial"
    assert prepared.spec_path == ".riskmap.yml"
    assert any("explicit invariant spec" in note for note in notes)


def test_business_invariant_profile_treats_any_explicit_spec_as_partial(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / ".riskmap.yml", "random_config:\n  enabled: true\n")
    notes: list[str] = []

    profile = get_profile("business_invariant_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path, notes)

    assert prepared.applicability == "partial"
    assert prepared.spec_path == ".riskmap.yml"
    assert any("explicit invariant spec" in note for note in notes)


def test_business_invariant_profile_flags_critical_flow_without_check_delta(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / ".riskmap.yml",
        "critical_flows:\n"
        "  - id: checkout\n"
        "    match: [checkout, billing]\n"
        "    checks: [checkout]\n",
    )
    profile = get_profile("business_invariant_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path, [])
    assessment = profile.assess_changed_scope(prepared, tmp_path, {"src/checkout/service.py"})

    assert len(assessment.signals.signals) == 1
    signal = assessment.signals.signals[0]
    assert signal.kind == "business_invariant_risk"
    assert signal.attributes["flow_id"] == "checkout"
    assert any("loaded 1 critical flow" in note for note in assessment.notes)


def test_business_invariant_profile_accepts_matching_check_delta(tmp_path: Path, write_file) -> None:
    write_file(
        tmp_path / ".riskmap.yml",
        "critical_flows:\n"
        "  - id: checkout\n"
        "    match: [checkout, billing]\n"
        "    checks: [checkout]\n",
    )
    profile = get_profile("business_invariant_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path, [])
    assessment = profile.assess_changed_scope(
        prepared,
        tmp_path,
        {"src/checkout/service.py", "tests/e2e/checkout.spec.ts"},
    )

    assert assessment.signals.signals == []


def test_ui_flow_labels_nuxt_app_pages_without_vue_suffix(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "package.json", '{"dependencies":{"nuxt":"4.2.0","vue":"3.5.0"}}')
    write_file(tmp_path / "app" / "pages" / "checkout" / "index.vue", "<template><main>checkout</main></template>\n")
    write_file(
        tmp_path / "app" / "components" / "product" / "ProductGallery.vue",
        "<template><div>gallery</div></template>\n",
    )

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)
    assessment = profile.assess_changed_scope(
        prepared,
        tmp_path,
        {
            "app/pages/checkout/index.vue",
            "app/components/product/ProductGallery.vue",
        },
    )

    assert prepared.applicability == "partial"
    assert assessment.changed_journeys == ["checkout"]
    assert "Review changed UI journeys: `checkout`." in assessment.review_focus
    assert "Review shared UI components affecting: `product/productgallery`." in assessment.review_focus


def test_ui_flow_labels_nuxt_pages_and_components_without_extension_tokens(tmp_path: Path, write_file) -> None:
    write_file(tmp_path / "package.json", '{"dependencies":{"nuxt":"3.0.0","vue":"3.4.0"}}')
    write_file(tmp_path / "pages" / "product" / "[slug].vue", "<template><main>product</main></template>\n")
    write_file(tmp_path / "components" / "CartModal.vue", "<template><aside>cart</aside></template>\n")

    profile = get_profile("ui_flow_risk")
    assert profile is not None

    prepared = profile.prepare(tmp_path)
    assessment = profile.assess_changed_scope(
        prepared,
        tmp_path,
        {
            "pages/product/[slug].vue",
            "components/CartModal.vue",
        },
    )

    assert assessment.changed_journeys == ["product/[slug]"]
    assert "Review changed UI journeys: `product/[slug]`." in assessment.review_focus
    assert "Review shared UI components affecting: `cartmodal`." in assessment.review_focus
