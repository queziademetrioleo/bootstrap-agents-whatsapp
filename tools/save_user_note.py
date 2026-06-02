"""Tool UNIVERSAL: salvar uma nota/preferencia sobre o usuario.

Persiste no metadata (JSONB) do usuario para personalizar futuras conversas.
"""

from __future__ import annotations

from agent import memory
from agent.tool_base import AgentTool, ToolContext


async def _run(ctx: ToolContext, chave: str, valor: str) -> dict:
    notes = dict(ctx.user.metadata.get("notes", {}))
    notes[chave] = valor
    await memory.update_user_metadata(ctx.user.id, {"notes": notes})
    return {"ok": True, "salvo": {chave: valor}}


TOOL = AgentTool(
    name="save_user_note",
    description=(
        "Salva uma informacao ou preferencia importante sobre o usuario para "
        "lembrar em conversas futuras (ex.: nome preferido, alergia, endereco). "
        "Use quando o usuario revelar um dado pessoal estavel que valha guardar."
    ),
    parameters={
        "type": "object",
        "properties": {
            "chave": {"type": "string", "description": "Identificador curto da nota, ex.: 'cidade'"},
            "valor": {"type": "string", "description": "Conteudo da nota"},
        },
        "required": ["chave", "valor"],
    },
    handler=_run,
    category="universal",
)
