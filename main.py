"""Harness CLI entry point.

Usage:
    python3 main.py "Create fib.py with a fib(n) function and a passing test."
    python3 main.py -f task.md
    python3 main.py --orchestrate "Build a small CLI todo app with tests."
    HARNESS_TEST_COMMAND="python3 -m pytest -q" python3 main.py "Make the tests pass."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.config import Config
from harness.loop import run_agent
from harness.providers import default_model_for


def main() -> int:
    parser = argparse.ArgumentParser(description="Coding-agent harness (MVP).")
    parser.add_argument("task", nargs="?", help="Task description.")
    parser.add_argument("-f", "--file", help="Read the task from a file.")
    parser.add_argument("--workspace", help="Workspace directory (overrides HARNESS_WORKSPACE).")
    parser.add_argument("--test-command", help="Evaluator verification command (e.g. 'pytest -q').")
    parser.add_argument("--provider", help="Provider (overrides HARNESS_PROVIDER): anthropic|openai|google|ollama.")
    parser.add_argument("--model", help="Model ID (overrides HARNESS_MODEL).")
    parser.add_argument(
        "--orchestrate",
        action="store_true",
        help="Decompose the task and run it with multiple sub-agents.",
    )
    args = parser.parse_args()

    if args.file:
        task = Path(args.file).read_text(encoding="utf-8")
    elif args.task:
        task = args.task
    else:
        parser.error("provide a task as an argument or via -f/--file.")

    config = Config()
    if args.provider:
        config.provider = args.provider.lower()
        # Switching provider on the CLI without an explicit --model re-picks that
        # provider's default, so a HARNESS_MODEL meant for another vendor isn't
        # sent to the wrong one. Pass --model to override.
        if not args.model:
            config.model = default_model_for(config.provider) or config.model
    if args.workspace:
        config.workspace = Path(args.workspace).resolve()
    if args.test_command is not None:
        config.test_command = args.test_command
    if args.model:
        config.model = args.model

    print(f"Provider:  {config.provider}")
    print(f"Model:     {config.model}")
    print(f"Workspace: {config.workspace}")
    print(f"Evaluator: {config.test_command or '(none)'}")
    print(f"Mode:      {'orchestrated' if args.orchestrate else 'single agent'}")
    print("-" * 60)

    if args.orchestrate:
        from harness.orchestrator import Orchestrator

        outcome = Orchestrator(config).run(task)
        success, summary, steps = outcome.success, outcome.summary, None
    else:
        result = run_agent(task, config)
        success, summary, steps = result.success, result.summary, result.steps

    print("-" * 60)
    tail = "" if steps is None else f" in {steps} steps"
    print(f"{'✓ SUCCESS' if success else '✗ FAILURE'}{tail}")
    print()
    print(summary)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
