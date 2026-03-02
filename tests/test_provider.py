from __future__ import annotations

from ai_risk_manager.agents.provider import resolve_provider


def test_resolve_provider_api_accepts_airisk_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("AIRISK_API_KEY", "x")

    resolution = resolve_provider("api", no_llm=False, ci=False)
    assert resolution.provider == "api"
    assert resolution.generated_without_llm is False


def test_resolve_provider_api_rejects_anthropic_only_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("AIRISK_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    resolution = resolve_provider("api", no_llm=False, ci=False)
    assert resolution.provider == "none"
    assert resolution.generated_without_llm is True
