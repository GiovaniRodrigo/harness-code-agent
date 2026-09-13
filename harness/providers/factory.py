"""Provider factory: pick a backend by name and construct it.

Concrete providers are imported lazily so their SDKs (anthropic / openai /
google-genai) are only required when actually selected.
"""

from __future__ import annotations

import os
from typing import Any

from harness.providers.base import Provider, ToolSpec

# Sensible default model per provider when no model is specified.
# Adjust to whatever you have access to.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "ollama": "llama3.1",
}


def default_model_for(provider: str) -> str:
    """The default model for ``provider`` when a request gives none.

    A `HARNESS_MODEL_<PROVIDER>` env var (e.g. ``HARNESS_MODEL_OLLAMA``) lets you
    override the shipped `DEFAULT_MODELS` entry *per provider* without editing
    code — handy when the built-in default (``llama3.1``) isn't what you have
    pulled locally, but you don't want to change it for everyone. Returns an
    empty string for an unknown provider.
    """
    provider = provider.lower()
    override = os.getenv(f"HARNESS_MODEL_{provider.upper()}")
    if override:
        return override
    return DEFAULT_MODELS.get(provider, "")


def build_provider(
    name: str,
    model: str,
    system: str,
    tools: list[ToolSpec],
    max_tokens: int = 16000,
    **options: Any,
) -> Provider:
    name = name.lower()
    if name == "anthropic":
        from harness.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model, system, tools, max_tokens, **options)
    if name == "openai":
        from harness.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(model, system, tools, max_tokens, **options)
    if name == "google":
        from harness.providers.google_provider import GoogleProvider

        return GoogleProvider(model, system, tools, max_tokens, **options)
    if name == "ollama":
        from harness.providers.ollama_provider import OllamaProvider

        return OllamaProvider(model, system, tools, max_tokens, **options)
    raise ValueError(
        f"Unknown provider '{name}'. Use one of: anthropic, openai, google, ollama."
    )
