# Spec — Iterative multi-agent orchestrator

> Status: ready-for-agent (pending publication to the issue tracker)
> Assumed design decisions (from the design discussion; correct if wrong):
> **scope** = legible reference harness; **topology** = iterative;
> **workspace** = single shared workspace with per-subtask git checkpoints.

## Problem Statement

As someone using the harness for non-trivial goals, a single coding agent in one
`run_agent` loop either runs out of steps or loses the thread on a large task
("build a small CLI app with tests and docs"). The current `Orchestrator` helps
by decomposing the goal, but it plans **once, up front**, and runs each subtask
in an **isolated sub-workspace**. That means: subtask 2 cannot build on the
files subtask 1 produced; the plan never adapts to what earlier subtasks reveal;
and a subtask failure aborts everything with no chance to re-plan. The result is
that dependent, real-world coding goals don't actually get completed by the
orchestrator today.

## Solution

Evolve the orchestrator from one-shot fan-out into an **iterative orchestrator
over one shared workspace**:

- All subtasks operate on a **single shared workspace** (like developers on one
  repo), so later subtasks see and build on earlier work.
- After each subtask, its changes are recorded as a **checkpoint** (a git commit
  in the workspace), giving an audit trail and a rollback point.
- The orchestrator **re-plans** between subtasks: it feeds the outcome of
  completed subtasks (success/failure, summary, and the current workspace state)
  back to the planner, which may adjust, add, drop, or reorder the remaining
  subtasks before continuing.
- On a subtask failure, the orchestrator gets one **re-plan/repair** attempt
  before giving up, instead of aborting immediately.
- When all subtasks complete, an optional **whole-goal verification** runs the
  configured test command against the shared workspace, so "done" means the
  integrated result works — not just that each piece finished.

Scope stays deliberately legible: sequential execution, in-process, no queue/DB.

## User Stories

1. As a harness user, I want to give the orchestrator one high-level goal, so that I don't have to decompose it into subtasks myself.
2. As a harness user, I want the planner to break the goal into ordered, self-contained subtasks, so that each sub-agent has a clear, bounded job.
3. As a harness user, I want all subtasks to share one workspace, so that a subtask that writes code can be used by a later subtask that tests it.
4. As a harness user, I want each subtask's changes committed as a checkpoint, so that I can see exactly what each sub-agent did and roll back a bad one.
5. As a harness user, I want the orchestrator to re-plan after each subtask using the latest results, so that the plan adapts to what the work reveals instead of guessing everything up front.
6. As a harness user, I want a failed subtask to trigger one repair/re-plan attempt, so that a single stumble doesn't throw away the whole run.
7. As a harness user, I want the orchestrator to stop and report clearly when it exhausts its repair budget, so that I'm not billed for a runaway loop.
8. As a harness user, I want a final whole-goal verification (my test command run against the shared workspace), so that success reflects the integrated result, not just per-subtask completion.
9. As a harness user, I want each sub-agent to receive the overall goal plus a summary of what earlier subtasks did, so that it works with context instead of in a vacuum.
10. As a harness user, I want the orchestrator to work with any configured provider (Anthropic/OpenAI/Google), so that vendor choice is orthogonal to orchestration.
11. As a harness user, I want the orchestrator to record every planning and subtask event to the event log, so that I can audit or replay the whole run.
12. As a harness user, I want a bound on the total number of subtasks and re-plans, so that decomposition can't expand without limit.
13. As a harness user, I want the final summary to show, per subtask, its title, checkpoint reference, status and step count, so that I can review the run at a glance.
14. As a harness user, I want to run the orchestrator from the CLI (`--orchestrate`) and from the HTTP API (`orchestrate: true`), so that both the terminal and the control panel can drive it.
15. As a harness user, I want the shared workspace initialized as a git repo automatically if it isn't one, so that checkpointing works without manual setup.
16. As a harness user, I want a subtask's failure and the repair attempt captured as distinct events, so that I can tell an initial failure from an unrecoverable one.
17. As a developer of the harness, I want orchestration decisions driven through the existing `Provider` seam, so that I can test planning and re-planning deterministically without API calls.
18. As a developer of the harness, I want checkpointing behind a small interface, so that I can test orchestration logic without shelling out to git in every test.

## Implementation Decisions

- **Modules.** Evolve `harness/orchestrator.py`. Introduce a checkpoint
  abstraction (a small interface with a git-backed implementation) so the
  orchestrator records a checkpoint after each subtask. Reuse the existing
  `Provider` layer for both planning and re-planning, and reuse `run_agent` as
  the sub-agent execution boundary.
