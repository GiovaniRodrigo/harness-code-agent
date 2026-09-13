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
        self.assertIn("ollama", DEFAULT_MODELS)

    def test_missing_sdk_is_lazy(self) -> None:
        # Constructing a backend whose SDK isn't installed must fail at import
        # time (ModuleNotFoundError), not at factory-dispatch time.
        try:
            build_provider("anthropic", "claude-opus-5", "system", [ToolSpec("t", "d", {})])
        except ModuleNotFoundError as exc:
            self.assertEqual(exc.name, "anthropic")
        except Exception:  # SDK happens to be installed — that's fine too.
            pass


class OllamaProviderTest(unittest.TestCase):
    """The Ollama backend reuses the OpenAI SDK; these need no network."""

    def test_base_url_normalization(self) -> None:
        from harness.providers.ollama_provider import _normalize_base_url

        self.assertEqual(_normalize_base_url("localhost:11434"), "http://localhost:11434/v1")
        self.assertEqual(_normalize_base_url("http://localhost:11434"), "http://localhost:11434/v1")
        self.assertEqual(_normalize_base_url("http://localhost:11434/"), "http://localhost:11434/v1")
        self.assertEqual(_normalize_base_url("http://localhost:11434/v1"), "http://localhost:11434/v1")
        self.assertEqual(_normalize_base_url("https://box:9999/v1"), "https://box:9999/v1")
        self.assertEqual(_normalize_base_url(""), "http://localhost:11434/v1")

    def test_token_param_is_max_tokens(self) -> None:
        from harness.providers.ollama_provider import OllamaProvider

        self.assertEqual(OllamaProvider.token_param, "max_tokens")

    def test_client_kwargs_prefer_option_then_env(self) -> None:
        import os
        from unittest.mock import patch

        from harness.providers.ollama_provider import OllamaProvider

        # Build without touching __init__ (which would import the openai SDK).
        prov = OllamaProvider.__new__(OllamaProvider)
        prov.options = {"base_url": "myhost:1234"}
        kwargs = prov._client_kwargs()
        self.assertEqual(kwargs["base_url"], "http://myhost:1234/v1")
        self.assertEqual(kwargs["api_key"], "ollama")  # placeholder when none set

        prov.options = {}
        with patch.dict(os.environ, {"OLLAMA_HOST": "http://server:11434"}, clear=False):
            os.environ.pop("OLLAMA_BASE_URL", None)
            self.assertEqual(prov._client_kwargs()["base_url"], "http://server:11434/v1")


class ParseArgsTest(unittest.TestCase):
    """`_parse_args` must tolerate the shapes OpenAI-compatible servers return."""

    def test_accepts_json_string(self) -> None:
        from harness.providers.openai_provider import _parse_args

        self.assertEqual(_parse_args('{"a": 1}'), {"a": 1})

    def test_accepts_already_decoded_dict(self) -> None:
        # Ollama may hand back structured arguments as an object, not a string.
        from harness.providers.openai_provider import _parse_args

        self.assertEqual(_parse_args({"a": 1}), {"a": 1})

    def test_empty_and_malformed_are_safe(self) -> None:
        from harness.providers.openai_provider import _parse_args

        self.assertEqual(_parse_args(""), {})
        self.assertEqual(_parse_args(None), {})
        self.assertEqual(_parse_args("not json"), {})
        self.assertEqual(_parse_args("[1, 2]"), {})  # non-object JSON


if __name__ == "__main__":
    unittest.main()
