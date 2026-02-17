from __future__ import annotations

from dataclasses import dataclass
import os
import shlex
import shutil
from typing import Literal

ProviderName = Literal["api", "cli", "none"]


@dataclass
class ProviderResolution:
    provider: ProviderName
    generated_without_llm: bool
    notes: list[str]


def _has_api_credentials() -> bool:
    keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "LITELLM_API_KEY",
    ]
    return any(bool(os.getenv(key)) for key in keys)


def _has_cli_backend() -> bool:
    configured = os.getenv("AIRISK_CLI_COMMAND")
    if configured:
        try:
            executable = shlex.split(configured)[0]
        except (ValueError, IndexError):
            return False
        return shutil.which(executable) is not None
    return shutil.which("codex") is not None or shutil.which("claude") is not None


def resolve_provider(selection: Literal["auto", "api", "cli"], *, no_llm: bool, ci: bool) -> ProviderResolution:
    if no_llm:
        return ProviderResolution(provider="none", generated_without_llm=True, notes=["LLM disabled by --no-llm."])

    notes: list[str] = []

    if selection == "api":
        if _has_api_credentials():
            return ProviderResolution(provider="api", generated_without_llm=False, notes=[])
        return ProviderResolution(
            provider="none",
            generated_without_llm=True,
            notes=["API provider selected but API credentials are missing. Use --no-llm or configure API keys."],
        )

    if selection == "cli":
        if _has_cli_backend():
            return ProviderResolution(provider="cli", generated_without_llm=False, notes=[])
        return ProviderResolution(
            provider="none",
            generated_without_llm=True,
            notes=["CLI provider selected but no supported AI CLI was found. Use --provider api or --no-llm."],
        )

    # auto
    if ci:
        if _has_api_credentials():
            notes.append("auto provider in CI: selected api.")
            return ProviderResolution(provider="api", generated_without_llm=False, notes=notes)
        notes.append("auto provider in CI: API unavailable, falling back to no-llm.")
        return ProviderResolution(provider="none", generated_without_llm=True, notes=notes)

    if _has_cli_backend():
        notes.append("auto provider local: selected cli.")
        return ProviderResolution(provider="cli", generated_without_llm=False, notes=notes)

    if _has_api_credentials():
        notes.append("auto provider local: CLI unavailable, selected api.")
        return ProviderResolution(provider="api", generated_without_llm=False, notes=notes)

    notes.append("auto provider local: no provider configured, falling back to no-llm.")
    return ProviderResolution(provider="none", generated_without_llm=True, notes=notes)