- **Shared workspace.** The orchestrator runs all sub-agents against one
  workspace (the run's `config.workspace`), not per-subtask sub-directories.
  Sub-agent isolation is dropped in favor of a shared tree plus checkpoints.
- **Checkpoints.** After each subtask, the orchestrator commits the workspace
  (initializing a git repo if needed). Each checkpoint carries the subtask title
  and index. A failed subtask can be rolled back to the prior checkpoint before a
  repair attempt.
- **Planner contract.** The planner is invoked with a `submit_plan` tool. The
  plan is an ordered list of subtasks; ordering encodes dependency (a subtask may
  rely on the workspace state left by earlier ones). Contract shape:

  ```
  submit_plan(subtasks: [{ title: string, description: string }])
  ```

  Re-planning uses the same tool, additionally given the completed subtasks'
  outcomes and a short description of the current workspace state; it returns the
  remaining subtasks (possibly changed).
- **Iterative loop.** plan → run subtask → checkpoint → re-plan with results →
  repeat until no subtasks remain or a budget is hit. A single plan that never
  needs adjustment degrades gracefully to today's behavior.
- **Failure & repair policy.** On subtask failure: roll back to the last
  checkpoint, ask the planner for a repair/re-plan once; if it fails again, stop
  and report. Budgets: max total subtasks and max re-plans (config-driven,
  reusing the env-var configuration style).
- **Worker context.** Each sub-agent's task text includes the overall goal and a
  brief summary of completed subtasks; the shared workspace supplies the rest.
- **Whole-goal verification.** If a test command is configured, run it against
  the shared workspace after the last subtask; failure marks the run unsuccessful
  and is recorded as an event.
- **Provider/model.** One provider/model for the whole run (planner and all
  workers), taken from `Config`. Per-subtask model routing is not introduced.
- **Entry points.** CLI `--orchestrate` and API `orchestrate: true` are
  unchanged at the surface; they call the evolved orchestrator.
- **Events.** New event kinds: `plan_created`, `replan`, `subtask_started`,
  `subtask_done`, `checkpoint_created`, `subtask_rolled_back`,
  `orchestration_aborted`, `whole_goal_verified`, `orchestration_done`.

## Testing Decisions

- **What makes a good test here:** assert observable outcomes — which subtasks
  were planned and re-planned, that a checkpoint exists after each subtask, that a
  failure triggers rollback + one repair, that budgets stop the loop, and that the
  aggregate status reflects whole-goal verification. Do not assert internal call
  order or private state.
- **Primary seam (prefer one):** the `Provider` interface. A scripted
  `FakeProvider` returns `submit_plan` tool calls for the initial plan and each
  re-plan, exactly as in the existing tests — no network, deterministic.
- **Second boundary:** `run_agent` is stubbed to return chosen `AgentResult`s
  (success/failure) so the orchestration logic is exercised without launching real
  agents.
- **Checkpoint seam:** test through the checkpoint interface with a fake
  implementation (record commits/rollbacks in memory) so tests don't depend on a
  real git binary; a small number of git-backed integration tests may cover the
  real implementation against a temp repo.
- **Modules tested:** `harness/orchestrator.py` (plan parse, iterative re-plan,
  failure→rollback→repair, budgets, aggregation, whole-goal verification).
- **Prior art:** `tests/test_orchestrator.py` and `tests/test_loop.py` — both
  drive the loop/orchestrator via `FakeProvider` and `patch(...run_agent)`. Follow
  the same pattern (stdlib `unittest`, `tempfile` workspaces).

## Out of Scope

- Parallel/concurrent subtask execution.
- Persistence beyond the in-memory/event-log state (no DB, no queue).
- Recursive sub-orchestrators (a subtask spawning its own orchestrator).
- Per-subtask provider/model routing.
- Real-time streaming (SSE/WebSocket) to the control panel — polling stays.
- Multi-user, auth, and any hosted/shared deployment concerns.
- Conflict resolution for concurrent edits (avoided by the sequential + shared
  workspace design).

## Further Notes

- The evolution is backward-compatible at the entry points: `--orchestrate` and
  the API `orchestrate` flag keep working; only the orchestrator's internals and
  event vocabulary change.
- The git-checkpoint design assumes `git` is available in the environment (it is
  here). The checkpoint interface keeps that dependency swappable and testable.
- OpenAI and Google provider backends remain unverified against live SDKs
  (Anthropic is the base dependency); orchestration relies only on the normalized
  `Provider` contract, so it is provider-agnostic by construction.
