"""Ponto de entrada CLI do harness.

Uso:
    python3 main.py "Crie fib.py com uma função fib(n) e um teste que passe."
    python3 main.py -f tarefa.md
    HARNESS_TEST_COMMAND="python3 -m pytest -q" python3 main.py "Faça os testes passarem."
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.config import Config
from harness.loop import run_agent


def main() -> int:
    parser = argparse.ArgumentParser(description="Coding-agent harness (MVP).")
    parser.add_argument("task", nargs="?", help="Descrição da tarefa.")
    parser.add_argument("-f", "--file", help="Ler a tarefa de um arquivo.")
    parser.add_argument("--workspace", help="Diretório de workspace (sobrescreve HARNESS_WORKSPACE).")
    parser.add_argument("--test-command", help="Comando de verificação do evaluator (ex.: 'pytest -q').")
    parser.add_argument("--model", help="Model ID (sobrescreve HARNESS_MODEL).")
    args = parser.parse_args()

    if args.file:
        task = Path(args.file).read_text(encoding="utf-8")
    elif args.task:
        task = args.task
    else:
        parser.error("forneça uma tarefa como argumento ou via -f/--file.")

    config = Config()
    if args.workspace:
        config.workspace = Path(args.workspace).resolve()
    if args.test_command is not None:
        config.test_command = args.test_command
    if args.model:
        config.model = args.model

    print(f"Modelo:    {config.model}")
    print(f"Workspace: {config.workspace}")
    print(f"Evaluator: {config.test_command or '(nenhum)'}")
    print("-" * 60)

    result = run_agent(task, config)

    print("-" * 60)
    print(f"{'✓ SUCESSO' if result.success else '✗ FALHA'} em {result.steps} passos")
    print()
    print(result.summary)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
