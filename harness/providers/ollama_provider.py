"""Ollama backend — local models via Ollama's OpenAI-compatible endpoint.

Ollama (https://ollama.com) serves an OpenAI-compatible Chat Completions API at
`/v1`, so this backend is a thin `OpenAIProvider` pointed at the local Ollama
host. It reuses the `openai` SDK (`pip install openai`); no Ollama-specific
package is needed. No API key is required, but the SDK insists on a non-empty
one, so a placeholder is sent.

Endpoint resolution (first match wins):
  - the `base_url` option, or
  - OLLAMA_BASE_URL / OLLAMA_HOST, or
  - http://localhost:11434/v1

A host given without a scheme or without the `/v1` suffix is normalized, so
`localhost:11434`, `http://localhost:11434` and `.../v1` all work.
"""

from __future__ import annotations

import os
from typing import Any

from harness.providers.openai_provider import OpenAIProvider

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"


def _normalize_base_url(raw: str) -> str:
    """Turn a user-supplied host into a full OpenAI-compatible `/v1` URL."""
    url = raw.strip().rstrip("/")
    if not url:
        return DEFAULT_OLLAMA_BASE_URL
    if "://" not in url:
        url = f"http://{url}"
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class OllamaProvider(OpenAIProvider):
    name = "ollama"

    # Ollama's OpenAI-compatible endpoint maps the classic `max_tokens` to
    # `num_predict`; it does not understand `max_completion_tokens`.
    token_param = "max_tokens"

    def _client_kwargs(self) -> dict[str, Any]:
        base_url = (
            self.options.get("base_url")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_HOST")
            or DEFAULT_OLLAMA_BASE_URL
        )
        api_key = self.options.get("api_key") or os.getenv("OLLAMA_API_KEY") or "ollama"
        return {"base_url": _normalize_base_url(base_url), "api_key": api_key}
