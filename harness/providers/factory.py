"""Provider factory: pick a backend by name and construct it.

Concrete providers are imported lazily so their SDKs (anthropic / openai /
google-genai) are only required when actually selected.
"""

from __future__ import annotations

from typing import Any

from harness.providers.base import Provider, ToolSpec

# Sensible default model per provider when HARNESS_MODEL is unset.
# Adjust to whatever you have access to.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "ollama": "llama3.1",
}


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
