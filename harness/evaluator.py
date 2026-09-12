"""Evaluator: fecha o loop com feedback verificável.

O agente dizer "terminei" não basta — o harness verifica. Se um comando de
teste estiver configurado, rodamos no sandbox. Testes passando => sucesso.
Testes falhando => devolvemos a saída ao agente para ele corrigir.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.sandbox import Sandbox


@dataclass
class Evaluation:
    success: bool
    feedback: str


class Evaluator:
    def __init__(self, test_command: str) -> None:
        self.test_command = test_command.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.test_command)

    def check(self, sandbox: Sandbox) -> Evaluation:
        """Roda o comando de teste. Sem comando configurado => aprova direto."""
        if not self.enabled:
            return Evaluation(success=True, feedback="")

        result = sandbox.run(self.test_command)
        if result["exit_code"] == 0:
            return Evaluation(success=True, feedback="")

        feedback = (
            f"O evaluator rodou `{self.test_command}` e falhou "
            f"(exit_code={result['exit_code']}). Corrija e não finalize até passar.\n"
        )
        if result["stdout"]:
            feedback += f"\n--- stdout ---\n{result['stdout']}"
        if result["stderr"]:
            feedback += f"\n--- stderr ---\n{result['stderr']}"
        return Evaluation(success=False, feedback=feedback)
