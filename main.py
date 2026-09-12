"""Harness CLI entry point.

Usage:
    python3 main.py "Create fib.py with a fib(n) function and a passing test."
    python3 main.py -f task.md
    HARNESS_TEST_COMMAND="python3 -m pytest -q" python3 main.py "Make the tests pass."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.config import Config
from harness.loop import run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Coding-agent harness (MVP).")
    parser.add_argument("task", nargs="?", help="Task description.")
    parser.add_argument("-f", "--file", help="Read the task from a file.")
    parser.add_argument("--workspace", help="Workspace directory (overrides HARNESS_WORKSPACE).")
    parser.add_argument("--test-command", help="Evaluator verification command (e.g. 'pytest -q').")
    parser.add_argument("--model", help="Model ID (overrides HARNESS_MODEL).")
    args = parser.parse_args()

    if args.file:
        task = Path(args.file).read_text(encoding="utf-8")
    elif args.task:
        task = args.task
    else:
        parser.error("provide a task as an argument or via -f/--file.")

    config = Config()
    if args.workspace:
        config.workspace = Path(args.workspace).resolve()
    if args.test_command is not None:
        config.test_command = args.test_command
    if args.model:
        config.model = args.model

    print(f"Model:     {config.model}")
    print(f"Workspace: {config.workspace}")
    print(f"Evaluator: {config.test_command or '(none)'}")
    print("-" * 60)

    result = run_agent(task, config)

    print("-" * 60)
    print(f"{'✓ SUCCESS' if result.success else '✗ FAILURE'} in {result.steps} steps")
    print()
    print(result.summary)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
