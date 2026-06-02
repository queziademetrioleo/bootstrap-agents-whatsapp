"""Debounce / agrupamento de mensagens quebradas em bolhas.

Quando o usuario manda varias mensagens seguidas ("ola" / "tudo bem?" /
"tenho duvidas..."), cada bolha chega como um evento separado. Sem agrupamento,
o agente responderia 3 vezes. Aqui acumulamos as bolhas num buffer no Redis e
processamos tudo junto apos uma janela de silencio (DEBOUNCE_SECONDS).

Padrao do marcador (concorrencia sem corrida):
  - cada bolha faz RPUSH no buffer e grava um "marcador" = message_id dela
  - o /pubsub/push dorme DEBOUNCE_SECONDS e relê o marcador
  - so a bolha cujo id == marcador atual (ninguem mandou nada depois) faz o FLUSH
  - as demais saem sem fazer nada

Dedup de entregas do Pub/Sub (at-least-once):
  - duplicata DENTRO da janela  -> guardada por um SET Redis (SADD idempotente)
  - duplicata APOS o flush       -> guardada por processed_messages (Postgres),
                                    marcado so APOS o processamento dar certo
"""

from __future__ import annotations

import json

from agent import memory
from agent.config import get_settings
from agent.models import InboundMessage
from agent.redis_client import get_client


def _buf_key(instance: str, phone: str) -> str:
    return f"buffer:{instance}:{phone}"


def _marker_key(instance: str, phone: str) -> str:
    return f"buffer_marker:{instance}:{phone}"


def _ids_key(instance: str, phone: str) -> str:
    return f"buffer_ids:{instance}:{phone}"


async def should_buffer(msg: InboundMessage) -> bool:
    """Adiciona a bolha ao buffer. Retorna False se for duplicata (ignorar).

    Faz dois guardas de dedup:
      - already_processed (Postgres) -> duplicata tardia, ja flushada antes
      - SADD no SET (Redis)          -> duplicata dentro da janela atual
    """
    if await memory.already_processed(msg.message_id):
        return False

    s = get_settings()
    client = get_client()
    ttl = s.debounce_buffer_ttl_seconds

    added = await client.sadd(_ids_key(msg.instance_name, msg.phone), msg.message_id)
    if added == 0:
        return False  # ja estava no buffer (redelivery dentro da janela)

    entry = json.dumps(
        {"text": msg.text, "name": msg.name, "message_id": msg.message_id, "ts": msg.timestamp},
        ensure_ascii=False,
    )
    async with client.pipeline(transaction=True) as pipe:
        pipe.expire(_ids_key(msg.instance_name, msg.phone), ttl)
        pipe.rpush(_buf_key(msg.instance_name, msg.phone), entry)
        pipe.expire(_buf_key(msg.instance_name, msg.phone), ttl)
        pipe.set(_marker_key(msg.instance_name, msg.phone), msg.message_id, ex=ttl)
        await pipe.execute()
    return True


async def is_latest(instance: str, phone: str, message_id: str) -> bool:
    """True se esta bolha ainda e a mais recente (ninguem mandou nada depois)."""
    marker = await get_client().get(_marker_key(instance, phone))
    return marker == message_id


async def drain(instance: str, phone: str) -> list[dict]:
    """Remove e retorna todas as bolhas acumuladas, em ordem de chegada."""
    client = get_client()
    async with client.pipeline(transaction=True) as pipe:
        pipe.lrange(_buf_key(instance, phone), 0, -1)
        pipe.delete(_buf_key(instance, phone))
        pipe.delete(_marker_key(instance, phone))
        pipe.delete(_ids_key(instance, phone))
        results = await pipe.execute()
    return [json.loads(r) for r in results[0]]


def combine(latest: InboundMessage, entries: list[dict]) -> InboundMessage:
    """Monta uma unica InboundMessage juntando o texto das bolhas (em ordem)."""
    combined_text = "\n".join(e["text"] for e in entries if e.get("text"))
    name = latest.name or next((e.get("name") for e in entries if e.get("name")), None)
    return InboundMessage(
        # id sintetico — o core nao re-checa idempotencia neste caminho.
        message_id=f"flush:{latest.instance_name}:{latest.phone}:{latest.message_id}",
        instance_name=latest.instance_name,
        phone=latest.phone,
        name=name,
        text=combined_text,
        timestamp=latest.timestamp,
    )


async def mark_entries_processed(entries: list[dict]) -> None:
    """Marca cada bolha em processed_messages — guarda contra duplicatas tardias.

    Chamado SO apos o processamento dar certo, para que uma falha (retry) possa
    reprocessar sem perder a mensagem.
    """
    for e in entries:
        mid = e.get("message_id")
        if mid:
            await memory.mark_processed(mid)
