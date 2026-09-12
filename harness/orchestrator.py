"""Iterative multi-agent orchestration over one shared workspace.

A planner decomposes a high-level goal into ordered subtasks. Subtasks run
sequentially as isolated coding agents (`run_agent`) but against ONE shared
workspace, so each builds on the last. After each subtask its changes are
committed as a checkpoint; a failed subtask is rolled back and the planner gets
one repair attempt. Between successful subtasks the planner may re-plan the
remaining work. When the plan is exhausted, an optional whole-goal verification
runs the configured test command against the shared workspace.

Planning reuses the vendor-neutral Provider layer, so orchestration works across
Anthropic / OpenAI / Google. Each planning call uses a fresh single-turn
provider (a submit_plan tool call), which keeps the Anthropic tool-use contract
valid without threading tool results back.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from harness.checkpoint import Checkpointer, GitCheckpointer
from harness.config import Config
from harness.evaluator import Evaluator
from harness.loop import AgentResult, run_agent
from harness.providers import ToolSpec, build_provider
from harness.sandbox import Sandbox
from harness.state import State

PLANNER_SYSTEM = """\
You are a planning agent for a team of coding agents that share one workspace.
Break the goal into a small number of ordered, self-contained subtasks; ordering
encodes dependency (a subtask may build on files left by earlier ones). Keep each
subtask concrete and independently actionable. Call submit_plan; do not do the
work yourself.
"""

PLAN_TOOL = ToolSpec(
    name="submit_plan",
    description="Submit the ordered list of subtasks (empty list means: nothing more to do).",
    input_schema={
        "type": "object",
        "properties": {
            "subtasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short subtask name."},
                        "description": {
                            "type": "string",
                            "description": "Self-contained instructions for one agent.",
                        },
                    },
                    "required": ["title", "description"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["subtasks"],
        "additionalProperties": False,
    },
)


@dataclass
class Subtask:
    title: str
    description: str


@dataclass
class SubtaskResult:
    title: str
    checkpoint: str
    result: AgentResult


@dataclass
class OrchestratorResult:
    success: bool
    summary: str
    subtasks: list[SubtaskResult]
    aborted: bool = False
    verified: bool | None = None  # None when no whole-goal verification ran


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "subtask"


def _log(msg: str) -> None:
    print(f"\033[2m[orchestrator]\033[0m {msg}", flush=True)


_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def _workspace_summary(workspace: Path, limit: int = 50) -> str:
    """A short listing of workspace files to orient the planner.

    Prunes VCS/dependency/build dirs and stops walking once past `limit`, so a
    large workspace doesn't cost a full tree walk on every planning round.
    """
    if not workspace.exists():
        return "(empty)"
    files: list[str] = []
    truncated = False
    for root, dirs, names in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in names:
            files.append(os.path.relpath(os.path.join(root, name), workspace))
            if len(files) > limit:
                truncated = True
                break
        if truncated:
            break
    if not files:
        return "(empty)"
    files.sort()
    listing = "\n".join(files[:limit])
    return listing + ("\n… (+more)" if truncated else "")


class Orchestrator:
    def __init__(self, config: Config | None = None, checkpointer: Checkpointer | None = None) -> None:
        self.config = config or Config()
        self.checkpointer = checkpointer

    # --- planning -----------------------------------------------------------

    def _plan_call(self, prompt: str) -> list[Subtask]:
        """One single-turn planning request; returns the parsed subtasks (may be empty)."""
        provider = build_provider(
            self.config.provider,
            self.config.model,
            PLANNER_SYSTEM,
            [PLAN_TOOL],
            max_tokens=self.config.max_tokens,
            effort=self.config.effort,
        )
        response = provider.send_user(prompt)
        for call in response.tool_calls:
            if call.name == "submit_plan":
                return [
                    Subtask(title=str(s["title"]), description=str(s["description"]))
                    for s in call.input.get("subtasks", [])
                    if s.get("title") and s.get("description")
                ]
        return []

    def plan(self, goal: str) -> list[Subtask]:
        """Initial decomposition. Falls back to a single subtask if the planner is silent."""
        subtasks = self._plan_call(
            f"Goal:\n{goal}\n\nDecompose it and call submit_plan with the subtasks."
        )
        return subtasks or [Subtask(title="main", description=goal)]

    def _replan(self, goal: str, completed: list[SubtaskResult], remaining: list[Subtask]) -> list[Subtask]:
        done = "\n".join(f"- {c.title}" for c in completed) or "(none)"
        rem = "\n".join(f"- {s.title}" for s in remaining) or "(none)"
        return self._plan_call(
            f"Goal:\n{goal}\n\nCompleted subtasks:\n{done}\n\nRemaining plan:\n{rem}\n\n"
            f"Current workspace files:\n{_workspace_summary(self.config.workspace)}\n\n"
            "Adjust the REMAINING subtasks if the progress warrants it and call submit_plan "
            "with only the remaining subtasks (do not repeat completed ones; empty means done)."
        )

    def _repair(self, goal: str, failed: Subtask, result: AgentResult, completed: list[SubtaskResult]) -> list[Subtask]:
        done = "\n".join(f"- {c.title}" for c in completed) or "(none)"
        return self._plan_call(
            f"Goal:\n{goal}\n\nCompleted subtasks:\n{done}\n\n"
            f"The subtask '{failed.title}' FAILED. Its agent reported:\n{result.summary}\n\n"
            f"Current workspace files:\n{_workspace_summary(self.config.workspace)}\n\n"
            "Propose revised remaining subtasks (you may retry the failed one differently) and "
            "call submit_plan. Return an empty list to give up."
        )

    # --- execution ----------------------------------------------------------

    def _worker_task(self, goal: str, subtask: Subtask, completed: list[SubtaskResult]) -> str:
        done = "\n".join(f"- {c.title}" for c in completed)
        context = f"Overall goal:\n{goal}\n\n"
        if done:
            context += f"Already completed by earlier agents (their work is in the workspace):\n{done}\n\n"
        return f"{context}Your subtask:\n{subtask.description}"

    def run(self, goal: str) -> OrchestratorResult:
        self.config.ensure_dirs()
        sandbox = Sandbox(self.config.workspace, self.config.command_timeout)
        checkpointer = self.checkpointer or GitCheckpointer(
            self.config.workspace, self.config.command_timeout
        )
        evaluator = Evaluator(self.config.test_command)
        state = State(task=goal, event_log_path=self.config.event_log)

        checkpointer.init()
        baseline = checkpointer.commit("orchestrator: start")
        last_checkpoint = baseline

        remaining = self.plan(goal)[: self.config.max_subtasks]
        state.record("plan_created", goal=goal, subtasks=[s.title for s in remaining])
        _log(f"plan: {[s.title for s in remaining]}")

        completed: list[SubtaskResult] = []
        replans_left = self.config.max_replans
        executed = 0
        aborted = False

        # Sub-agents share the workspace; the whole-goal test runs once at the end,
        # so per-subtask evaluation is disabled here.
        sub_config = replace(self.config, test_command="")

        while remaining and executed < self.config.max_subtasks:
            subtask = remaining.pop(0)
            executed += 1
            _log(f"[{executed}] {subtask.title}")
            state.record("subtask_started", title=subtask.title)
            try:
                result = run_agent(self._worker_task(goal, subtask, completed), sub_config)
            except Exception as exc:  # a crash is treated like a failed subtask
                state.record("subtask_error", title=subtask.title, error=f"{type(exc).__name__}: {exc}")
                result = AgentResult(success=False, summary=f"error: {type(exc).__name__}: {exc}", steps=0)

            if result.success:
                checkpoint = checkpointer.commit(f"subtask: {subtask.title}")
                last_checkpoint = checkpoint
                completed.append(SubtaskResult(subtask.title, checkpoint, result))
                state.record("subtask_done", title=subtask.title, success=True, checkpoint=checkpoint)
                # Re-plan the tail while there is work left and budget remains.
                if remaining and replans_left > 0:
                    replans_left -= 1
                    remaining = self._replan(goal, completed, remaining)[
                        : max(0, self.config.max_subtasks - executed)
                    ]
                    state.record("replan", remaining=[s.title for s in remaining])
                continue

            # Failure: roll back and try to repair once (subject to the budget).
            state.record("subtask_done", title=subtask.title, success=False)
            checkpointer.rollback(last_checkpoint)
            state.record("subtask_rolled_back", to=last_checkpoint)
            if replans_left <= 0:
                aborted = True
                state.record("orchestration_aborted", reason="replan budget exhausted", after=subtask.title)
                completed.append(SubtaskResult(subtask.title, last_checkpoint, result))
                break
            replans_left -= 1
            repair = self._repair(goal, subtask, result, completed)[: self.config.max_subtasks]
            state.record("replan", phase="repair", remaining=[s.title for s in repair])
            if not repair:
                aborted = True
                state.record("orchestration_aborted", reason="planner gave up", after=subtask.title)
                completed.append(SubtaskResult(subtask.title, last_checkpoint, result))
                break
            remaining = repair

        # Whole-goal verification (only if we didn't abort and a test command is set).
        verified: bool | None = None
        if not aborted and evaluator.enabled:
            evaluation = evaluator.check(sandbox)
            verified = evaluation.success
            state.record("whole_goal_verified", success=verified)

        success = (not aborted) and (verified is None or verified)
        state.record("orchestration_done", success=success, subtasks=len(completed), verified=verified)
        summary = _render_summary(goal, completed, aborted=aborted, verified=verified)
        return OrchestratorResult(
            success=success, summary=summary, subtasks=completed, aborted=aborted, verified=verified
        )


def _render_summary(
    goal: str, results: list[SubtaskResult], *, aborted: bool, verified: bool | None
) -> str:
    lines = [f"Goal: {goal}", ""]
    for i, r in enumerate(results, start=1):
        mark = "✓" if r.result.success else "✗"
        short = (r.checkpoint or "")[:8]
        lines.append(f"{mark} [{i}] {r.title} ({r.result.steps} steps) @ {short}")
    if aborted:
        lines.append("\n⚠ orchestration aborted before completing the plan.")
    if verified is not None:
        lines.append(f"\nWhole-goal verification: {'passed' if verified else 'FAILED'}.")
    return "\n".join(lines)
