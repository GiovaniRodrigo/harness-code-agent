"""Multi-agent orchestration.

A planner decomposes a high-level goal into independent subtasks, then each
subtask runs as its own isolated coding agent (`run_agent`) in a dedicated
sub-workspace. Results are aggregated. The planner reuses the vendor-neutral
Provider layer, so orchestration works across Anthropic / OpenAI / Google too.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from harness.config import Config
from harness.loop import AgentResult, run_agent
from harness.providers import ToolSpec, build_provider
from harness.state import State

PLANNER_SYSTEM = """\
You are a planning agent. Given a high-level goal, break it into a small number
of independent, concretely-actionable subtasks that separate coding agents can
each carry out on their own. Keep subtasks self-contained and ordered by
dependency. Call submit_plan with the list; do not do the work yourself.
"""

PLAN_TOOL = ToolSpec(
    name="submit_plan",
    description="Submit the decomposition of the goal into independent subtasks.",
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
    workspace: str
    result: AgentResult


@dataclass
class OrchestratorResult:
    success: bool
    summary: str
    subtasks: list[SubtaskResult]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "subtask"


def _log(msg: str) -> None:
    print(f"\033[2m[orchestrator]\033[0m {msg}", flush=True)


class Orchestrator:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()

    def plan(self, goal: str) -> list[Subtask]:
        """Ask the planner to decompose the goal. Falls back to a single task."""
        provider = build_provider(
            self.config.provider,
            self.config.model,
            PLANNER_SYSTEM,
            [PLAN_TOOL],
            max_tokens=self.config.max_tokens,
            effort=self.config.effort,
        )
        response = provider.send_user(
            f"Goal:\n{goal}\n\nDecompose it and call submit_plan with the subtasks."
        )
        for call in response.tool_calls:
            if call.name == "submit_plan":
                raw = call.input.get("subtasks", [])
                subtasks = [
                    Subtask(title=str(s["title"]), description=str(s["description"]))
                    for s in raw
                    if s.get("title") and s.get("description")
                ]
                if subtasks:
                    return subtasks
        # Planner returned no usable plan: run the goal as a single subtask.
        return [Subtask(title="main", description=goal)]

    def run(self, goal: str) -> OrchestratorResult:
        self.config.ensure_dirs()
        state = State(task=goal, event_log_path=self.config.event_log)
        subtasks = self.plan(goal)
        state.record("plan_created", goal=goal, subtasks=[s.title for s in subtasks])
        _log(f"plan: {len(subtasks)} subtask(s) -> {[s.title for s in subtasks]}")

        results: list[SubtaskResult] = []
        for i, subtask in enumerate(subtasks, start=1):
            sub_workspace = self.config.workspace / f"{i:02d}-{_slug(subtask.title)}"
            sub_config = replace(self.config, workspace=sub_workspace)
            _log(f"[{i}/{len(subtasks)}] {subtask.title} -> {sub_workspace}")
            result = run_agent(subtask.description, sub_config)
            state.record(
                "subtask_done",
                title=subtask.title,
                success=result.success,
                steps=result.steps,
            )
            results.append(
                SubtaskResult(title=subtask.title, workspace=str(sub_workspace), result=result)
            )
            # Subtasks are ordered by dependency, so a failure likely breaks the
            # ones after it — stop and report rather than compounding the failure.
            if not result.success:
                remaining = len(subtasks) - i
                _log(f"subtask '{subtask.title}' failed; stopping ({remaining} subtask(s) skipped).")
                state.record("orchestration_aborted", after=subtask.title, skipped=remaining)
                break

        success = all(r.result.success for r in results)
        summary = _render_summary(goal, results)
        state.record("orchestration_done", success=success, subtasks=len(results))
        return OrchestratorResult(success=success, summary=summary, subtasks=results)


def _render_summary(goal: str, results: list[SubtaskResult]) -> str:
    lines = [f"Goal: {goal}", ""]
    for i, r in enumerate(results, start=1):
        mark = "✓" if r.result.success else "✗"
        lines.append(f"{mark} [{i}] {r.title} ({r.result.steps} steps) — {r.workspace}")
        if r.result.summary:
            lines.append(f"    {r.result.summary.splitlines()[0]}")
    return "\n".join(lines)
