from __future__ import annotations

from unittest.mock import patch

import pytest

from ai_risk_manager.agents.llm_runtime import LLMRuntimeError, call_llm_json


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
