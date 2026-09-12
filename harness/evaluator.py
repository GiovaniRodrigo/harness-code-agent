"""Evaluator: closes the loop with verifiable feedback.

The agent saying "I'm done" is not enough — the harness verifies. If a test
command is configured, we run it in the sandbox. Tests pass => success. Tests
fail => we hand the output back to the agent to fix.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.sandbox import Sandbox


@dataclass
class Evaluation:
    success: bool
    feedback: str


class Evaluator:
    def __init__(self, test_command: str) -> None:
        self.test_command = test_command.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.test_command)

    def check(self, sandbox: Sandbox) -> Evaluation:
        """Run the test command. No command configured => approve immediately."""
        if not self.enabled:
            return Evaluation(success=True, feedback="")

        result = sandbox.run(self.test_command)
        if result["exit_code"] == 0:
            return Evaluation(success=True, feedback="")

        feedback = (
            f"The evaluator ran `{self.test_command}` and it failed "
            f"(exit_code={result['exit_code']}). Fix it and do not finish until it passes.\n"
        )
        if result["stdout"]:
            feedback += f"\n--- stdout ---\n{result['stdout']}"
        if result["stderr"]:
            feedback += f"\n--- stderr ---\n{result['stderr']}"
        return Evaluation(success=False, feedback=feedback)
