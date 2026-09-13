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


def _server_models() -> list[dict] | None:
    """Return the daemon's model records, or ``None`` if it's unreachable."""
    try:
        with urllib.request.urlopen(f"{_api_root()}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return [m for m in data.get("models", []) if m.get("name")]


def _is_embedding(model: dict) -> bool:
    """Best-effort guess: does this model only produce embeddings (no chat)?

    ``/api/tags`` has no explicit capability flag, so we go by the strongest
    signals available — an ``embed`` in the name or a BERT-family lineage.
    """
    name = model.get("name", "").lower()
    details = model.get("details") or {}
    families = [str(f).lower() for f in (details.get("families") or [])]
    families.append(str(details.get("family") or "").lower())
    if "embed" in name:
        return True
    return any("bert" in fam for fam in families)


def _pick_model(models: list[dict]) -> str | None:
    """Prefer OLLAMA_TEST_MODEL; else the first non-embedding model available.

    Skipping known embedding models avoids auto-selecting a model that cannot
    serve chat completions when a usable one is also installed.
    """
    names = [m["name"] for m in models]
    wanted = os.getenv("OLLAMA_TEST_MODEL")
    if wanted:
        # Accept both "qwen2.5:0.5b" and a bare "qwen2.5" (matches any tag).
        for name in names:
            if name == wanted or name.split(":", 1)[0] == wanted.split(":", 1)[0]:
                return name
        return wanted  # trust the caller; the chat preflight below verifies it
    for model in models:
        if not _is_embedding(model):
            return model["name"]
    return names[0] if names else None


def _chat_usable(model: str) -> tuple[bool, str]:
    """Probe the OpenAI-compatible endpoint with a 1-token chat completion.

    This turns "model missing / not a chat model / server error" into a clean
    skip precondition instead of a mid-test failure, so the CI-safe promise
    holds even when the picked model can't actually chat.
    """
    body = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
    ).encode()
    req = urllib.request.Request(
        f"{_api_root()}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        detail = getattr(exc, "reason", exc)
        return False, str(detail)
    return True, ""


def _require_ollama() -> str:
    """Skip the whole test unless a live server has a CHAT-usable model."""
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
    usable, err = _chat_usable(model)
    if not usable:
        raise unittest.SkipTest(f"model {model!r} is not usable for chat: {err}")
    return model


class OllamaIntegrationTest(unittest.TestCase):
    """End-to-end exercises against a running Ollama daemon."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.model = _require_ollama()

    # NOTE: these assert the *provider's* behavior (a real round trip, history
    # threading, tool-call plumbing), NOT the model's knowledge or reasoning.
    # The configured model may be tiny and can answer "mars" to a planet
    # question; grading its intelligence would make the suite flaky, so we only
    # check the contract the harness relies on.

    def test_chat_completion_end_to_end(self) -> None:
        """A plain prompt makes a real round trip and returns a clean text turn."""
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

    def test_multi_turn_keeps_history(self) -> None:
        """Two turns in one session are threaded into a single growing history.

        This proves the integration concern — the provider preserves and extends
        the conversation across ``send_user`` calls — deterministically, without
        depending on a small model actually *recalling* anything.
        """
        prov = build_provider(
            "ollama",
            self.model,
            system="You are a terse assistant.",
            tools=[],
            max_tokens=32,
        )
        first = prov.send_user("Say: one")
        self.assertTrue(first.done)
        self.assertTrue(first.text.strip(), "expected non-empty text on the first turn")

        second = prov.send_user("Say: two")
        self.assertTrue(second.done)
        self.assertTrue(second.text.strip(), "expected non-empty text on the second turn")

        # The OpenAI-compatible backend threads the whole exchange into its
        # history: system + user1 + assistant1 + user2 + assistant2.
        roles = [m["role"] for m in prov._messages]
        self.assertEqual(roles, ["system", "user", "assistant", "user", "assistant"])
        self.assertEqual(prov._messages[1]["content"], "Say: one")
        self.assertEqual(prov._messages[3]["content"], "Say: two")

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

        # Feeding the tool result back must be accepted and produce a further
        # assistant turn. We assert the plumbing (history threading), not that a
        # tiny model then echoes the number back verbatim.
        final = prov.send_tool_results(
            [ToolOutput(tool_call_id=call.id, name=call.name, content="5")]
        )
        self.assertIsInstance(final.done, bool)
        roles = [m["role"] for m in prov._messages]
        self.assertIn("tool", roles, "the tool result must be threaded into history")
        self.assertEqual(roles[-1], "assistant", "a further assistant turn must follow the tool result")


if __name__ == "__main__":
    unittest.main()
