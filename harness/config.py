"""Harness configuration, read from the environment with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Model. Default: the most capable one. Override with HARNESS_MODEL=claude-sonnet-5 etc.
    model: str = field(default_factory=lambda: os.getenv("HARNESS_MODEL", "claude-opus-5"))

    # Reasoning effort: low | medium | high | xhigh | max.
    effort: str = field(default_factory=lambda: os.getenv("HARNESS_EFFORT", "high"))

    # Token ceiling per model response.
    max_tokens: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_TOKENS", "16000")))

    # The agent's working directory. EVERYTHING happens confined here (sandbox).
    workspace: Path = field(
        default_factory=lambda: Path(os.getenv("HARNESS_WORKSPACE", "./workspace")).resolve()
    )

    # Agent loop limits.
    max_steps: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_STEPS", "40")))

    # Command the evaluator runs to verify the work (e.g. "pytest -q").
    # Empty => no automatic verification; the agent finishes on the first end_turn.
    test_command: str = field(default_factory=lambda: os.getenv("HARNESS_TEST_COMMAND", ""))

    # How many times, at most, we hand a test failure back to the agent to fix.
    max_eval_retries: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_EVAL_RETRIES", "3")))

    # Timeout (seconds) for shell commands in the sandbox.
    command_timeout: int = field(default_factory=lambda: int(os.getenv("HARNESS_CMD_TIMEOUT", "120")))

    # Max size (bytes) of tool output returned to the model, so we don't blow the context.
    max_tool_output: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_TOOL_OUTPUT", "16000")))

    # Event log path (JSONL). Enables auditing and replay.
    event_log: Path = field(
        default_factory=lambda: Path(os.getenv("HARNESS_EVENT_LOG", "./harness_events.jsonl"))
    )

    def ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
