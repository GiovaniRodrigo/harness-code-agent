"""Optional HTTP API for the harness (FastAPI).

Exposes the harness to a frontend (e.g. a panel generated with v0):
- POST /run           -> launch a task, returns {run_id}
- GET  /events/{id}   -> poll a run's event log + status + summary
- GET  /runs          -> list past runs (most recent first)

Runs execute in a background thread; state is in-memory, which is fine for
local/single-process use. For anything shared or durable, back it with a store.

Install:  pip3 install fastapi uvicorn
Run:      python3 -m harness.api   # serves on http://127.0.0.1:8000
"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from harness.config import Config
from harness.loop import run_agent
from harness.orchestrator import Orchestrator
from harness.providers import DEFAULT_MODELS

_RUNS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


class RunRequest(BaseModel):
    task: str
    provider: str | None = None
    model: str | None = None
    orchestrate: bool = False
    test_command: str | None = None


def _build_config(req: RunRequest, workspace: Path, event_log: Path) -> Config:
    config = Config()
    if req.provider:
        config.provider = req.provider.lower()
        # Switching provider without a model re-picks that provider's default.
        config.model = req.model or DEFAULT_MODELS.get(config.provider, config.model)
    elif req.model:
        config.model = req.model
    if req.test_command is not None:
        config.test_command = req.test_command
    config.workspace = workspace
    config.event_log = event_log
    return config


def _execute(run_id: str, req: RunRequest, config: Config) -> None:
    try:
        if req.orchestrate:
            outcome = Orchestrator(config).run(req.task)
            success, summary = outcome.success, outcome.summary
        else:
            result = run_agent(req.task, config)
            success, summary = result.success, result.summary
        status, error = "succeeded" if success else "failed", None
    except Exception as exc:  # surface harness/provider errors to the client
        status, summary, error = "error", "", f"{type(exc).__name__}: {exc}"
    with _LOCK:
        _RUNS[run_id].update(status=status, summary=summary, error=error)


def _read_events(event_log: Path) -> list[dict[str, Any]]:
    if not event_log.exists():
        return []
    events = []
    for line in event_log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def create_app(runs_dir: Path | None = None) -> FastAPI:
    base = (runs_dir or Path("./harness_runs")).resolve()
    base.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="harness_ai control panel API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/run")
    def run(req: RunRequest) -> dict[str, str]:
        if not req.task.strip():
            raise HTTPException(status_code=400, detail="task is required")
        run_id = uuid.uuid4().hex
        workspace = base / run_id / "workspace"
        event_log = base / run_id / "events.jsonl"
        config = _build_config(req, workspace, event_log)
        with _LOCK:
            _RUNS[run_id] = {
                "run_id": run_id,
                "task": req.task,
                "provider": config.provider,
                "model": config.model,
                "orchestrate": req.orchestrate,
                "status": "running",
                "summary": "",
                "error": None,
                "event_log": str(event_log),
            }
        threading.Thread(target=_execute, args=(run_id, req, config), daemon=True).start()
        return {"run_id": run_id}

    @app.get("/events/{run_id}")
    def events(run_id: str) -> dict[str, Any]:
        with _LOCK:
            run = _RUNS.get(run_id)
            if run is None:
                raise HTTPException(status_code=404, detail="unknown run_id")
            run = dict(run)
        return {**run, "events": _read_events(Path(run["event_log"]))}

    @app.get("/runs")
    def runs() -> dict[str, Any]:
        with _LOCK:
            items = [
                {k: v for k, v in r.items() if k != "event_log"} for r in _RUNS.values()
            ]
        return {"runs": list(reversed(items))}

    return app


app = None  # lazily created in __main__ to avoid importing fastapi on package import


def main() -> None:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
