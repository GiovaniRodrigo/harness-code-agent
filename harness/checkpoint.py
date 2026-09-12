"""Checkpointing for the orchestrator's shared workspace.

The orchestrator runs subtasks against one shared workspace and records a
checkpoint after each, so later subtasks build on earlier work and a failed
subtask can be rolled back. The interface is small and swappable, so
orchestration logic can be tested without a real git binary.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class CheckpointError(Exception):
    """A checkpoint operation failed (e.g. a git command errored)."""


class Checkpointer(ABC):
    @abstractmethod
    def init(self) -> None:
        """Prepare the workspace for checkpointing."""

    @abstractmethod
    def commit(self, label: str) -> str:
        """Record the current workspace state; return a checkpoint handle."""

    @abstractmethod
    def rollback(self, checkpoint: str) -> None:
        """Restore the workspace to a previous checkpoint handle."""


class GitCheckpointer(Checkpointer):
    """Checkpoints as git commits in the workspace.

    Uses a per-commit identity so it doesn't depend on the machine's global git
    config, and `--allow-empty` so a subtask that changed nothing still yields a
    checkpoint (keeping the audit trail one-per-subtask).
    """

    def __init__(self, workspace: Path, command_timeout: int = 120) -> None:
        self.workspace = Path(workspace)
        self.command_timeout = command_timeout

    def _git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.workspace), *args],
            capture_output=True,
            text=True,
            timeout=self.command_timeout,
        )
        if proc.returncode != 0:
            raise CheckpointError(
                f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc.stdout.strip()

    def init(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not (self.workspace / ".git").exists():
            self._git("init")

    def commit(self, label: str) -> str:
        self._git("add", "-A")
        self._git(
            "-c",
            "user.name=harness",
            "-c",
            "user.email=harness@local",
            "commit",
            "--allow-empty",
            "-m",
            label,
        )
        return self._git("rev-parse", "HEAD")

    def rollback(self, checkpoint: str) -> None:
        self._git("reset", "--hard", checkpoint)
        self._git("clean", "-fd")
