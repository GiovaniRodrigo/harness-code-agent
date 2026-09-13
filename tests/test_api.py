"""Tests for the FastAPI control-panel layer.

Skipped unless fastapi + httpx are installed (they are optional deps). run_agent
and Orchestrator are patched so nothing hits a real model; the background run
thread finishes quickly and we poll /events for the outcome.
"""

from __future__ import annotations

import importlib.util
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_HAS_API = (
    importlib.util.find_spec("fastapi") is not None
    and importlib.util.find_spec("httpx") is not None
)

if _HAS_API:
    from fastapi.testclient import TestClient

    from harness import api
    from harness.loop import AgentResult
    from harness.orchestrator import OrchestratorResult, SubtaskResult


@unittest.skipUnless(_HAS_API, "fastapi/httpx not installed")
class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        api._RUNS.clear()
        self._tmp = tempfile.mkdtemp()
        self.client = TestClient(api.create_app(runs_dir=Path(self._tmp)))

    def _wait(self, run_id: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.client.get(f"/events/{run_id}").json()
            if data["status"] != "running":
                return data
            time.sleep(0.02)
        self.fail("run did not finish within the timeout")

    def test_run_returns_id_and_succeeds(self) -> None:
        with patch.object(api, "run_agent", return_value=AgentResult(True, "did it", 2)):
            resp = self.client.post("/run", json={"task": "hello", "provider": "anthropic"})
            self.assertEqual(resp.status_code, 200)
            run_id = resp.json()["run_id"]
            data = self._wait(run_id)
        self.assertEqual(data["status"], "succeeded")
        self.assertEqual(data["summary"], "did it")
        self.assertIn("events", data)

    def test_failed_run_reports_failed(self) -> None:
        with patch.object(api, "run_agent", return_value=AgentResult(False, "nope", 1)):
            run_id = self.client.post("/run", json={"task": "hello"}).json()["run_id"]
            data = self._wait(run_id)
        self.assertEqual(data["status"], "failed")

    def test_run_exception_reports_error(self) -> None:
        with patch.object(api, "run_agent", side_effect=RuntimeError("boom")):
            run_id = self.client.post("/run", json={"task": "hello"}).json()["run_id"]
            data = self._wait(run_id)
        self.assertEqual(data["status"], "error")
        self.assertIn("boom", data["error"])

    def test_empty_task_is_rejected(self) -> None:
        resp = self.client.post("/run", json={"task": "   "})
        self.assertEqual(resp.status_code, 400)

    def test_unknown_run_is_404(self) -> None:
        resp = self.client.get("/events/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_runs_lists_most_recent_first(self) -> None:
        with patch.object(api, "run_agent", return_value=AgentResult(True, "ok", 1)):
            id1 = self.client.post("/run", json={"task": "a"}).json()["run_id"]
            self._wait(id1)
            id2 = self.client.post("/run", json={"task": "b"}).json()["run_id"]
            self._wait(id2)
        ids = [r["run_id"] for r in self.client.get("/runs").json()["runs"]]
        self.assertEqual(ids[0], id2)
        self.assertIn(id1, ids)

    def test_orchestrated_run_surfaces_detail(self) -> None:
        outcome = OrchestratorResult(
            success=True,
            summary="orchestrated",
            subtasks=[SubtaskResult("A", "abc12345", AgentResult(True, "a", 1))],
            aborted=False,
            verified=True,
        )

        class FakeOrchestrator:
            def __init__(self, config) -> None:
                pass

            def run(self, task: str) -> OrchestratorResult:
                return outcome

        with patch.object(api, "Orchestrator", FakeOrchestrator):
            run_id = self.client.post(
                "/run", json={"task": "big goal", "orchestrate": True}
            ).json()["run_id"]
            data = self._wait(run_id)
        self.assertEqual(data["status"], "succeeded")
        self.assertTrue(data["verified"])
        self.assertEqual(data["subtasks"][0]["title"], "A")
        self.assertFalse(data["aborted"])


if __name__ == "__main__":
    unittest.main()
