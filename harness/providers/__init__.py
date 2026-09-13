"""Vendor-neutral provider layer.

The agent loop talks to any LLM backend through `Provider`. Concrete backends
(Anthropic / OpenAI / Google) are constructed via `build_provider` and imported
lazily, so only the SDK you actually use needs to be installed.
"""

from harness.providers.base import (
    LLMResponse,
    Provider,
    ToolCall,
    ToolOutput,
    ToolSpec,
)
from harness.providers.factory import DEFAULT_MODELS, build_provider, default_model_for

__all__ = [
    "LLMResponse",
    "Provider",
    "ToolCall",
    "ToolOutput",
    "ToolSpec",
    "DEFAULT_MODELS",
    "build_provider",
    "default_model_for",
]
