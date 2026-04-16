from __future__ import annotations

from ai_risk_manager.profiles.base import ProfileId
from ai_risk_manager.profiles.business_invariant import BusinessInvariantProfile
from ai_risk_manager.profiles.code_risk import CodeRiskProfile
from ai_risk_manager.profiles.ui_flow import UiFlowProfile

_CODE_RISK_PROFILE = CodeRiskProfile()
_UI_FLOW_PROFILE = UiFlowProfile()
_BUSINESS_INVARIANT_PROFILE = BusinessInvariantProfile()
Profile = CodeRiskProfile | UiFlowProfile | BusinessInvariantProfile
_PROFILES: dict[ProfileId, Profile] = {
    "code_risk": _CODE_RISK_PROFILE,
    "ui_flow_risk": _UI_FLOW_PROFILE,
    "business_invariant_risk": _BUSINESS_INVARIANT_PROFILE,
}


def get_profile(profile_id: ProfileId) -> Profile | None:
    profile = _PROFILES.get(profile_id)
    if profile is None:
        return None
    return profile


def list_profile_ids() -> tuple[ProfileId, ...]:
    return tuple(_PROFILES.keys())


__all__ = ["get_profile", "list_profile_ids"]
