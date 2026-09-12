"""The agent loop — the heart of the harness.

It stitches all the components together: context -> provider (LLM) -> (policy ->
sandbox -> tools) -> state/event log -> evaluator. The loop is vendor-neutral:
it talks to any backend through the `Provider` interface, so switching between
Anthropic, OpenAI and Google is just a config change.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.config import Config
from harness.context import system_prompt, truncate_output
from harness.evaluator import Evaluator
from harness.policies import PolicyEngine
from harness.providers import ToolOutput, ToolSpec, build_provider
from harness.sandbox import Sandbox
from harness.state import State
from harness.tools.registry import default_registry


@dataclass
class AgentResult:
    success: bool
    summary: str
    steps: int


def _log(msg: str) -> None:
    print(f"\033[2m[harness]\033[0m {msg}", flush=True)


def run_agent(task: str, config: Config | None = None) -> AgentResult:
    config = config or Config()
    config.ensure_dirs()

    sandbox = Sandbox(config.workspace, config.command_timeout)
    registry = default_registry()
    policy = PolicyEngine()
    evaluator = Evaluator(config.test_command)

    # Convert the registry's tool definitions into vendor-neutral specs.
    tool_specs = [
        ToolSpec(s["name"], s["description"], s["input_schema"]) for s in registry.schemas()
    ]
    # `effort` is Anthropic-specific; other providers absorb unknown options
    # via **options, so the loop stays free of per-provider branching.
    provider = build_provider(
        config.provider,
        config.model,
        system_prompt(config),
        tool_specs,
        max_tokens=config.max_tokens,
        effort=config.effort,
    )

    state = State(task=task, event_log_path=config.event_log)
    state.record(
        "task_created",
        task=task,
        provider=config.provider,
        model=config.model,
        workspace=str(config.workspace),
    )

    response = provider.send_user(task)
    eval_retries = 0
    final_text = ""

    while state.step < config.max_steps:
        state.step += 1
        state.record("model_called", done=response.done, tool_calls=len(response.tool_calls))
        if response.text:
            final_text = response.text

        # 1) The model stopped calling tools => candidate to finish.
        if response.done:
            evaluation = evaluator.check(sandbox)
            if evaluation.success:
                state.record("task_completed", summary=final_text)
                _log("task complete." + ("" if not evaluator.enabled else " tests green."))
                return AgentResult(success=True, summary=final_text, steps=state.step)

            eval_retries += 1
            state.record("evaluation_failed", retry=eval_retries)
            if eval_retries > config.max_eval_retries:
                state.record("evaluation_gave_up", retries=eval_retries)
                _log("evaluator rejected after the retry limit.")
                return AgentResult(success=False, summary=final_text, steps=state.step)

            _log(f"evaluator rejected (attempt {eval_retries}); handing back to the agent.")
            response = provider.send_user(evaluation.feedback)
            continue

        # Not done, but nothing to execute: the model stopped for another
        # reason (e.g. max_tokens or refusal). Terminate instead of sending an
        # empty tool-results turn, which the provider APIs reject.
        if not response.tool_calls:
            state.record("stopped_without_tools", steps=state.step)
            _log("model stopped without finishing or calling tools.")
            return AgentResult(success=False, summary=final_text, steps=state.step)

        # 2) Execute each requested tool call, subject to the policies.
        outputs: list[ToolOutput] = []
        for call in response.tool_calls:
            decision = policy.check(call.name, call.input)
            if not decision.allowed:
                state.record("tool_rejected", tool=call.name, reason=decision.reason)
                _log(f"policy blocked {call.name}: {decision.reason}")
                outputs.append(ToolOutput(call.id, call.name, decision.reason, is_error=True))
                continue

            _log(f"→ {call.name}({_preview(call.input)})")
            result = registry.execute(call.name, call.input, sandbox)
            content = truncate_output(result.content, config.max_tool_output)
            state.record(
                "tool_executed",
                tool=call.name,
                args=call.input,
                is_error=result.is_error,
                output_bytes=len(result.content),
            )
            outputs.append(ToolOutput(call.id, call.name, content, is_error=result.is_error))

        response = provider.send_tool_results(outputs)

    # Hit the step ceiling.
    state.record("max_steps_reached", steps=state.step)
    _log("step limit reached.")
    return AgentResult(success=False, summary=final_text, steps=state.step)


def _preview(args: dict, limit: int = 80) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= limit else text[:limit] + "…"
