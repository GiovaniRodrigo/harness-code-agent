# harness_ai — coding-agent harness (MVP)

Um harness mínimo, porém real, para um **agente de programação**. A ideia
central: o LLM não é o sistema — ele é um componente dentro de um sistema que
fornece **contexto, ferramentas, estado, limites e feedback verificável**.

```
Tarefa
  │
  ▼
┌──────────────────────── Harness ────────────────────────┐
│  context → LLM (loop) → policy → sandbox → tools         │
│                 │                                        │
│                 ▼                                        │
│            state / event log                             │
│                 │                                        │
│                 ▼                                        │
│            evaluator (roda os testes)                    │
│           pass ──► fim     |     fail ──► feedback ──► LLM│
└──────────────────────────────────────────────────────────┘
```

## Componentes

| Arquivo | Papel |
|---|---|
| `harness/loop.py` | O loop do agente — costura tudo. Loop **manual** (`while stop_reason == "tool_use"`), para deixar cada etapa visível. |
| `harness/llm.py` | Wrapper fino sobre a Messages API (modelo, thinking adaptativo, esforço). |
| `harness/tools/` | `Tool` base, `registry` e as ferramentas: `read_file`, `write_file`, `list_dir`, `run_command`. O modelo só age por aqui. |
| `harness/sandbox.py` | Confina caminhos e comandos ao workspace; timeout de comandos. |
| `harness/policies.py` | Guardrails: bloqueia comandos claramente perigosos antes de executar. |
| `harness/context.py` | System prompt (cacheável) e truncamento de saídas grandes. |
| `harness/state.py` | Histórico + **event log** append-only (JSONL) para auditoria/replay. |
| `harness/evaluator.py` | Fecha o loop: roda o comando de teste e devolve falhas ao agente. |
| `harness/config.py` | Configuração via ambiente, com defaults. |
| `main.py` | CLI. |

## Instalação

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # ou use `ant auth login`
```

## Uso

```bash
# Tarefa inline (sem verificação automática)
python main.py "Crie hello.py que imprime 'olá' e rode-o."

# Com evaluator: o agente só termina quando os testes passarem
python main.py -f example/task.md --test-command "python -m pytest -q"
```

Saída do agente (arquivos criados, etc.) fica em `./workspace/`. Cada passo é
registrado em `./harness_events.jsonl`.

## Configuração

Todas as variáveis são opcionais (veja `.env.example`):

- `HARNESS_MODEL` — default `claude-opus-5`. Troque para `claude-sonnet-5` para reduzir custo.
- `HARNESS_EFFORT` — `low` | `medium` | `high` | `xhigh` | `max`.
- `HARNESS_WORKSPACE` — diretório de trabalho do agente.
- `HARNESS_TEST_COMMAND` — comando do evaluator (ex.: `pytest -q`).
- `HARNESS_MAX_STEPS`, `HARNESS_MAX_EVAL_RETRIES`, `HARNESS_CMD_TIMEOUT`, `HARNESS_MAX_TOOL_OUTPUT`.

## Segurança (leia antes de usar de verdade)

O `sandbox.py` confina caminhos e o `policies.py` bloqueia acidentes óbvios,
mas **não é isolamento forte**. `run_command` executa shell de verdade. Para
tarefas não confiáveis, rode o harness inteiro dentro de um container ou VM
descartável e restrinja a rede.

## Próximos passos (para evoluir do MVP)

- **Streaming** de respostas e `task_budget` para tarefas longas.
- **Compaction** / context editing quando o histórico crescer.
- **Human-in-the-loop**: confirmar ações irreversíveis em vez de só bloquear.
- **Checkpoints**: retomar execução a partir do event log.
- Sandbox real (container por sessão) e limites de CPU/memória/rede.
