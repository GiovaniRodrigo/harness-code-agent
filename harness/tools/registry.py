"""Registry: o modelo só enxerga as ferramentas registradas aqui."""

from __future__ import annotations

from typing import Any

from harness.sandbox import Sandbox
from harness.tools.base import Tool, ToolResult
from harness.tools.filesystem import ListDir, ReadFile, WriteFile
from harness.tools.shell import RunCommand


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """Definições no formato do parâmetro `tools` da Messages API.

        Ordem determinística — importante para o cache de prompt não invalidar.
        """
        return [self._tools[name].to_schema() for name in sorted(self._tools)]

    def execute(self, name: str, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(f"Ferramenta desconhecida: {name}", is_error=True)
        return tool.run(args, sandbox)


def default_registry() -> ToolRegistry:
    """Conjunto padrão de ferramentas de um coding agent."""
    return ToolRegistry([ReadFile(), WriteFile(), ListDir(), RunCommand()])
