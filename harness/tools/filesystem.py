"""Filesystem tools, all confined to the sandbox."""

from __future__ import annotations

from typing import Any

from harness.sandbox import Sandbox, SandboxError
from harness.tools.base import Tool, ToolResult


class ReadFile(Tool):
    name = "read_file"
    description = "Read the contents of a text file inside the workspace."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace."},
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
            return ToolResult(f"File not found: {args['path']}", is_error=True)
        try:
            return ToolResult(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            return ToolResult(f"'{args['path']}' is not UTF-8 text.", is_error=True)


class WriteFile(Tool):
    name = "write_file"
    description = (
        "Create or overwrite a text file inside the workspace. "
        "Creates intermediate directories if needed."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to the workspace."},
            "content": {"type": "string", "description": "Full file contents."},
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
        return ToolResult(f"Wrote {len(args['content'])} bytes to {args['path']}")


class ListDir(Tool):
    name = "list_dir"
    description = "List files and subdirectories of a path inside the workspace."
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path relative to the workspace. Use '.' for the root.",
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
            return ToolResult(f"Directory not found: {args['path']}", is_error=True)
        entries = []
        for child in sorted(path.iterdir()):
            marker = "/" if child.is_dir() else ""
            entries.append(f"{child.name}{marker}")
        return ToolResult("\n".join(entries) if entries else "(empty)")
