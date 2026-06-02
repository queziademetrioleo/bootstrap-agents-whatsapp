"""Cliente da Evolution API — envio de mensagens de volta ao WhatsApp.

A Evolution roda no Compute Engine; aqui so a chamamos via HTTP REST. A apikey
vai no header. Retry com backoff para resiliencia a instabilidade de rede.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
async def send_text(instance_name: str, phone: str, text: str) -> None:
    """Envia uma mensagem de texto via Evolution API (endpoint sendText)."""
    s = get_settings()
    url = f"{s.evolution_base_url}/message/sendText/{instance_name}"
    payload = {"number": phone, "text": text}
    headers = {"apikey": s.evolution_api_key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
    log.info("Resposta enviada", extra={"fields": {"instance": instance_name, "phone": phone}})
