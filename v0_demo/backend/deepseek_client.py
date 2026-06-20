from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT_SEC = int(os.getenv("DEEPSEEK_TIMEOUT_SEC", "90"))
AVAILABILITY_DEEPSEEK_MODEL = os.getenv("AVAILABILITY_DEEPSEEK_MODEL", "deepseek-chat")


def deepseek_model_ready() -> tuple[bool, str]:
    """Check DeepSeek API availability by listing models."""
    if not DEEPSEEK_API_KEY:
        return False, "DEEPSEEK_API_KEY not configured"
    req = Request(
        f"{DEEPSEEK_API_URL}/models",
        method="GET",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        return False, f"cannot connect to DeepSeek API: {exc}"
    except Exception as exc:
        return False, f"DeepSeek API check failed: {exc}"
    models = data.get("data", [])
    if not models:
        return False, "no models returned from DeepSeek API"
    return True, "ready"


def deepseek_chat(payload: dict[str, Any]) -> dict[str, Any]:
    """Call DeepSeek chat completion API (OpenAI-compatible).

    Expects 'model', 'messages', and optional 'stream'/'format' in payload.
    Returns the full response JSON from DeepSeek API.
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not configured")

    body_payload: dict[str, Any] = {
        "model": payload["model"],
        "messages": payload["messages"],
        "stream": False,
    }

    # DeepSeek supports 'response_format' (OpenAI-compatible) for JSON mode
    if payload.get("format") == "json":
        body_payload["response_format"] = {"type": "json_object"}

    # Map Ollama options to OpenAI params
    options = payload.get("options", {})
    if "temperature" in options:
        body_payload["temperature"] = options["temperature"]
    if "top_p" in options:
        body_payload["top_p"] = options["top_p"]
    if "max_tokens" in options:
        body_payload["max_tokens"] = options["max_tokens"]

    body = json.dumps(body_payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"{DEEPSEEK_API_URL}/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=DEEPSEEK_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(
            f"DeepSeek API HTTP error {exc.code}: {error_body}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"DeepSeek API request timed out after {DEEPSEEK_TIMEOUT_SEC}s"
        ) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise RuntimeError(
                f"DeepSeek API request timed out after {DEEPSEEK_TIMEOUT_SEC}s"
            ) from exc
        raise RuntimeError(f"DeepSeek API unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("DeepSeek API returned non-JSON response") from exc


def extract_deepseek_content(response: dict[str, Any]) -> str:
    """Extract the content string from a DeepSeek/OpenAI chat completion response."""
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected DeepSeek API response structure: {exc}") from exc
