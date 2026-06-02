"""Tool de DOMINIO (exemplo): consultar status de pedido.

EXEMPLO DIDATICO — copie este arquivo como ponto de partida para uma tool sua.
Aqui usamos a integracao de exemplo (integrations/example_crm.py). Numa tool
real, troque pela sua integracao e regras de negocio.

Para ativar uma tool de dominio num agente, adicione o nome dela em
`tools_enabled` no registro de agent_configs (ver docs/creating-a-new-agent.md).
"""

from __future__ import annotations

from agent.tool_base import AgentTool, ToolContext
from integrations import example_crm


async def _run(ctx: ToolContext, numero_pedido: str) -> dict:
    pedido = await example_crm.get_order(ctx, numero_pedido)
    if pedido is None:
        return {"encontrado": False, "numero_pedido": numero_pedido}
    return {"encontrado": True, **pedido}


TOOL = AgentTool(
    name="check_order_status",
    description=(
        "Consulta o status de um pedido pelo numero. Retorna situacao, previsao "
        "de entrega e itens. Use quando o usuario perguntar sobre um pedido."
    ),
    parameters={
        "type": "object",
        "properties": {
            "numero_pedido": {"type": "string", "description": "Numero/codigo do pedido"},
        },
        "required": ["numero_pedido"],
    },
    handler=_run,
    category="domain",
)
