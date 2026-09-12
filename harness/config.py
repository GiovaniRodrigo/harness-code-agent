"""Configuração do harness, lida do ambiente com defaults sensatos."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Modelo. Default: o mais capaz. Troque com HARNESS_MODEL=claude-sonnet-5 etc.
    model: str = field(default_factory=lambda: os.getenv("HARNESS_MODEL", "claude-opus-5"))

    # Esforço de raciocínio: low | medium | high | xhigh | max.
    effort: str = field(default_factory=lambda: os.getenv("HARNESS_EFFORT", "high"))

    # Teto de tokens por resposta do modelo.
    max_tokens: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_TOKENS", "16000")))

    # Diretório de trabalho do agente. TUDO acontece confinado aqui (sandbox).
    workspace: Path = field(
        default_factory=lambda: Path(os.getenv("HARNESS_WORKSPACE", "./workspace")).resolve()
    )

    # Limites do loop do agente.
    max_steps: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_STEPS", "40")))

    # Comando executado pelo evaluator para verificar o trabalho (ex.: "pytest -q").
    # Vazio => sem verificação automática; o agente termina no primeiro end_turn.
    test_command: str = field(default_factory=lambda: os.getenv("HARNESS_TEST_COMMAND", ""))

    # Quantas vezes, no máximo, devolvemos falha de teste ao agente para ele corrigir.
    max_eval_retries: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_EVAL_RETRIES", "3")))

    # Timeout (segundos) para comandos de shell no sandbox.
    command_timeout: int = field(default_factory=lambda: int(os.getenv("HARNESS_CMD_TIMEOUT", "120")))

    # Tamanho máximo (bytes) de saída de ferramenta devolvida ao modelo, para não estourar o contexto.
    max_tool_output: int = field(default_factory=lambda: int(os.getenv("HARNESS_MAX_TOOL_OUTPUT", "16000")))

    # Caminho do event log (JSONL). Permite auditoria e replay.
    event_log: Path = field(
        default_factory=lambda: Path(os.getenv("HARNESS_EVENT_LOG", "./harness_events.jsonl"))
    )

    def ensure_dirs(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
