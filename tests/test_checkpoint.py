"""Integration tests for GitCheckpointer against a real temp repo."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from harness.checkpoint import GitCheckpointer


@unittest.skipIf(shutil.which("git") is None, "git not available")
class GitCheckpointerTest(unittest.TestCase):
    def test_commit_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            cp = GitCheckpointer(ws)
            cp.init()
            base = cp.commit("start")

            # A subtask writes a file; checkpoint it.
            (ws / "a.txt").write_text("hello", encoding="utf-8")
            after_a = cp.commit("subtask: A")
            self.assertNotEqual(base, after_a)
            self.assertTrue((ws / "a.txt").exists())

            # A later subtask makes a mess; roll back to after A.
            (ws / "b.txt").write_text("oops", encoding="utf-8")
            (ws / "a.txt").write_text("corrupted", encoding="utf-8")
            cp.rollback(after_a)

            self.assertFalse((ws / "b.txt").exists())  # untracked file cleaned
            self.assertEqual((ws / "a.txt").read_text(encoding="utf-8"), "hello")

    def test_init_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / "ws"
            cp = GitCheckpointer(ws)
            cp.init()
            cp.init()  # must not raise on an already-initialized repo
            self.assertTrue((ws / ".git").exists())


if __name__ == "__main__":
    unittest.main()
