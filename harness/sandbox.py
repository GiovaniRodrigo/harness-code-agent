"""Sandbox: confines all agent activity to the workspace directory.

This is not container-level isolation — it is a first line of in-process
defense. For real, higher-risk use, run the whole harness inside a disposable
container/VM. Here we make sure paths and commands don't accidentally escape
the workspace.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class SandboxError(Exception):
    """Sandbox boundary violation (path traversal, workspace escape, etc.)."""


class Sandbox:
    def __init__(self, workspace: Path, command_timeout: int = 120) -> None:
        self.workspace = workspace.resolve()
        self.command_timeout = command_timeout
        self.workspace.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        """Resolve a path relative to the workspace and reject any escape.

        Blocks path traversal (../), absolute paths, and symlinks that point
        outside the workspace.
        """
        candidate = (self.workspace / relative_path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise SandboxError(
                f"Path '{relative_path}' escapes the workspace {self.workspace}"
            )
        return candidate

    def run(self, command: str) -> dict:
        """Run a shell command with cwd=workspace and a timeout.

        Returns exit_code, stdout, stderr. Does not raise on command failure —
        a non-zero exit_code is useful information for the agent.
        """
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Command exceeded the {self.command_timeout}s timeout and was killed.",
            }
