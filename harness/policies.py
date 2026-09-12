"""Policies / guardrails.

Antes de executar qualquer tool_use, o harness consulta a policy. Aqui
implementamos um denylist simples para comandos de shell claramente
destrutivos ou que escapam do sandbox. Em produção, evolua para confirmação
humana (human-in-the-loop) nas ações irreversíveis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Padrões bloqueados em run_command. Não é uma sandbox de segurança completa —
# é uma rede de proteção contra acidentes óbvios.
_BLOCKED_PATTERNS = [
    r"\brm\s+-rf\s+/(?:\s|$)",   # rm -rf / (raiz)
    r"\brm\s+-rf\s+~",           # rm -rf no home
    r":\(\)\s*\{.*\};:",         # fork bomb
    r"\bsudo\b",                  # escalonamento de privilégio
    r"\bshutdown\b|\breboot\b",
    r"\bmkfs\b|\bdd\s+if=",      # formatação / escrita em disco cru
    r">\s*/dev/sd",               # escrita direta em dispositivo
    r"\bcurl\b.*\|\s*(sh|bash)",  # pipe de rede para shell
    r"\bwget\b.*\|\s*(sh|bash)",
]


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


class PolicyEngine:
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        if tool_name == "run_command":
            command = str(args.get("command", ""))
            for pattern in _BLOCKED_PATTERNS:
                if re.search(pattern, command):
                    return Decision(
                        allowed=False,
                        reason=(
                            f"Comando bloqueado pela policy (padrão perigoso: /{pattern}/). "
                            "Ajuste a abordagem sem esse comando."
                        ),
                    )
        return Decision(allowed=True)
