"""O loop do agente — o coração do harness.

Costura todos os componentes: context -> LLM -> (policy -> sandbox -> tools)
-> state/event log -> evaluator. É um loop manual (não o tool runner do SDK)
justamente porque o objetivo aqui é ver e controlar cada etapa.
"""

from __future__ import annotations

from dataclasses import dataclass

from harness.config import Config
from harness.context import build_system, truncate_output
from harness.evaluator import Evaluator
from harness.llm import LLM
from harness.policies import PolicyEngine
from harness.sandbox import Sandbox
from harness.state import State
from harness.tools.registry import ToolRegistry, default_registry


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
    registry: ToolRegistry = default_registry()
    policy = PolicyEngine()
    evaluator = Evaluator(config.test_command)
    llm = LLM(config)

    state = State(task=task, event_log_path=config.event_log)
    state.record("task_created", task=task, model=config.model, workspace=str(config.workspace))
    state.add_user(task)

    system = build_system(config)
    tools = registry.schemas()
    eval_retries = 0
    final_text = ""

    while state.step < config.max_steps:
        state.step += 1

        # 1) Uma iteração de raciocínio do modelo.
        response = llm.generate(system=system, messages=state.messages, tools=tools)
        state.record("model_called", stop_reason=response.stop_reason)

        # Preserva a resposta inteira no histórico (inclui blocos de thinking,
        # que precisam voltar ao modelo na mesma sessão/modelo).
        state.add_assistant(response.content)

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if text_blocks:
            final_text = "\n".join(text_blocks)

        # Servidor pausou um tool server-side: basta reenviar para continuar.
        if response.stop_reason == "pause_turn":
            continue

        # 2) O modelo parou de chamar ferramentas => candidato a finalizar.
        if response.stop_reason == "end_turn":
            evaluation = evaluator.check(sandbox)
            if evaluation.success:
                state.record("task_completed", summary=final_text)
                _log("tarefa concluída." + ("" if not evaluator.enabled else " testes verdes."))
                return AgentResult(success=True, summary=final_text, steps=state.step)

            eval_retries += 1
            state.record("evaluation_failed", retry=eval_retries)
            if eval_retries > config.max_eval_retries:
                state.record("evaluation_gave_up", retries=eval_retries)
                _log("evaluator reprovou após o limite de tentativas.")
                return AgentResult(success=False, summary=final_text, steps=state.step)

            _log(f"evaluator reprovou (tentativa {eval_retries}); devolvendo ao agente.")
            state.add_user(evaluation.feedback)
            continue

        # 3) stop_reason == "tool_use": executa cada chamada.
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        tool_results = []
        for block in tool_uses:
            decision = policy.check(block.name, block.input)
            if not decision.allowed:
                state.record("tool_rejected", tool=block.name, reason=decision.reason)
                _log(f"policy bloqueou {block.name}: {decision.reason}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": decision.reason,
                        "is_error": True,
                    }
                )
                continue

            _log(f"→ {block.name}({_preview(block.input)})")
            result = registry.execute(block.name, block.input, sandbox)
            content = truncate_output(result.content, config.max_tool_output)
            state.record(
                "tool_executed",
                tool=block.name,
                args=block.input,
                is_error=result.is_error,
                output_bytes=len(result.content),
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                    "is_error": result.is_error,
                }
            )

        state.add_user(tool_results)

    # Estourou o teto de passos.
    state.record("max_steps_reached", steps=state.step)
    _log("limite de passos atingido.")
    return AgentResult(success=False, summary=final_text, steps=state.step)


def _preview(args: dict, limit: int = 80) -> str:
    text = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return text if len(text) <= limit else text[:limit] + "…"
