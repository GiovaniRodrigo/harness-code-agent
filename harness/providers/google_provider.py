"""Google Gemini backend (google-genai SDK + function calling).

Note: written against the `google-genai` SDK (`pip install google-genai`,
`from google import genai`), not the older `google-generativeai` package. The
SDK is not installed in this repo by default, so this provider is not exercised
by the smoke tests; verify against your installed SDK version before relying on
it. Gemini matches function responses by NAME (not by a call id), so parallel
calls to the same tool in one turn can be ambiguous.
"""

from __future__ import annotations

from typing import Any

from harness.providers.base import (
    LLMResponse,
    Provider,
    ToolCall,
    ToolOutput,
    ToolSpec,
)


class GoogleProvider(Provider):
    name = "google"

    def __init__(
        self,
        model: str,
        system: str,
        tools: list[ToolSpec],
        max_tokens: int = 16000,
        **options: Any,
    ) -> None:
        super().__init__(model, system, tools, max_tokens, **options)
        from google import genai  # lazy: only needed when this provider is selected
        from google.genai import types

        self._genai = genai
        self._types = types
        self.client = genai.Client()

        declarations = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters=t.input_schema
            )
            for t in tools
        ]
        self._config = types.GenerateContentConfig(
            system_instruction=system or None,
            tools=[types.Tool(function_declarations=declarations)] if declarations else None,
            max_output_tokens=max_tokens,
        )
        self._contents: list[Any] = []

    def _generate(self) -> LLMResponse:
        response = self.client.models.generate_content(
            model=self.model, contents=self._contents, config=self._config
        )
        candidate = response.candidates[0]
        # Preserve the model's turn in history.
        self._contents.append(candidate.content)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for part in candidate.content.parts or []:
            if getattr(part, "function_call", None):
                fc = part.function_call
                # Gemini has no per-call id; use the function name as the handle.
                tool_calls.append(ToolCall(id=fc.name, name=fc.name, input=dict(fc.args or {})))
            elif getattr(part, "text", None):
                text_parts.append(part.text)

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            done=not tool_calls,
        )

    def send_user(self, text: str) -> LLMResponse:
        types = self._types
        self._contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        return self._generate()

    def send_tool_results(self, results: list[ToolOutput]) -> LLMResponse:
        types = self._types
        parts = [
            types.Part.from_function_response(name=r.name, response={"result": r.content})
            for r in results
        ]
        self._contents.append(types.Content(role="user", parts=parts))
        return self._generate()
