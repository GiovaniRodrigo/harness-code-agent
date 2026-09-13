#!/usr/bin/env bash
#
# watch-and-update.sh — poll the remote branch and re-deploy the local stack.
#
# Watches `origin/main` (configurable). Whenever the remote branch advances
# (e.g. a PR is merged), it fast-forwards the local checkout and restarts the
# whole system (`make up`: API on :8000 + web panel on :3000). Poll-based, so
# it needs nothing beyond git and the tools `make up` already uses.
#
# Usage:
#   scripts/watch-and-update.sh          # or: make watch
#
# Tunables (env vars):
#   WATCH_BRANCH   branch to track      (default: main)
#   WATCH_REMOTE   remote to fetch      (default: origin)
#   WATCH_INTERVAL seconds between polls (default: 30)
#
# Stop with Ctrl+C — the watcher and the stack it started both shut down.

set -euo pipefail

BRANCH="${WATCH_BRANCH:-main}"
REMOTE="${WATCH_REMOTE:-origin}"
INTERVAL="${WATCH_INTERVAL:-30}"

# Repo root is the script's parent directory.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG="$ROOT/harness_watch.stack.log"     # stack (make up) output goes here
PIDFILE="$(mktemp)"                      # holds the stack's process-group id
STACK_PGID=""

log() { printf '\033[2m[watch]\033[0m %s\n' "$*"; }

start_stack() {
  : > "$LOG"
  log "starting stack (make up); output -> $LOG"
  # setsid puts the stack in its own session/process group so we can signal the
  # whole tree (make + uvicorn + next) without touching this watcher. The inner
  # shell records the new group leader's pid (== pgid) for stop_stack.
  setsid bash -c "echo \$\$ > '$PIDFILE'; exec make up" >>"$LOG" 2>&1 &
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [ -s "$PIDFILE" ] && break
    sleep 0.3
  done
  STACK_PGID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$STACK_PGID" ]; then
    log "stack running (pgid $STACK_PGID)"
  else
    log "warning: could not determine stack pgid; restart may be unclean"
  fi
}

stop_stack() {
  [ -n "$STACK_PGID" ] || return 0
  log "stopping stack (pgid $STACK_PGID)…"
  kill -TERM "-$STACK_PGID" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "-$STACK_PGID" 2>/dev/null || break
    sleep 0.5
  done
  kill -KILL "-$STACK_PGID" 2>/dev/null || true
  STACK_PGID=""
}

cleanup() {
  trap - INT TERM EXIT
  log "shutting down"
  stop_stack
  rm -f "$PIDFILE"
  exit 0
}
trap cleanup INT TERM EXIT

# Make sure we are on the branch we intend to track.
if [ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]; then
  log "checking out $BRANCH"
  git checkout "$BRANCH"
fi

log "watching $REMOTE/$BRANCH every ${INTERVAL}s (Ctrl+C to stop)"
start_stack

while true; do
  sleep "$INTERVAL"

  if ! git fetch --quiet "$REMOTE" "$BRANCH" 2>/dev/null; then
    log "fetch failed; will retry"
    continue
  fi

  local_sha="$(git rev-parse HEAD)"
  remote_sha="$(git rev-parse "$REMOTE/$BRANCH")"
  [ "$local_sha" = "$remote_sha" ] && continue

  log "update detected: ${local_sha:0:7} -> ${remote_sha:0:7}"

  # Refuse to touch a dirty tree — never clobber uncommitted local work.
  if ! git diff --quiet || ! git diff --cached --quiet; then
    log "local changes present; skipping auto-update until the tree is clean"
    continue
  fi

  if git merge --ff-only "$REMOTE/$BRANCH"; then
    log "fast-forwarded; redeploying"
    stop_stack
    start_stack
    log "stack updated to ${remote_sha:0:7}"
  else
    log "cannot fast-forward (diverged); resolve manually, then the watcher resumes"
  fi
done
