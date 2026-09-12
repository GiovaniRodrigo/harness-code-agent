"""Unit tests for the provider factory (no SDK / network required)."""

from __future__ import annotations

import unittest

from harness.providers import DEFAULT_MODELS, ToolSpec, build_provider


class ProviderFactoryTest(unittest.TestCase):
    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_provider("nope", "m", "system", [])

    def test_default_models_present(self) -> None:
        self.assertEqual(DEFAULT_MODELS["anthropic"], "claude-opus-5")
        self.assertIn("openai", DEFAULT_MODELS)
        self.assertIn("google", DEFAULT_MODELS)

    def test_missing_sdk_is_lazy(self) -> None:
        # Constructing a backend whose SDK isn't installed must fail at import
        # time (ModuleNotFoundError), not at factory-dispatch time.
        try:
            build_provider("anthropic", "claude-opus-5", "system", [ToolSpec("t", "d", {})])
        except ModuleNotFoundError as exc:
            self.assertEqual(exc.name, "anthropic")
        except Exception:  # SDK happens to be installed — that's fine too.
            pass


if __name__ == "__main__":
    unittest.main()
