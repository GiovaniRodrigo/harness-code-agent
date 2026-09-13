"""Test the .env loader helper (skipped if python-dotenv isn't installed)."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from harness.config import load_env

_HAS_DOTENV = importlib.util.find_spec("dotenv") is not None


@unittest.skipUnless(_HAS_DOTENV, "python-dotenv not installed")
class LoadEnvTest(unittest.TestCase):
    def test_loads_values_from_file(self) -> None:
        key = "HARNESS_TEST_ENV_VALUE"
        saved = os.environ.pop(key, None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env_path = Path(tmp) / ".env"
                env_path.write_text(f"{key}=from_dotenv\n", encoding="utf-8")
                self.assertTrue(load_env(str(env_path)))
                self.assertEqual(os.environ[key], "from_dotenv")
        finally:
            if saved is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved

    def test_missing_file_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # A path that doesn't exist must not raise.
            self.assertFalse(load_env(str(Path(tmp) / "nope.env")))


if __name__ == "__main__":
    unittest.main()
