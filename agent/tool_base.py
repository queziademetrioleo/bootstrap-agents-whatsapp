"""Contrato de uma Tool — a interface que o colaborador implementa.

Cada arquivo em `tools/` declara UMA tool, expondo uma variavel modulo-nivel
chamada `TOOL` (instancia de AgentTool). O registry faz auto-discovery.

Exemplo minimo (tools/minha_tool.py):

    from agent.tool_base import AgentTool, ToolContext

    async def _run(ctx: ToolContext, cidade: str) -> dict:
        return {"clima": "ensolarado", "cidade": cidade}

    TOOL = AgentTool(
        name="consultar_clima",
        description="Consulta o clima atual de uma cidade brasileira.",
        parameters={
            "type": "object",
            "properties": {
                "cidade": {"type": "string", "description": "Nome da cidade"},
            },
            "required": ["cidade"],
        },
        handler=_run,
        category="domain",
    )
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.models import UserProfile

# Categorias do plano: universais (core), de dominio, de integracao.
ToolCategory = str  # "universal" | "domain" | "integration"


@dataclass
class ToolContext:
    """Contexto injetado em toda execucao de tool.

    Da a tool acesso ao usuario e ao agente sem precisar reabrir conexoes nem
    saber nada sobre infraestrutura. Use os helpers de agent.memory / integrations.
    """

    agent_id: str
    instance_name: str
    user: UserProfile
    config: dict[str, Any] = field(default_factory=dict)


# Assinatura do handler: async def handler(ctx, **kwargs) -> Any (serializavel em JSON)
ToolHandler = Callable[..., Awaitable[Any]]


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema (object) dos argumentos
    handler: ToolHandler
    category: ToolCategory = "domain"

    def __post_init__(self) -> None:
        if not self.name or not self.name.replace("_", "").isalnum():
            raise ValueError(f"Nome de tool invalido: {self.name!r} (use snake_case alfanumerico)")
        if not inspect.iscoroutinefunction(self.handler):
            raise TypeError(f"O handler da tool {self.name!r} precisa ser `async def`.")
        if self.parameters.get("type") != "object":
            raise ValueError(f"parameters da tool {self.name!r} deve ser um JSON Schema do tipo object")

    async def run(self, ctx: ToolContext, **kwargs: Any) -> Any:
        return await self.handler(ctx, **kwargs)
