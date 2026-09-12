"""Tests for the multi-agent orchestrator, with no API calls.

`plan()` is driven by a scripted FakeProvider; `run()` has `run_agent` stubbed
so we exercise decomposition and aggregation without launching real agents.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.config import Config
from harness.loop import AgentResult
from harness.orchestrator import Orchestrator
from harness.providers import LLMResponse, Provider, ToolCall


class FakeProvider(Provider):
    def __init__(self, response: LLMResponse) -> None:
        self._response = response

    def send_user(self, text: str) -> LLMResponse:
        return self._response

    def send_tool_results(self, results):  # type: ignore[override]
        return LLMResponse(done=True)


def _config(tmp: str) -> Config:
    cfg = Config()
    cfg.workspace = Path(tmp) / "workspace"
    cfg.event_log = Path(tmp) / "events.jsonl"
    return cfg


class OrchestratorTest(unittest.TestCase):
    def test_plan_parses_subtasks(self) -> None:
        plan_call = ToolCall(
            "1",
            "submit_plan",
            {
                "subtasks": [
                    {"title": "Model", "description": "Write the model."},
                    {"title": "Tests", "description": "Write the tests."},
                ]
            },
        )
        fake = FakeProvider(LLMResponse(tool_calls=[plan_call]))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=fake):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual([s.title for s in subtasks], ["Model", "Tests"])

    def test_plan_falls_back_to_single_subtask(self) -> None:
        fake = FakeProvider(LLMResponse(text="no plan", done=True))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=fake):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual(len(subtasks), 1)
        self.assertEqual(subtasks[0].title, "main")

    def test_plan_empty_submit_plan_falls_back(self) -> None:
        # submit_plan called, but with an empty subtasks list -> fallback.
        empty_call = ToolCall("1", "submit_plan", {"subtasks": []})
        fake = FakeProvider(LLMResponse(tool_calls=[empty_call]))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=fake):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual(len(subtasks), 1)
        self.assertEqual(subtasks[0].title, "main")

    def test_run_stops_on_subtask_failure(self) -> None:
        plan_call = ToolCall(
            "1",
            "submit_plan",
            {
                "subtasks": [
                    {"title": "First step", "description": "do A"},
                    {"title": "Second step", "description": "do B"},
                ]
            },
        )
        fake = FakeProvider(LLMResponse(tool_calls=[plan_call]))
        calls: list[str] = []

        def failing_run_agent(desc: str, cfg: Config) -> AgentResult:
            calls.append(desc)
            return AgentResult(success=False, summary="failed", steps=1)

        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=fake), patch(
                "harness.orchestrator.run_agent", side_effect=failing_run_agent
            ):
                outcome = Orchestrator(_config(tmp)).run("build two things")

        self.assertFalse(outcome.success)
        # Stopped after the first failure; the second subtask never ran.
        self.assertEqual(calls, ["do A"])
        self.assertEqual(len(outcome.subtasks), 1)

    def test_run_aggregates_subtasks(self) -> None:
        plan_call = ToolCall(
            "1",
            "submit_plan",
            {
                "subtasks": [
                    {"title": "First step", "description": "do A"},
                    {"title": "Second step", "description": "do B"},
                ]
            },
        )
        fake = FakeProvider(LLMResponse(tool_calls=[plan_call]))
        seen: list[tuple[str, Path]] = []

        def fake_run_agent(desc: str, cfg: Config) -> AgentResult:
            seen.append((desc, cfg.workspace))
            return AgentResult(success=True, summary=f"did: {desc}", steps=1)

        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=fake), patch(
                "harness.orchestrator.run_agent", side_effect=fake_run_agent
            ):
                outcome = Orchestrator(_config(tmp)).run("build two things")

        self.assertTrue(outcome.success)
        self.assertEqual(len(outcome.subtasks), 2)
        # Each subtask ran in its own distinct sub-workspace.
        workspaces = {str(ws) for _, ws in seen}
        self.assertEqual(len(workspaces), 2)
        self.assertTrue(any("first-step" in w for w in workspaces))


if __name__ == "__main__":
    unittest.main()
