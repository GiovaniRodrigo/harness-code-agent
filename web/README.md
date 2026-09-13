# Harness control panel (web)

A Next.js control panel for the coding-agent harness backend. It was generated
with [v0](https://v0.app) and talks to the harness HTTP API defined in
[`harness/api.py`](../harness/api.py).

## What it does

- **Launch a task** — task description, provider (Anthropic / OpenAI / Google),
  optional model and test command, and an "Orchestrate (multi-agent)" toggle.
  Posts to `POST /run`.
- **Live run view** — polls `GET /events/{run_id}` every second while a run is
  active, rendering a color-coded event timeline (auto-scrolled to the newest
  event) with a status badge and the final summary once the run finishes.
- **History** — lists past runs from `GET /runs`; clicking a row loads it into
  the live view.

## Backend API

The panel expects the harness API from this repo:

- `POST /run` — `{ task, provider, model?, orchestrate, test_command? }` → `{ run_id }`
- `GET /events/{run_id}` — run status, summary, error and the event log
- `GET /runs` — past runs, most recent first

Start it from the repo root (see the top-level [`README.md`](../README.md)):

```bash
pip install fastapi uvicorn   # in the venv
python -m harness.api         # serves http://127.0.0.1:8000
```

## Running the panel

```bash
cd web
pnpm install          # or npm install
cp .env.example .env.local   # optional; edit NEXT_PUBLIC_HARNESS_API if needed
pnpm dev
```

The API base URL comes from `NEXT_PUBLIC_HARNESS_API` and defaults to
`http://127.0.0.1:8000`.

> The lockfile is not committed — run your package manager's install once to
> generate one.
