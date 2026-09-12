"""Base interface for a tool.

Each tool declares its schema (what the model sees) and implements `run`.
The model NEVER touches the system directly — only through a registered Tool.
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
    #: Name exposed to the model (must match tool_use.name).
    name: str = ""
    #: Description that helps the model decide when to use the tool.
    description: str = ""
    #: JSON Schema of the arguments.
    input_schema: dict[str, Any] = {}

    def to_schema(self) -> dict[str, Any]:
        """Format accepted by the Messages API `tools` parameter."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, args: dict[str, Any], sandbox: Sandbox) -> ToolResult:  # pragma: no cover
        raise NotImplementedError
