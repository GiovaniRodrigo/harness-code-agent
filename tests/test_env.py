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


class ConfigModelResolutionTest(unittest.TestCase):
    """Config fills the model from HARNESS_MODEL_<PROVIDER> before the shipped default."""

    def test_per_provider_override_fills_empty_model(self) -> None:
        from unittest.mock import patch

        from harness.config import Config

        env = {"HARNESS_PROVIDER": "ollama", "HARNESS_MODEL": "", "HARNESS_MODEL_OLLAMA": "llama3.2:1b"}
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(Config().model, "llama3.2:1b")

    def test_shipped_default_when_no_override(self) -> None:
        from unittest.mock import patch

        from harness.config import Config

        with patch.dict(os.environ, {"HARNESS_PROVIDER": "ollama", "HARNESS_MODEL": ""}, clear=False):
            os.environ.pop("HARNESS_MODEL_OLLAMA", None)
            self.assertEqual(Config().model, "llama3.1")

    def test_explicit_global_model_wins_over_override(self) -> None:
        from unittest.mock import patch

        from harness.config import Config

        env = {
            "HARNESS_PROVIDER": "ollama",
            "HARNESS_MODEL": "explicit-model",
            "HARNESS_MODEL_OLLAMA": "llama3.2:1b",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertEqual(Config().model, "explicit-model")


if __name__ == "__main__":
    unittest.main()
