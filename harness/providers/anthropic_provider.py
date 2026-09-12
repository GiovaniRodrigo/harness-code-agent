"""Anthropic backend (Messages API + tool use).

Keeps the native `content` blocks in history, which preserves thinking blocks
across turns (required when adaptive thinking is combined with tool use on the
same model).
"""

from __future__ import annotations

from typing import Any

from harness.providers.base import (
    LLMResponse,
    Provider,
    ToolCall,
    ToolOutput,
    ToolSpec,
)


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(
        self,
        model: str,
        system: str,
        tools: list[ToolSpec],
        max_tokens: int = 16000,
        effort: str = "high",
        **options: Any,
    ) -> None:
        super().__init__(model, system, tools, max_tokens, **options)
        import anthropic  # lazy: only needed when this provider is selected

        self.client = anthropic.Anthropic()
        self.effort = effort
        # System prompt as a cacheable block (stable across the session).
        self._system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        self._tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
        self._messages: list[dict[str, Any]] = []

    def _generate(self) -> LLMResponse:
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=self._system,
                messages=self._messages,
                tools=self._tools,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
            )
            # Preserve the whole assistant turn (thinking + text + tool_use).
            self._messages.append({"role": "assistant", "content": response.content})

            # A server-side tool paused mid-turn; resend to continue.
            if response.stop_reason == "pause_turn":
                continue

            text = "\n".join(b.text for b in response.content if b.type == "text")
            tool_calls = [
                ToolCall(id=b.id, name=b.name, input=dict(b.input))
                for b in response.content
                if b.type == "tool_use"
            ]
            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                done=response.stop_reason == "end_turn",
            )

    def send_user(self, text: str) -> LLMResponse:
        self._messages.append({"role": "user", "content": text})
        return self._generate()

    def send_tool_results(self, results: list[ToolOutput]) -> LLMResponse:
        content = [
            {
                "type": "tool_result",
                "tool_use_id": r.tool_call_id,
                "content": r.content,
                "is_error": r.is_error,
            }
            for r in results
        ]
        self._messages.append({"role": "user", "content": content})
        return self._generate()
