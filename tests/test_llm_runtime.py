from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, _invoke_api, _invoke_cli, call_llm_json


def test_call_llm_json_retries_and_succeeds() -> None:
    with patch(
        "ai_risk_manager.agents.llm_runtime._invoke_provider",
        side_effect=[RuntimeError("x"), RuntimeError("y"), "{\"ok\": true}"],
    ) as mock_invoke:
        payload = call_llm_json("api", "prompt", max_retries=2)

    assert payload == {"ok": True}
    assert mock_invoke.call_count == 3


def test_call_llm_json_raises_after_retries_exhausted() -> None:
    with patch("ai_risk_manager.agents.llm_runtime._invoke_provider", side_effect=RuntimeError("x")):
        with pytest.raises(LLMRuntimeError):
            call_llm_json("api", "prompt", max_retries=2)


def test_call_llm_json_passes_timeout_to_provider() -> None:
    with patch("ai_risk_manager.agents.llm_runtime._invoke_provider", return_value="{\"ok\": true}") as mock_invoke:
        payload = call_llm_json("cli", "prompt", max_retries=0, timeout_seconds=7.5)

    assert payload == {"ok": True}
    assert mock_invoke.call_args.kwargs["timeout_seconds"] == 7.5


def test_invoke_api_rejects_non_http_base(monkeypatch) -> None:
    monkeypatch.setenv("AIRISK_API_KEY", "secret")
    monkeypatch.setenv("AIRISK_API_BASE", "file:///tmp/socket")

    with pytest.raises(LLMRuntimeError, match="http"):
        _invoke_api("prompt")


def test_invoke_cli_uses_codex_prompt_as_positional_argument() -> None:
    with (
        patch("ai_risk_manager.agents.llm_runtime.shutil_which", side_effect=lambda name: "/usr/bin/codex" if name == "codex" else None),
        patch(
            "ai_risk_manager.agents.llm_runtime.subprocess.run",
            return_value=type(
                "_Proc",
                (),
                {
                    "returncode": 0,
                    "stdout": "{\"ok\": true}",
                    "stderr": "",
                },
            )(),
        ) as mock_run,
    ):
        output = _invoke_cli("hello")

    assert output == "{\"ok\": true}"
    assert mock_run.call_args.args[0] == ["codex", "exec", "--skip-git-repo-check", "--color", "never", "hello"]


def test_invoke_cli_raises_runtime_error_on_timeout() -> None:
    with (
        patch("ai_risk_manager.agents.llm_runtime.shutil_which", side_effect=lambda name: "/usr/bin/codex" if name == "codex" else None),
        patch(
            "ai_risk_manager.agents.llm_runtime.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["codex"], timeout=1),
        ),
    ):
        with pytest.raises(LLMRuntimeError, match="timed out"):
            _invoke_cli("hello", timeout_seconds=1.0)
