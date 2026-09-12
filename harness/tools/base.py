"""Interface base de uma ferramenta.

Cada ferramenta declara seu schema (o que o modelo vê) e implementa `run`.
O modelo NUNCA toca o sistema diretamente — só através de uma Tool registrada.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harness.sandbox import Sandbox


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


class Tool:
    #: Nome exposto ao modelo (deve casar com o tool_use.name).
    name: str = ""
    #: Descrição que ajuda o modelo a decidir quando usar a ferramenta.
    description: str = ""
    #: JSON Schema dos argumentos.
    input_schema: dict[str, Any] = {}

    def to_schema(self) -> dict[str, Any]:
        """Formato aceito pelo parâmetro `tools` da Messages API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:  # pragma: no cover
        raise NotImplementedError
