"""Wrapper fino sobre o SDK da Anthropic.

Isola a chamada da Messages API do resto do harness: modelo, thinking
adaptativo, esforço e o conjunto de ferramentas. O loop do agente (loop.py)
não conhece detalhes do SDK — só chama `generate`.
"""

from __future__ import annotations

from typing import Any

import anthropic

from harness.config import Config


class LLM:
    def __init__(self, config: Config) -> None:
        self.config = config
        # Resolve credenciais do ambiente (ANTHROPIC_API_KEY ou perfil `ant auth login`).
        self.client = anthropic.Anthropic()

    def generate(
        self,
        system: list[dict],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> anthropic.types.Message:
        """Uma iteração de raciocínio do agente.

        Devolve o objeto Message inteiro; o loop inspeciona stop_reason e os
        blocos de conteúdo (thinking / text / tool_use).
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
