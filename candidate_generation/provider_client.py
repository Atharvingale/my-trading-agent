"""Swappable LLM provider client for candidate generation (Module 15).

Why stdlib urllib instead of an SDK: swapping providers must be a config
change (environment variables), not a code change. Plain JSON POST works
identically against any endpoint that accepts a prompt and returns JSON, so
tests can point at two local mock servers without touching this file. No URL,
key, or model name is hardcoded here; callers pass them in or use env.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


ENV_URL = "CANDIDATE_PROVIDER_URL"
ENV_API_KEY = "CANDIDATE_PROVIDER_API_KEY"
ENV_MODEL = "CANDIDATE_PROVIDER_MODEL"


def load_config_from_env() -> dict[str, str]:
    """Read provider config from the environment (never hardcoded)."""
    url = str(os.environ.get(ENV_URL, "")).strip()
    if not url:
        raise ValueError("missing %s: set the provider endpoint URL" % ENV_URL)
    model = str(os.environ.get(ENV_MODEL, "")).strip()
    if not model:
        raise ValueError("missing %s: set the provider model name" % ENV_MODEL)
    key = str(os.environ.get(ENV_API_KEY, "") or "")
    return {"api_url": url, "api_key": key, "model_name": model}


def propose_hypothesis(
    prompt: str,
    api_url: str,
    api_key: str,
    model_name: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """POST one prompt to any provider endpoint and return its JSON object.

    The same code works for Anthropic, OpenAI, a local model server, or a test
    mock — only api_url/api_key/model_name change. Non-JSON or non-object
    responses raise so the generator logs them as rejected, never coerced.
    """
    text = str(prompt)
    if not text.strip():
        raise ValueError("prompt must be non-empty")
    url = str(api_url).strip()
    if not url:
        raise ValueError("api_url must be non-empty (set via %s)" % ENV_URL)
    model = str(model_name).strip()
    if not model:
        raise ValueError("model_name must be non-empty (set via %s)" % ENV_MODEL)
    key = str(api_key or "")
    body = {"model": model, "prompt": text}
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    if key.strip():
        request.add_header("Authorization", "Bearer " + key.strip())
    timeout = int(timeout_seconds)
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("provider returned non-JSON output") from exc
    if not isinstance(parsed, dict):
        raise ValueError("provider returned a non-object payload")
    return parsed


def propose_from_env(prompt: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Convenience wrapper: config comes entirely from the environment."""
    config = load_config_from_env()
    return propose_hypothesis(
        prompt,
        config["api_url"],
        config["api_key"],
        config["model_name"],
        timeout_seconds=timeout_seconds,
    )
