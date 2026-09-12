"""Integration tests for the agent loop, driven by a scripted FakeProvider.

The provider layer is the seam: by swapping in a fake, we exercise the whole
loop (tool execution, policy blocking, evaluator, step ceiling) with no API
calls and no network.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.config import Config
from harness.loop import run_agent
from harness.providers import LLMResponse, Provider, ToolCall


class FakeProvider(Provider):
    """Returns scripted LLMResponses; records what the loop sends it."""

    def __init__(self, script: list[LLMResponse], default: LLMResponse | None = None) -> None:
        self.script = list(script)
        self.default = default
        self.received: list[tuple[str, object]] = []

    def _pop(self) -> LLMResponse:
        if self.script:
            return self.script.pop(0)
        if self.default is not None:
            return self.default
        return LLMResponse(text="", done=True)

    def send_user(self, text: str) -> LLMResponse:
        self.received.append(("user", text))
        return self._pop()

    def send_tool_results(self, results):  # type: ignore[override]
        self.received.append(("tool_results", results))
        return self._pop()


def _config(tmp: str, **overrides) -> Config:
    cfg = Config()
    cfg.workspace = Path(tmp) / "workspace"
    cfg.event_log = Path(tmp) / "events.jsonl"
    cfg.test_command = ""  # evaluator disabled unless a test overrides
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


class AgentLoopTest(unittest.TestCase):
    def test_writes_file_then_finishes(self) -> None:
        script = [
            LLMResponse(
                text="working",
                tool_calls=[
                    ToolCall("1", "write_file", {"path": "hello.py", "content": "print('hi')"})
                ],
            ),
            LLMResponse(text="done: created hello.py", done=True),
        ]
        fake = FakeProvider(script)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(tmp)
            with patch("harness.loop.build_provider", return_value=fake):
                result = run_agent("create hello.py", cfg)
            self.assertTrue(result.success)
            self.assertEqual(result.summary, "done: created hello.py")
            self.assertTrue((cfg.workspace / "hello.py").exists())

    def test_policy_blocks_dangerous_command(self) -> None:
        script = [
            LLMResponse(tool_calls=[ToolCall("1", "run_command", {"command": "rm -rf /"})]),
            LLMResponse(text="stopped", done=True),
        ]
        fake = FakeProvider(script)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(tmp)
            with patch("harness.loop.build_provider", return_value=fake):
                run_agent("do something dangerous", cfg)
        results = [payload for kind, payload in fake.received if kind == "tool_results"]
        self.assertEqual(len(results), 1)
        output = results[0][0]
        self.assertTrue(output.is_error)
        self.assertIn("blocked", output.content.lower())

    def test_evaluator_retries_then_gives_up(self) -> None:
        # The model always "finishes", but the test command keeps failing, so
        # the evaluator hands feedback back until the retry budget is spent.
        fake = FakeProvider([], default=LLMResponse(text="done", done=True))
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(tmp, test_command="exit 1", max_eval_retries=2)
            with patch("harness.loop.build_provider", return_value=fake):
                result = run_agent("make the tests pass", cfg)
            self.assertFalse(result.success)
            # 1 initial task send + feedback for retries 1 and 2 (gives up at 3).
            user_sends = [payload for kind, payload in fake.received if kind == "user"]
            self.assertEqual(len(user_sends), 3)
            self.assertEqual(result.steps, 3)

    def test_hits_step_ceiling(self) -> None:
        # Provider never finishes — always asks for another tool call.
        fake = FakeProvider(
            [], default=LLMResponse(tool_calls=[ToolCall("1", "list_dir", {"path": "."})])
        )
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _config(tmp, max_steps=3)
            with patch("harness.loop.build_provider", return_value=fake):
                result = run_agent("loop forever", cfg)
            self.assertFalse(result.success)
            self.assertEqual(result.steps, 3)


if __name__ == "__main__":
    unittest.main()
