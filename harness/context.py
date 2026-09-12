"""Context manager: monta o system prompt e trunca saídas de ferramenta.

Um harness bom controla o que entra no contexto a cada iteração. Aqui o
essencial: um system prompt estável (bom para cache) e truncamento de
saídas grandes de ferramenta para não estourar o orçamento de tokens.
"""

from __future__ import annotations

from harness.config import Config

SYSTEM_TEMPLATE = """\
Você é um agente de programação autônomo rodando dentro de um harness.

Ambiente:
- Você trabalha confinado a um workspace. Todos os caminhos são relativos a ele.
- Você age SOMENTE através das ferramentas disponíveis (read_file, write_file,
  list_dir, run_command). Não há outra forma de tocar o sistema.
- Comandos de shell rodam no workspace, com timeout, e passam por policies de
  segurança que podem bloquear ações perigosas.

Como trabalhar:
- Explore antes de editar: liste diretórios e leia arquivos relevantes.
- Faça mudanças pequenas e verificáveis.
- Quando houver como verificar (testes, execução), verifique você mesmo com run_command.
- Ao terminar a tarefa, pare de chamar ferramentas e escreva um resumo curto do
  que foi feito e como verificou.

Seja direto e eficiente com as chamadas de ferramenta.
"""


def build_system(config: Config) -> list[dict]:
    """System prompt como bloco cacheável (estável entre iterações)."""
    return [
        {
            "type": "text",
            "text": SYSTEM_TEMPLATE,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def truncate_output(text: str, max_bytes: int) -> str:
    """Trunca no meio, preservando início e fim (mais úteis que o miolo)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    head = encoded[: max_bytes // 2].decode("utf-8", errors="ignore")
    tail = encoded[-max_bytes // 2 :].decode("utf-8", errors="ignore")
    omitted = len(encoded) - max_bytes
    return f"{head}\n\n... [{omitted} bytes omitidos pelo harness] ...\n\n{tail}"
