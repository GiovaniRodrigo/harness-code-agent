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

On construction the provider runs a cheap preflight against the native
`/api/tags` endpoint: if the requested model isn't pulled it raises
`ModelNotAvailableError` with the installed models and the `ollama pull`
command, instead of failing later with a raw `404 model not found`. If the
host is unreachable the preflight is skipped so the real request surfaces the
connection error.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from harness.providers.base import ToolSpec
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


def _api_root(base_url_v1: str) -> str:
    """Native Ollama root (drops the `/v1`) for the `/api/*` endpoints."""
    return base_url_v1[: -len("/v1")] if base_url_v1.endswith("/v1") else base_url_v1


def _installed_models(api_root: str, timeout: float = 3.0) -> list[str] | None:
    """Model tags the daemon reports via `/api/tags`.

    Returns ``None`` when the server can't be reached or gives a bad response —
    the signal to *skip* the preflight and let the real request surface the
    underlying connection error, rather than inventing a new failure mode.
    """
    try:
        with urllib.request.urlopen(f"{api_root}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return [m["name"] for m in data.get("models", []) if m.get("name")]


def _model_present(model: str, installed: list[str]) -> bool:
    """Is ``model`` among the installed tags?

    Ollama stores an untagged pull (``llama3.1``) as ``llama3.1:latest``, so a
    request without an explicit tag matches the ``:latest`` variant too.
    """
    if model in installed:
        return True
    if ":" not in model and f"{model}:latest" in installed:
        return True
    return False


class ModelNotAvailableError(RuntimeError):
    """Raised when the requested model isn't installed on the Ollama host."""


class OllamaProvider(OpenAIProvider):
    name = "ollama"

    # Ollama's OpenAI-compatible endpoint maps the classic `max_tokens` to
    # `num_predict`; it does not understand `max_completion_tokens`.
    token_param = "max_tokens"

    def __init__(
        self,
        model: str,
        system: str,
        tools: list[ToolSpec],
        max_tokens: int = 16000,
        **options: Any,
    ) -> None:
        super().__init__(model, system, tools, max_tokens, **options)
        # Fail fast with an actionable message if the model isn't pulled, rather
        # than letting the first turn blow up with a raw `404 model not found`.
        self._preflight_model()

    def _preflight_model(self) -> None:
        """Verify the model exists on the host; skip quietly if the host is down."""
        api_root = _api_root(self._client_kwargs()["base_url"])
        installed = _installed_models(api_root)
        if installed is None:
            return  # host unreachable — let the real request report that
        if _model_present(self.model, installed):
            return
        listed = ", ".join(installed) if installed else None
        if listed:
            available = f"Installed: {listed}."
        else:
            available = "Installed: (none)."
        raise ModelNotAvailableError(
            f"Model {self.model!r} not found on Ollama at {api_root}. "
            f"{available} Pull it with:  ollama pull {self.model}"
        )

    def _client_kwargs(self) -> dict[str, Any]:
        base_url = (
            self.options.get("base_url")
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_HOST")
            or DEFAULT_OLLAMA_BASE_URL
        )
        api_key = self.options.get("api_key") or os.getenv("OLLAMA_API_KEY") or "ollama"
        return {"base_url": _normalize_base_url(base_url), "api_key": api_key}
