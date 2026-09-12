"""Provider abstraction: one backend per LLM vendor.

The harness talks to models ONLY through this interface, so the agent loop
stays vendor-neutral. Each provider owns its own native conversation history
and translates the harness's normalized tool specs / tool results to and from
its SDK's wire format.

Normalized types (vendor-neutral):
- ToolSpec   : a tool definition the model may call (name/description/schema).
- ToolCall   : the model asking to call a tool (id + name + parsed input).
- ToolOutput : the result we hand back for a given ToolCall.
- LLMResponse: one turn of the model (assistant text + any tool calls + done).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ToolOutput:
    # Both are carried because vendors match results differently: Anthropic and
    # OpenAI match by call id; Google matches by function name.
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


@dataclass
class LLMResponse:
    #: Assistant text for this turn (empty when the turn is pure tool calls).
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    #: True when the model stopped WITHOUT requesting tools (candidate to finish).
    done: bool = False


class Provider(ABC):
    """Stateful, single-conversation client for one vendor.

    Construction pins the system prompt and tool set for the whole session.
    The loop then alternates `send_user` / `send_tool_results`, and each call
    returns a normalized `LLMResponse`.
    """

    name: str = "provider"

    def __init__(
        self,
        model: str,
        system: str,
        tools: list[ToolSpec],
        max_tokens: int = 16000,
        **options: Any,
    ) -> None:
        self.model = model
        self.system = system
        self.tools = tools
        self.max_tokens = max_tokens
        self.options = options

    @abstractmethod
    def send_user(self, text: str) -> LLMResponse:
        """Append a user message and get the next assistant turn."""

    @abstractmethod
    def send_tool_results(self, results: list[ToolOutput]) -> LLMResponse:
        """Append tool results and get the next assistant turn."""
