"""Tool UNIVERSAL: buscar no historico longo de conversas do usuario.

Permite ao agente recuperar contexto de interacoes anteriores que ja sairam da
janela curta (Redis), consultando o Postgres.
"""

from __future__ import annotations

from agent import memory
from agent.tool_base import AgentTool, ToolContext


async def _run(ctx: ToolContext, limite: int = 10) -> dict:
    limite = max(1, min(int(limite), 50))
    turns = await memory.recent_long_history(ctx.user.id, limit=limite)
    return {
        "total": len(turns),
        "mensagens": [{"role": t.role, "content": t.content} for t in turns],
    }


TOOL = AgentTool(
    name="search_conversation_history",
    description=(
        "Recupera as mensagens mais recentes do historico completo de conversas "
        "deste usuario. Use quando precisar lembrar de algo discutido antes que "
        "nao esta no contexto atual da conversa."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limite": {
                "type": "integer",
                "description": "Quantidade de mensagens a recuperar (1-50, padrao 10)",
            },
        },
        "required": [],
    },
    handler=_run,
    category="universal",
)
