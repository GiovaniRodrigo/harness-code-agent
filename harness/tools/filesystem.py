"""Ferramentas de filesystem, todas confinadas ao sandbox."""

from __future__ import annotations

from typing import Any

from harness.sandbox import Sandbox, SandboxError
from harness.tools.base import Tool, ToolResult


class ReadFile(Tool):
    name = "read_file"
    description = "Lê o conteúdo de um arquivo de texto dentro do workspace."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo ao workspace."},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:
        try:
            path = sandbox.resolve(args["path"])
        except SandboxError as e:
            return ToolResult(str(e), is_error=True)
        if not path.is_file():
            return ToolResult(f"Arquivo não encontrado: {args['path']}", is_error=True)
        try:
            return ToolResult(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            return ToolResult(f"'{args['path']}' não é texto UTF-8.", is_error=True)


class WriteFile(Tool):
    name = "write_file"
    description = (
        "Cria ou sobrescreve um arquivo de texto dentro do workspace. "
        "Cria diretórios intermediários se necessário."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Caminho relativo ao workspace."},
            "content": {"type": "string", "description": "Conteúdo completo do arquivo."},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:
        try:
            path = sandbox.resolve(args["path"])
        except SandboxError as e:
            return ToolResult(str(e), is_error=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        return ToolResult(f"Gravado {len(args['content'])} bytes em {args['path']}")


class ListDir(Tool):
    name = "list_dir"
    description = "Lista arquivos e subdiretórios de um caminho dentro do workspace."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Caminho relativo ao workspace. Use '.' para a raiz.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:
        try:
            path = sandbox.resolve(args["path"])
        except SandboxError as e:
            return ToolResult(str(e), is_error=True)
        if not path.is_dir():
            return ToolResult(f"Diretório não encontrado: {args['path']}", is_error=True)
        entries = []
        for child in sorted(path.iterdir()):
            marker = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{marker}")
        return ToolResult("\n".join(entries) if entries else "(vazio)")
