"""OpenAI backend (Chat Completions + function calling).

Note: written against the `openai` Python SDK's Chat Completions API. The SDK
is not installed in this repo by default (`pip install openai`), so this
provider is not exercised by the smoke tests; verify against your installed
SDK version before relying on it.
"""

from __future__ import annotations

import json
from typing import Any

from harness.providers.base import (
    LLMResponse,
    Provider,
    ToolCall,
    ToolOutput,
    ToolSpec,
)


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(
        self,
        model: str,
        system: str,
        tools: list[ToolSpec],
        max_tokens: int = 16000,
        **options: Any,
    ) -> None:
        super().__init__(model, system, tools, max_tokens, **options)
        from openai import OpenAI  # lazy: only needed when this provider is selected

        self.client = OpenAI()
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]
        self._messages: list[dict[str, Any]] = []
        if system:
            self._messages.append({"role": "system", "content": system})

    def _generate(self) -> LLMResponse:
        completion = self.client.chat.completions.create(
            model=self.model,
            # Newer models (o-series, gpt-5) reject the legacy `max_tokens` and
            # require `max_completion_tokens`, which current chat models accept.
            max_completion_tokens=self.max_tokens,
            messages=self._messages,
            tools=self._tools or None,
        )
        message = completion.choices[0].message
        raw_calls = message.tool_calls or []

        # Rebuild the assistant turn as a plain dict for the history.
        assistant: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
        if raw_calls:
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in raw_calls
            ]
        self._messages.append(assistant)

        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, input=_parse_args(tc.function.arguments))
            for tc in raw_calls
        ]
        return LLMResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            done=not raw_calls,
        )

    def send_user(self, text: str) -> LLMResponse:
        self._messages.append({"role": "user", "content": text})
        return self._generate()

    def send_tool_results(self, results: list[ToolOutput]) -> LLMResponse:
        for r in results:
            self._messages.append(
                {"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content}
            )
        return self._generate()


def _parse_args(arguments: str) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string; never string-match them."""
    try:
        return json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        return {}
