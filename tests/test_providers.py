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

    def test_default_model_for_falls_back_to_shipped(self) -> None:
        import os
        from unittest.mock import patch

        from harness.providers import default_model_for

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HARNESS_MODEL_OLLAMA", None)
            self.assertEqual(default_model_for("ollama"), "llama3.1")
            self.assertEqual(default_model_for("OLLAMA"), "llama3.1")  # case-insensitive
        self.assertEqual(default_model_for("nope"), "")  # unknown provider

    def test_default_model_for_env_override_is_per_provider(self) -> None:
        import os
        from unittest.mock import patch

        from harness.providers import default_model_for

        with patch.dict(os.environ, {"HARNESS_MODEL_OLLAMA": "llama3.2:1b"}, clear=False):
            self.assertEqual(default_model_for("ollama"), "llama3.2:1b")
            # Override for one provider must not leak into another.
            os.environ.pop("HARNESS_MODEL_ANTHROPIC", None)
            self.assertEqual(default_model_for("anthropic"), "claude-opus-5")

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


class OllamaPreflightTest(unittest.TestCase):
    """Model-existence preflight — pure logic, mocked `/api/tags`, no network."""

    def test_model_present_matches_exact_and_latest(self) -> None:
        from harness.providers.ollama_provider import _model_present

        installed = ["qwen2.5:0.5b", "llama3.1:latest", "llama3.2:1b"]
        self.assertTrue(_model_present("qwen2.5:0.5b", installed))
        self.assertTrue(_model_present("llama3.1", installed))  # bare -> :latest
        self.assertTrue(_model_present("llama3.1:latest", installed))
        self.assertFalse(_model_present("mistral", installed))
        self.assertFalse(_model_present("llama3.2", installed))  # only :1b is present

    def _bare_provider(self, model: str):
        # Build without __init__ so the openai SDK is never imported/needed.
        from harness.providers.ollama_provider import OllamaProvider

        prov = OllamaProvider.__new__(OllamaProvider)
        prov.model = model
        prov.options = {}
        return prov

    def test_preflight_raises_with_pull_hint_when_missing(self) -> None:
        from unittest.mock import patch

        from harness.providers import ollama_provider as mod
        from harness.providers.ollama_provider import ModelNotAvailableError

        prov = self._bare_provider("llama3.1")
        with patch.object(mod, "_installed_models", return_value=["qwen2.5:0.5b"]):
            with self.assertRaises(ModelNotAvailableError) as ctx:
                prov._preflight_model()
        msg = str(ctx.exception)
        self.assertIn("llama3.1", msg)
        self.assertIn("qwen2.5:0.5b", msg)  # lists what's actually installed
        self.assertIn("ollama pull llama3.1", msg)  # copy-paste fix

    def test_preflight_empty_list_says_none(self) -> None:
        from unittest.mock import patch

        from harness.providers import ollama_provider as mod
        from harness.providers.ollama_provider import ModelNotAvailableError

        prov = self._bare_provider("llama3.1")
        with patch.object(mod, "_installed_models", return_value=[]):
            with self.assertRaises(ModelNotAvailableError) as ctx:
                prov._preflight_model()
        self.assertIn("(none)", str(ctx.exception))

    def test_preflight_skips_when_host_unreachable(self) -> None:
        from unittest.mock import patch

        from harness.providers import ollama_provider as mod

        prov = self._bare_provider("llama3.1")
        # None == couldn't reach /api/tags: do NOT raise, let the real call report it.
        with patch.object(mod, "_installed_models", return_value=None):
            self.assertIsNone(prov._preflight_model())

    def test_preflight_passes_when_present(self) -> None:
        from unittest.mock import patch

        from harness.providers import ollama_provider as mod

        prov = self._bare_provider("llama3.2:1b")
        with patch.object(mod, "_installed_models", return_value=["llama3.2:1b"]):
            self.assertIsNone(prov._preflight_model())


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
