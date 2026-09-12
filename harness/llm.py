"""Thin wrapper over the Anthropic SDK.

Isolates the Messages API call from the rest of the harness: model, adaptive
thinking, effort, and the tool set. The agent loop (loop.py) knows nothing
about SDK details — it just calls `generate`.
"""

from __future__ import annotations

from typing import Any

import anthropic

from harness.config import Config


class LLM:
    def __init__(self, config: Config) -> None:
        self.config = config
        # Resolve credentials from the environment (ANTHROPIC_API_KEY or an
        # `ant auth login` profile).
        self.client = anthropic.Anthropic()

    def generate(
        self,
        system: list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> anthropic.types.Message:
        """One reasoning iteration of the agent.

        Returns the whole Message object; the loop inspects stop_reason and the
        content blocks (thinking / text / tool_use).
        """
        return self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": self.config.effort},
        )
