"""Policies / guardrails.

Before executing any tool_use, the harness consults the policy. Here we
implement a simple denylist for shell commands that are clearly destructive or
that escape the sandbox. In production, evolve this into human-in-the-loop
confirmation for irreversible actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Patterns blocked in run_command. This is not a full security sandbox —
# it is a safety net against obvious accidents.
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",   # rm -rf / (root)
    r"\brm\s+-rf\s+~",           # rm -rf on home
    r":\(\)\s*\{.*\};:",         # fork bomb
    r"\bsudo\b",                  # privilege escalation
    r"\bshutdown\b|\breboot\b",
    r"\bmkfs\b|\bdd\s+if=",      # format / raw disk write
    r">\s*/dev/sd",               # direct write to a device
    r"\bcurl\b.*\|\s*(sh|bash)",  # piping the network into a shell
    r"\bwget\b.*\|\s*(sh|bash)",
]


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


class PolicyEngine:
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        if tool_name == "run_command":
            command = str(args.get("command", ""))
            for pattern in _BLOCKED_PATTERNS:
                if re.search(pattern, command):
                    return Decision(
                        allowed=False,
                        reason=(
                            f"Command blocked by policy (dangerous pattern: /{pattern}/). "
                            "Adjust your approach without that command."
                        ),
                    )
        return Decision(allowed=True)
