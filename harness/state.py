"""Run state + an append-only event log.

An agent may take dozens of actions. Storing each step as an event lets you
audit, reproduce bugs, and evaluate the agent afterwards. The conversation
history itself lives inside the active Provider, so State is event-log-only.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class State:
    task: str
    event_log_path: Path
    step: int = 0

    def record(self, kind: str, **data: Any) -> None:
        """Append an event to the JSONL log. Never rewrites — append-only."""
        event = {"ts": time.time(), "step": self.step, "kind": kind, **data}
        with self.event_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
