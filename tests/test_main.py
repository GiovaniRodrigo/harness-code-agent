"""Tests for the CLI wiring in main.py (no model calls)."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

import main
from harness.loop import AgentResult
from harness.orchestrator import OrchestratorResult


class CliTest(unittest.TestCase):
    def test_provider_override_repicks_default_model(self) -> None:
        argv = ["main.py", "--provider", "openai", "do something"]
        with patch.object(sys, "argv", argv), patch.object(
            main, "run_agent", return_value=AgentResult(True, "ok", 1)
        ) as run_agent:
            rc = main.main()
        config = run_agent.call_args.args[1]
        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model, "gpt-4o")  # re-picked default for the provider
        self.assertEqual(rc, 0)

    def test_explicit_model_is_kept(self) -> None:
        argv = ["main.py", "--provider", "google", "--model", "gemini-2.5-flash", "task"]
        with patch.object(sys, "argv", argv), patch.object(
            main, "run_agent", return_value=AgentResult(True, "ok", 1)
        ) as run_agent:
            main.main()
        config = run_agent.call_args.args[1]
        self.assertEqual(config.provider, "google")
        self.assertEqual(config.model, "gemini-2.5-flash")

    def test_orchestrate_flag_routes_to_orchestrator(self) -> None:
        outcome = OrchestratorResult(success=True, summary="orch", subtasks=[], aborted=False)

        class FakeOrchestrator:
            def __init__(self, config) -> None:
                pass

            def run(self, task: str) -> OrchestratorResult:
                return outcome

        argv = ["main.py", "--orchestrate", "build the thing"]
        with patch.object(sys, "argv", argv), patch(
            "harness.orchestrator.Orchestrator", FakeOrchestrator
        ), patch.object(main, "run_agent", side_effect=AssertionError("should not be called")):
            rc = main.main()
        self.assertEqual(rc, 0)

    def test_failure_returns_nonzero(self) -> None:
        argv = ["main.py", "task"]
        with patch.object(sys, "argv", argv), patch.object(
            main, "run_agent", return_value=AgentResult(False, "nope", 1)
        ):
            rc = main.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
