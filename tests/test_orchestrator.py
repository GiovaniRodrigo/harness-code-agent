"""Tests for the iterative multi-agent orchestrator (no API calls, no git).

Planning is driven through the Provider seam (a scripted FakeProvider per
planning call), checkpointing through an in-memory FakeCheckpointer, and
subtask execution through a stubbed run_agent.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.checkpoint import Checkpointer
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


class FakeCheckpointer(Checkpointer):
    def __init__(self) -> None:
        self.commits: list[tuple[str, str]] = []
        self.rollbacks: list[str] = []
        self._n = 0

    def init(self) -> None:
        pass

    def commit(self, label: str) -> str:
        self._n += 1
        cid = f"ckpt{self._n}"
        self.commits.append((cid, label))
        return cid

    def rollback(self, checkpoint: str) -> None:
        self.rollbacks.append(checkpoint)


def _plan_provider(subtasks: list[tuple[str, str]]) -> FakeProvider:
    call = ToolCall(
        "1",
        "submit_plan",
        {"subtasks": [{"title": t, "description": d} for t, d in subtasks]},
    )
    return FakeProvider(LLMResponse(tool_calls=[call]))


def _config(tmp: str, **overrides) -> Config:
    cfg = Config()
    cfg.workspace = Path(tmp) / "workspace"
    cfg.event_log = Path(tmp) / "events.jsonl"
    cfg.test_command = ""
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _ok(_desc: str, _cfg: Config) -> AgentResult:
    return AgentResult(success=True, summary="done", steps=1)


class PlanTest(unittest.TestCase):
    def test_plan_parses_subtasks(self) -> None:
        provider = _plan_provider([("Model", "m"), ("Tests", "t")])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=provider):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual([s.title for s in subtasks], ["Model", "Tests"])

    def test_plan_falls_back_when_no_tool_call(self) -> None:
        provider = FakeProvider(LLMResponse(text="no plan", done=True))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=provider):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual([s.title for s in subtasks], ["main"])

    def test_plan_falls_back_on_empty_plan(self) -> None:
        provider = _plan_provider([])
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", return_value=provider):
                subtasks = Orchestrator(_config(tmp)).plan("build a thing")
        self.assertEqual([s.title for s in subtasks], ["main"])


class RunTest(unittest.TestCase):
    def test_happy_path_checkpoints_each_subtask(self) -> None:
        providers = [_plan_provider([("A", "do A"), ("B", "do B")]), _plan_provider([("B", "do B")])]
        ckpt = FakeCheckpointer()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", side_effect=_ok
            ):
                outcome = Orchestrator(_config(tmp), checkpointer=ckpt).run("build A and B")
        self.assertTrue(outcome.success)
        self.assertFalse(outcome.aborted)
        self.assertEqual([s.title for s in outcome.subtasks], ["A", "B"])
        # baseline + one commit per successful subtask, no rollbacks.
        self.assertEqual(len(ckpt.commits), 3)
        self.assertEqual(ckpt.rollbacks, [])

    def test_replan_changes_remaining_plan(self) -> None:
        # Initial plan is A,B,C; after A succeeds the planner re-plans the tail
        # down to a single new subtask X. B and C must be dropped.
        providers = [
            _plan_provider([("A", "do A"), ("B", "do B"), ("C", "do C")]),
            _plan_provider([("X", "do X instead")]),
        ]
        ckpt = FakeCheckpointer()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", side_effect=_ok
            ):
                outcome = Orchestrator(_config(tmp), checkpointer=ckpt).run("build it")
        self.assertTrue(outcome.success)
        self.assertEqual([s.title for s in outcome.subtasks], ["A", "X"])

    def test_subtask_exception_is_treated_as_failure(self) -> None:
        providers = [_plan_provider([("A", "do A")]), _plan_provider([])]  # repair gives up
        ckpt = FakeCheckpointer()

        def boom(_desc: str, _cfg: Config) -> AgentResult:
            raise RuntimeError("provider exploded")

        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", side_effect=boom
            ):
                outcome = Orchestrator(_config(tmp), checkpointer=ckpt).run("do A")
        # The crash is caught, rolled back, and (repair empty) aborts cleanly.
        self.assertFalse(outcome.success)
        self.assertTrue(outcome.aborted)
        self.assertEqual(len(ckpt.rollbacks), 1)

    def test_failure_triggers_rollback_and_repair(self) -> None:
        providers = [_plan_provider([("A", "do A")]), _plan_provider([("A2", "do A better")])]
        results = iter([AgentResult(False, "boom", 1), AgentResult(True, "fixed", 2)])
        ckpt = FakeCheckpointer()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", side_effect=lambda d, c: next(results)
            ):
                outcome = Orchestrator(_config(tmp), checkpointer=ckpt).run("do A")
        self.assertTrue(outcome.success)
        self.assertFalse(outcome.aborted)
        self.assertEqual([s.title for s in outcome.subtasks], ["A2"])
        self.assertEqual(len(ckpt.rollbacks), 1)  # rolled back after A failed

    def test_aborts_when_repair_gives_up(self) -> None:
        providers = [_plan_provider([("A", "do A")]), _plan_provider([])]  # repair returns nothing
        ckpt = FakeCheckpointer()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", return_value=AgentResult(False, "boom", 1)
            ):
                outcome = Orchestrator(_config(tmp), checkpointer=ckpt).run("do A")
        self.assertFalse(outcome.success)
        self.assertTrue(outcome.aborted)
        self.assertEqual(len(ckpt.rollbacks), 1)

    def test_whole_goal_verification_can_fail(self) -> None:
        providers = [_plan_provider([("A", "do A")])]
        ckpt = FakeCheckpointer()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(tmp, test_command="exit 1")
            with patch("harness.orchestrator.build_provider", side_effect=providers), patch(
                "harness.orchestrator.run_agent", side_effect=_ok
            ):
                outcome = Orchestrator(cfg, checkpointer=ckpt).run("do A")
        self.assertFalse(outcome.success)
        self.assertFalse(outcome.aborted)
        self.assertFalse(outcome.verified)


if __name__ == "__main__":
    unittest.main()
