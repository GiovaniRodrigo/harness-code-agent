"""harness_ai — um coding-agent harness mínimo, porém real.

O LLM é apenas um componente. O harness fornece o ambiente: contexto,
ferramentas, estado, limites (policies), sandbox e feedback verificável
(evaluator). O ponto de entrada é `harness.loop.run_agent`.
"""

__version__ = "0.1.0"
