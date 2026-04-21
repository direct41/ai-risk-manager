from __future__ import annotations

import json
import os
import re
import shlex
import subprocess  # nosec B404
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


class LLMRuntimeError(RuntimeError):
    pass


def call_llm_json(
    provider: str,
    prompt: str,
    *,
    max_retries: int = 2,
    timeout_seconds: float | None = None,
) -> dict:
    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            raw = _invoke_provider(provider, prompt, timeout_seconds=timeout_seconds)
            payload = _extract_json(raw)
            if not isinstance(payload, dict):
                raise ValueError("LLM response root must be a JSON object")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    raise LLMRuntimeError(f"LLM call failed after retries: {last_error}")


def _invoke_provider(provider: str, prompt: str, *, timeout_seconds: float | None = None) -> str:
    if provider == "api":
        return _invoke_api(prompt, timeout_seconds=timeout_seconds)
    if provider == "cli":
        return _invoke_cli(prompt, timeout_seconds=timeout_seconds)
    raise LLMRuntimeError(f"Unsupported provider: {provider}")


def _invoke_api(prompt: str, *, timeout_seconds: float | None = None) -> str:
    api_key = os.getenv("AIRISK_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("LITELLM_API_KEY")
    if not api_key:
        raise LLMRuntimeError("API key is missing for API provider")

    base = _http_api_base(os.getenv("AIRISK_API_BASE", "https://api.openai.com/v1"))
    model = os.getenv("AIRISK_API_MODEL", "gpt-4o-mini")
    timeout = timeout_seconds if timeout_seconds is not None else float(os.getenv("AIRISK_API_TIMEOUT", "60"))

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }

    req = urllib_request.Request(
        url=f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        # URL scheme and host are validated by _http_api_base before Request construction.
        with urllib_request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            data = json.loads(resp.read().decode("utf-8"))
    except urllib_error.URLError as exc:
        raise LLMRuntimeError(f"API request failed: {exc}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LLMRuntimeError("API response has no choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "\n".join(text_parts)
    if not isinstance(content, str) or not content.strip():
        raise LLMRuntimeError("API response has empty content")
    return content


def _http_api_base(raw_base: str) -> str:
    base = raw_base.rstrip("/")
    parsed = urllib_parse.urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LLMRuntimeError("AIRISK_API_BASE must be an http(s) URL")
    return base


def _invoke_cli(prompt: str, *, timeout_seconds: float | None = None) -> str:
    configured = os.getenv("AIRISK_CLI_COMMAND")
    if configured:
        cmd = shlex.split(configured)
    elif shutil_which("codex"):
        # Use non-interactive mode to avoid TTY prompts in CI/automation.
        cmd = ["codex", "exec", "--skip-git-repo-check", "--color", "never"]
    elif shutil_which("claude"):
        cmd = ["claude", "-p"]
    else:
        raise LLMRuntimeError("No supported AI CLI found for CLI provider")

    cmd = cmd + [prompt]
    timeout = timeout_seconds if timeout_seconds is not None else float(os.getenv("AIRISK_CLI_TIMEOUT", "120"))
    try:
        # CLI provider is explicit operator opt-in and shell is never used.
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # nosec B603
    except subprocess.TimeoutExpired as exc:
        raise LLMRuntimeError(f"CLI command timed out after {timeout:.1f}s") from exc
    output = (proc.stdout or "").strip()
    if proc.returncode != 0:
        raise LLMRuntimeError(f"CLI command failed ({proc.returncode}): {(proc.stderr or '').strip()}")
    if not output:
        raise LLMRuntimeError("CLI command returned empty output")
    return output


def _extract_json(raw: str) -> dict | list:
    text = raw.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\}|\[[\s\S]*?\])\s*```", text)
    if fenced:
        return json.loads(fenced.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise LLMRuntimeError("Could not extract JSON from LLM output")


def shutil_which(name: str) -> str | None:
    from shutil import which

    return which(name)
