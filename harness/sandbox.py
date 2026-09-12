"""Sandbox: confina toda a atividade do agente ao diretório de workspace.

Não é isolamento de nível de container — é a primeira linha de defesa em
processo. Para uso real com risco elevado, rode o harness inteiro dentro de
um container/VM descartável. Aqui garantimos que caminhos e comandos não
escapem do workspace por acidente.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class SandboxError(Exception):
    """Violação de fronteira do sandbox (path traversal, workspace, etc.)."""


class Sandbox:
    def __init__(self, workspace: Path, command_timeout: int = 120) -> None:
        self.workspace = workspace.resolve()
        self.command_timeout = command_timeout
        self.workspace.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative_path: str) -> Path:
        """Resolve um caminho relativo ao workspace e recusa qualquer escape.

        Bloqueia path traversal (../), caminhos absolutos e symlinks que
        apontem para fora do workspace.
        """
        candidate = (self.workspace / relative_path).resolve()
        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise SandboxError(
                f"Caminho '{relative_path}' escapa do workspace {self.workspace}"
            )
        return candidate

    def run(self, command: str) -> dict:
        """Executa um comando de shell com cwd=workspace e timeout.

        Retorna exit_code, stdout, stderr. Não levanta em falha de comando —
        o exit_code diferente de zero é informação útil para o agente.
        """
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )
            return {
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "exit_code": 124,
                "stdout": "",
                "stderr": f"Comando excedeu o timeout de {self.command_timeout}s e foi encerrado.",
            }
