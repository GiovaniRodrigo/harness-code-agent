"""Estado da execução + event log append-only.

Um agente pode fazer dezenas de ações. Guardar cada passo como um evento
permite auditar, reproduzir bugs e avaliar o agente depois.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class State:
    task: str
    event_log_path: Path
    step: int = 0
    # Histórico no formato aceito pela Messages API (role/content).
    messages: list[dict[str, Any]] = field(default_factory=list)

    def record(self, kind: str, **data: Any) -> None:
        """Anexa um evento ao log JSONL. Nunca reescreve — append-only."""
        event = {"ts": time.time(), "step": self.step, "kind": kind, **data}
        with self.event_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def add_user(self, content: Any) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: Any) -> None:
        self.messages.append({"role": "assistant", "content": content})
