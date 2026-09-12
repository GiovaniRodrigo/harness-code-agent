# harness_ai — coding-agent harness (MVP)

A minimal but real harness for a **coding agent**. The core idea: the LLM is
not the system — it is a component inside a system that provides **context,
tools, state, limits, and verifiable feedback**.

```
Task
  │
  ▼
┌──────────────────────── Harness ────────────────────────┐
│  context → LLM (loop) → policy → sandbox → tools         │
│                 │                                        │
│                 ▼                                        │
│            state / event log                             │
│                 │                                        │
│                 ▼                                        │
│            evaluator (runs the tests)                    │
│           pass ──► done    |     fail ──► feedback ──► LLM│
└──────────────────────────────────────────────────────────┘
```

## Components

| File | Role |
|---|---|
| `harness/loop.py` | The agent loop — stitches everything together. A **manual** loop (`while stop_reason == "tool_use"`) so every step stays visible. |
| `harness/providers/` | Vendor-neutral `Provider` layer — one backend per LLM vendor (Anthropic, OpenAI, Google), selected by `HARNESS_PROVIDER`. |
| `harness/tools/` | The `Tool` base, the `registry`, and the tools: `read_file`, `write_file`, `list_dir`, `run_command`. The model only acts through these. |
| `harness/sandbox.py` | Confines paths and commands to the workspace; command timeout. |
| `harness/policies.py` | Guardrails: blocks clearly dangerous commands before they run. |
| `harness/context.py` | System prompt (cacheable) and truncation of large outputs. |
| `harness/state.py` | History + an append-only **event log** (JSONL) for audit/replay. |
| `harness/evaluator.py` | Closes the loop: runs the test command and hands failures back to the agent. |
| `harness/config.py` | Environment-based configuration, with defaults. |
| `main.py` | CLI. |

## Installation

```bash
pip3 install -r requirements.txt          # installs the Anthropic backend
export ANTHROPIC_API_KEY=sk-ant-...        # or use `ant auth login`
```

To use another backend, install its SDK and set the matching key:

```bash
pip3 install openai        && export OPENAI_API_KEY=...   # HARNESS_PROVIDER=openai
pip3 install google-genai  && export GOOGLE_API_KEY=...   # HARNESS_PROVIDER=google
```

> Use `python3`/`pip3`. If you prefer to type just `python`/`pip`, install the
> `python-is-python3` package (`sudo apt install python-is-python3`).

## Usage

```bash
# Inline task (no automatic verification)
python3 main.py "Create hello.py that prints 'hello' and run it."

# With the evaluator: the agent only finishes once the tests pass
python3 main.py -f example/task.md --test-command "python3 -m pytest -q"
```

The agent's output (created files, etc.) lands in `./workspace/`. Every step is
recorded in `./harness_events.jsonl`.

## Configuration

All variables are optional (see `.env.example`):

- `HARNESS_PROVIDER` — `anthropic` (default) | `openai` | `google`.
- `HARNESS_MODEL` — model id. If empty, a per-provider default is used
  (`claude-opus-5`, `gpt-4o`, `gemini-2.5-pro`).
- `HARNESS_EFFORT` — `low` | `medium` | `high` | `xhigh` | `max` (Anthropic only).
- `HARNESS_WORKSPACE` — the agent's working directory.
- `HARNESS_TEST_COMMAND` — the evaluator command (e.g. `pytest -q`).
- `HARNESS_MAX_STEPS`, `HARNESS_MAX_EVAL_RETRIES`, `HARNESS_CMD_TIMEOUT`, `HARNESS_MAX_TOOL_OUTPUT`.

## Providers (multi-vendor)

The harness is vendor-neutral. The agent loop talks to models only through the
`Provider` interface in `harness/providers/`, so the same loop, tools, sandbox,
policies and evaluator work across vendors. Each provider owns its native
conversation history and translates the harness's normalized tool specs / tool
results to and from its SDK's wire format.

```bash
HARNESS_PROVIDER=openai python3 main.py "Create hello.py and run it."
HARNESS_PROVIDER=google HARNESS_MODEL=gemini-2.5-flash python3 main.py -f example/task.md
```

Only the Anthropic backend is smoke-tested here (its SDK is the base
dependency). The OpenAI and Google backends are written against their current
SDKs but not exercised in CI — verify against your installed SDK version.

## Orchestration (multi-agent)

For larger goals, a planner agent decomposes the goal into independent subtasks
and runs each as its own isolated coding agent (in a dedicated sub-workspace),
then aggregates the results. The planner reuses the same Provider layer, so it
works across vendors too.

```bash
python3 main.py --orchestrate "Build a small CLI todo app with pytest tests."
```

Each subtask lands in `workspace/NN-<slug>/`; see `harness/orchestrator.py`.

## Security (read before real use)

`sandbox.py` confines paths and `policies.py` blocks obvious accidents, but
this is **not strong isolation**. `run_command` runs a real shell. For
untrusted tasks, run the whole harness inside a disposable container or VM and
restrict the network.

## Next steps (to grow beyond the MVP)

- **Streaming** responses and `task_budget` for long tasks.
- **Compaction** / context editing once the history grows.
- **Human-in-the-loop**: confirm irreversible actions instead of just blocking them.
- **Checkpoints**: resume a run from the event log.
- A real sandbox (per-session container) with CPU/memory/network limits.
