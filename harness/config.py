"""Harness configuration, read from the environment with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from harness.providers.factory import default_model_for


def load_env(path: str | None = None) -> bool:
    """Load a .env file into the environment if python-dotenv is available.

    Returns True if a file was loaded. Missing lib or missing file is a no-op,
    so the harness works with or without python-dotenv installed. Existing
    environment variables are not overridden.
    """
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        return False
    return load_dotenv(dotenv_path=path)


# Auto-load .env on import, before any Config() reads os.getenv.
load_env()


@dataclass
class Config:
    # LLM backend: anthropic | openai | google | ollama.
    provider: str = field(default_factory=lambda: os.getenv("HARNESS_PROVIDER", "anthropic").lower())

    # Model id. Empty => a per-provider default is filled in __post_init__.
    model: str = field(default_factory=lambda: os.getenv("HARNESS_MODEL", ""))

    # Reasoning effort (Anthropic only): low | medium | high | xhigh | max.
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

    # Orchestration budgets: max subtasks executed and max planner re-plans/repairs.
    max_subtasks: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_SUBTASKS", "8")))
    max_replans: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_REPLANS", "3")))

    # Timeout (seconds) for shell commands in the sandbox.
    command_timeout: int = field(default_factory=lambda: int(os.getenv("HARNESS_CMD_TIMEOUT", "120")))

    # Max size (bytes) of tool output returned to the model, so we don't blow the context.
    max_tool_output: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_TOOL_OUTPUT", "16000")))

    # Event log path (JSONL). Enables auditing and replay.
    event_log: Path = field(
        default_factory=lambda: Path(os.getenv("HARNESS_EVENT_LOG", "./harness_events.jsonl"))
    )

    def __post_init__(self) -> None:
        self.provider = self.provider.lower()
        # Pick a per-provider default model when HARNESS_MODEL is unset
        # (honors a HARNESS_MODEL_<PROVIDER> override before the shipped default).
        if not self.model:
            self.model = default_model_for(self.provider)

    def ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
