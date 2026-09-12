"""Context manager: builds the system prompt and truncates tool output.

A good harness controls what enters the context on each iteration. The
essentials here: a stable system prompt (good for caching) and truncation of
large tool outputs so we don't blow the token budget.
"""

from __future__ import annotations

from harness.config import Config

SYSTEM_TEMPLATE = """\
You are an autonomous coding agent running inside a harness.

Environment:
- You work confined to a workspace. All paths are relative to it.
- You act ONLY through the available tools (read_file, write_file, list_dir,
  run_command). There is no other way to touch the system.
- Shell commands run in the workspace, with a timeout, and pass through safety
  policies that may block dangerous actions.

How to work:
- Explore before editing: list directories and read the relevant files.
- Make small, verifiable changes.
- When there is a way to verify (tests, execution), verify it yourself with run_command.
- When the task is done, stop calling tools and write a short summary of what
  you did and how you verified it.

Be direct and efficient with your tool calls.
"""


def system_prompt(config: Config) -> str:
    """The system prompt as plain text.

    Vendor-neutral: each provider applies its own formatting (e.g. the Anthropic
    provider wraps it in a cacheable block).
    """
    return SYSTEM_TEMPLATE


def truncate_output(text: str, max_bytes: int) -> str:
    """Truncate in the middle, keeping the head and tail (more useful than the middle)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    head = encoded[: max_bytes // 2].decode("utf-8", errors="ignore")
    tail = encoded[-max_bytes // 2 :].decode("utf-8", errors="ignore")
    omitted = len(encoded) - max_bytes
    return f"{head}\n\n... [{omitted} bytes omitted by the harness] ...\n\n{tail}"
