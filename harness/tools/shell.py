"""Shell tool, executed in the sandbox and subject to the policies."""

from __future__ import annotations

from typing import Any

from harness.sandbox import Sandbox
from harness.tools.base import Tool, ToolResult


class RunCommand(Tool):
    name = "run_command"
    description = (
        "Run a shell command in the workspace directory (e.g. run tests, list "
        "dependencies, execute a script). Returns exit_code, stdout and stderr."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to run."},
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
        # A failing command is not a tool error: the model needs to see the
        # exit_code to decide the next step. is_error is reserved for harness failures.
        return ToolResult(text)
