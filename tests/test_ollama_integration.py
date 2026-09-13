"""Integration tests for the Ollama backend against a REAL running server.

Unlike ``tests/test_providers.py`` (pure unit tests, no network), these drive
``build_provider("ollama", ...)`` end to end: a live Ollama daemon, the
OpenAI-compatible ``/v1`` endpoint, and a real local model doing inference.

They are written to be safe in CI and on machines without Ollama: each test
**skips** (never fails) when a precondition is missing —

  * the ``openai`` SDK isn't installed,
  * no Ollama server answers on the configured host, or
  * the server has no model to run.

Configuration (all optional):
  * ``OLLAMA_HOST`` / ``OLLAMA_BASE_URL`` — where the daemon lives
    (default ``http://localhost:11434``).
  * ``OLLAMA_TEST_MODEL`` — model to use; otherwise the first model the server
    reports via ``/api/tags`` is chosen.

Run just these:  ``.venv/bin/python -m unittest tests.test_ollama_integration``
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.error
import urllib.request

from harness.providers import ToolSpec, build_provider
from harness.providers.ollama_provider import DEFAULT_OLLAMA_BASE_URL, _normalize_base_url


def _api_root() -> str:
    """Base Ollama URL WITHOUT the ``/v1`` suffix (for the native ``/api/*``)."""
    raw = os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or DEFAULT_OLLAMA_BASE_URL
    v1 = _normalize_base_url(raw)  # e.g. http://localhost:11434/v1
    return v1[: -len("/v1")] if v1.endswith("/v1") else v1


def _server_models() -> list[str] | None:
    """Return model names the daemon reports, or ``None`` if it's unreachable."""
    try:
        with urllib.request.urlopen(f"{_api_root()}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return [m["name"] for m in data.get("models", []) if m.get("name")]


def _pick_model(available: list[str]) -> str | None:
    """Prefer OLLAMA_TEST_MODEL; else the first model the server has."""
    wanted = os.getenv("OLLAMA_TEST_MODEL")
    if wanted:
        # Accept both "qwen2.5:0.5b" and a bare "qwen2.5" (matches any tag).
        for name in available:
            if name == wanted or name.split(":", 1)[0] == wanted.split(":", 1)[0]:
                return name
        return wanted  # trust the caller even if /api/tags didn't list it
    return available[0] if available else None


def _require_ollama() -> str:
    """Skip the whole test unless a live server WITH a model is available."""
    try:
        import openai  # noqa: F401
    except ModuleNotFoundError:
        raise unittest.SkipTest("openai SDK not installed (pip install openai)")

    models = _server_models()
    if models is None:
        raise unittest.SkipTest(f"no Ollama server reachable at {_api_root()}")
    model = _pick_model(models)
    if not model:
        raise unittest.SkipTest("Ollama server has no models (try: ollama pull qwen2.5:0.5b)")
    return model


class OllamaIntegrationTest(unittest.TestCase):
    """End-to-end exercises against a running Ollama daemon."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.model = _require_ollama()

    def test_chat_completion_end_to_end(self) -> None:
        """A plain prompt returns assistant text and a clean `done` turn."""
        prov = build_provider(
            "ollama",
            self.model,
            system="You are a terse assistant. Answer in one short sentence.",
            tools=[],
            max_tokens=64,
        )
        resp = prov.send_user("Name the largest planet in our solar system.")

        self.assertTrue(resp.text.strip(), "expected non-empty assistant text")
        self.assertEqual(resp.tool_calls, [], "no tools were offered, so none should be called")
        self.assertTrue(resp.done, "a pure-text turn must report done=True")
        self.assertIn("jupiter", resp.text.lower())

    def test_multi_turn_keeps_history(self) -> None:
        """A follow-up question resolves against earlier turns in the session."""
        prov = build_provider(
            "ollama",
            self.model,
            system="You are a precise assistant. Reply with digits only when asked for a number.",
            tools=[],
            max_tokens=32,
        )
        first = prov.send_user("Remember the number 42. Reply with just: OK")
        self.assertTrue(first.done)

        second = prov.send_user("What number did I ask you to remember? Reply with the digits only.")
        self.assertTrue(second.done)
        self.assertIn("42", second.text)

    def test_tool_call_roundtrip(self) -> None:
        """When the model calls a tool, feeding the result back must work.

        Small local models are unreliable tool callers, so if the model answers
        directly instead of calling the tool we skip rather than fail — the goal
        here is to prove the tool-call plumbing (`send_tool_results`) works, not
        to grade the model's judgment.
        """
        add_tool = ToolSpec(
            name="add",
            description="Add two integers and return their sum.",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "first addend"},
                    "b": {"type": "integer", "description": "second addend"},
                },
                "required": ["a", "b"],
            },
        )
        prov = build_provider(
            "ollama",
            self.model,
            system="You are a calculator. Use the `add` tool for any addition.",
            tools=[add_tool],
            max_tokens=128,
        )
        resp = prov.send_user("Use the add tool to compute 2 + 3.")

        if not resp.tool_calls:
            self.skipTest(f"model {self.model!r} did not emit a tool call")

        from harness.providers import ToolOutput

        call = resp.tool_calls[0]
        self.assertEqual(call.name, "add")
        self.assertIsInstance(call.input, dict)

        final = prov.send_tool_results(
            [ToolOutput(tool_call_id=call.id, name=call.name, content="5")]
        )
        self.assertTrue(final.text.strip(), "expected a final assistant answer after the tool result")
        self.assertIn("5", final.text)


if __name__ == "__main__":
    unittest.main()
