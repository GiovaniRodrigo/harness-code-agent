"""Ferramenta de shell, executada no sandbox e sujeita às policies."""

from __future__ import annotations

from typing import Any

from harness.sandbox import Sandbox
from harness.tools.base import Tool, ToolResult


class RunCommand(Tool):
    name = "run_command"
    description = (
        "Executa um comando de shell no diretório do workspace (ex.: rodar testes, "
        "listar dependências, executar um script). Retorna exit_code, stdout e stderr."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Comando de shell a executar."},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:
        result = sandbox.run(args["command"])
        parts = [f"exit_code: {result['exit_code']}"]
        if result["stdout"]:
            parts.append(f"--- stdout ---\n{result['stdout']}")
        if result["stderr"]:
            parts.append(f"--- stderr ---\n{result['stderr']}")
        text = "\n".join(parts)
        # Falha de comando não é erro de ferramenta: o modelo precisa ver o exit_code
        # para decidir o próximo passo. is_error fica reservado a falhas do harness.
        return ToolResult(text)
