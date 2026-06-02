"""Core do agente — o loop de processamento de uma mensagem.

Sequencia (plano, secao "Processamento"):
  1. idempotencia (Postgres)
  2. contexto do usuario (Redis curto + Postgres perfil)
  3. RAG automatico (embedding -> PgVector -> injecao no system prompt)
  4. montar prompt final
  5. Gemini via Vertex com function calling (loop de tools)
  6. salvar turno (Redis + Postgres)
  7. enviar resposta via Evolution API

Este modulo e core imutavel — colaboradores estendem via tools/, nao aqui.
"""

from __future__ import annotations

import json

from google.genai import types

from agent import evolution, memory, rag, redis_client
from agent.config import get_settings
from agent.genai_client import get_client
from agent.logging_config import get_logger
from agent.models import AgentConfig, InboundMessage, Turn
from agent.tool_base import ToolContext
from agent.tool_registry import as_genai_tools, tools_for_agent

log = get_logger(__name__)


def _build_system_prompt(base_prompt: str, rag_context: str) -> str:
    parts = [base_prompt.strip()]
    if rag_context:
        parts.append("\n" + rag_context)
    return "\n".join(parts)


def _history_to_contents(history: list[Turn], current_text: str) -> list[types.Content]:
    """Converte historico curto + mensagem atual no formato de contents do SDK."""
    contents: list[types.Content] = []
    for turn in history:
        role = "user" if turn.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=turn.content)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=current_text)]))
    return contents


async def _resolve_agent_config(instance_name: str) -> AgentConfig:
    cfg = await memory.get_agent_config(instance_name)
    if cfg is not None:
        return cfg
    # Fallback: agente default se a instancia nao estiver cadastrada.
    s = get_settings()
    log.warning(
        "Instancia sem agent_config — usando default",
        extra={"fields": {"instance": instance_name}},
    )
    return AgentConfig(
        instance_name=instance_name,
        agent_id=s.default_agent_id,
        system_prompt=(
            "Voce e um assistente prestativo no WhatsApp. Responda em portugues, "
            "de forma curta e direta."
        ),
        tools_enabled=[],
        config={},
    )


async def process_message(msg: InboundMessage, *, check_idempotency: bool = True) -> None:
    """Processa um turno.

    check_idempotency=False e usado pelo caminho de debounce (agent/buffer.py),
    onde as bolhas individuais ja foram dedupadas antes de serem agrupadas.
    """
    s = get_settings()

    # 1. Idempotencia — claim atomico (vence a corrida entre instancias).
    if check_idempotency and not await memory.mark_processed(msg.message_id):
        log.info("Mensagem duplicada — descartada", extra={"fields": {"mid": msg.message_id}})
        return

    cfg = await _resolve_agent_config(msg.instance_name)

    # 2. Contexto do usuario.
    user = await memory.get_or_create_user(msg.phone, msg.name)
    history = await redis_client.get_history(msg.instance_name, msg.phone)

    # 3-5. RAG + geracao. Mostra "digitando..." enquanto processa (best-effort).
    async with evolution.typing(msg.instance_name, msg.phone):
        final_text, rag_hits = await _generate_reply(msg, cfg, user, history)

    # 6. Persistencia do turno (curto + longo).
    await redis_client.append_turns(
        msg.instance_name,
        msg.phone,
        Turn(role="user", content=msg.text),
        Turn(role="agent", content=final_text),
    )
    await memory.save_turn(user.id, "user", msg.text)
    await memory.save_turn(user.id, "agent", final_text)

    # 7. Envio da resposta.
    await evolution.send_text(msg.instance_name, msg.phone, final_text)
    log.info(
        "Turno concluido",
        extra={"fields": {"agent_id": cfg.agent_id, "phone": msg.phone, "rag_hits": rag_hits}},
    )


async def _generate_reply(msg, cfg, user, history) -> tuple[str, int]:
    """RAG + loop de function calling. Retorna (texto_final, qtd_hits_rag).

    Extraido de process_message para rodar dentro do indicador "digitando...".
    """
    s = get_settings()

    # 3. RAG automatico.
    hits = await rag.retrieve(msg.text, cfg.agent_id)
    rag_context = rag.format_context(hits)

    # 4. Prompt final.
    system_prompt = _build_system_prompt(cfg.system_prompt, rag_context)
    contents = _history_to_contents(history, msg.text)

    # 5. Loop de function calling.
    selected_tools = tools_for_agent(cfg.tools_enabled)
    genai_tools = as_genai_tools(selected_tools)
    tool_ctx = ToolContext(
        agent_id=cfg.agent_id,
        instance_name=msg.instance_name,
        user=user,
        config=cfg.config,
    )
    client = get_client()

    final_text = ""
    for iteration in range(s.max_tool_iterations):
        response = client.models.generate_content(
            model=s.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=genai_tools or None,
                temperature=0.4,
            ),
        )

        calls = response.function_calls or []
        if not calls:
            final_text = (response.text or "").strip()
            break

        # Anexa a resposta do modelo (com as function calls) ao historico da chamada.
        contents.append(response.candidates[0].content)

        tool_response_parts: list[types.Part] = []
        for call in calls:
            tool = selected_tools.get(call.name)
            args = dict(call.args or {})
            if tool is None:
                result = {"error": f"tool desconhecida: {call.name}"}
            else:
                try:
                    result = await tool.run(tool_ctx, **args)
                except Exception as exc:  # noqa: BLE001 — devolver erro ao modelo
                    log.exception("Erro executando tool")
                    result = {"error": str(exc)}
            log.info(
                "Tool executada",
                extra={"fields": {"tool": call.name, "iter": iteration}},
            )
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=call.name,
                    response=result if isinstance(result, dict) else {"result": result},
                )
            )
        contents.append(types.Content(role="user", parts=tool_response_parts))
    else:
        log.warning("max_tool_iterations atingido sem resposta final")
        final_text = "Desculpe, nao consegui concluir agora. Pode reformular?"

    if not final_text:
        final_text = "Desculpe, nao entendi. Pode reformular?"

    return final_text, len(hits)


def serialize_result(result) -> str:
    """Helper para tools que retornam objetos nao-dict — garante JSON serializavel."""
    return json.dumps(result, ensure_ascii=False, default=str)
