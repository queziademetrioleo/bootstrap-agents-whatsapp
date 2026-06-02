"""Normalizacao do payload cru da Evolution -> InboundMessage.

A Evolution (Baileys) entrega o evento `messages.upsert` com a estrutura abaixo.
So tratamos mensagens de texto recebidas (fromMe=false). Retorna None quando o
evento deve ser ignorado (mensagem propria, sem texto, evento de conexao, etc).
"""

from __future__ import annotations

from typing import Any

from agent.models import InboundMessage


def _extract_text(message: dict[str, Any]) -> str | None:
    if not message:
        return None
    if "conversation" in message:
        return message["conversation"]
    if "extendedTextMessage" in message:
        return message["extendedTextMessage"].get("text")
    # Legendas de midia tambem sao texto util.
    for media in ("imageMessage", "videoMessage", "documentMessage"):
        if media in message and message[media].get("caption"):
            return message[media]["caption"]
    return None


def parse_evolution_event(payload: dict[str, Any]) -> InboundMessage | None:
    event = (payload.get("event") or "").lower().replace("_", ".")
    if event != "messages.upsert":
        return None

    instance = payload.get("instance") or payload.get("instanceName")
    data = payload.get("data") or {}
    key = data.get("key") or {}

    if key.get("fromMe"):
        return None  # ignora mensagens enviadas pelo proprio numero

    remote_jid = key.get("remoteJid") or ""
    if remote_jid.endswith("@g.us"):
        return None  # ignora grupos por padrao

    phone = remote_jid.split("@", 1)[0]
    text = _extract_text(data.get("message") or {})
    if not text or not phone or not instance:
        return None

    return InboundMessage(
        message_id=key.get("id") or f"{instance}:{phone}:{data.get('messageTimestamp')}",
        instance_name=instance,
        phone=phone,
        name=data.get("pushName"),
        text=text,
        timestamp=data.get("messageTimestamp"),
        raw=data,
    )
