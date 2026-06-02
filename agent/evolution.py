"""Cliente da Evolution API — envio de mensagens e indicador "digitando...".

A Evolution roda no Compute Engine; aqui so a chamamos via HTTP REST. A apikey
vai no header. Retry com backoff para o envio de texto. A presenca
("digitando...") e best-effort: nunca quebra o fluxo do agente.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.config import get_settings
from agent.logging_config import get_logger, mask_phone

log = get_logger(__name__)


def _headers() -> dict[str, str]:
    return {"apikey": get_settings().evolution_api_key, "Content-Type": "application/json"}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
async def send_text(instance_name: str, phone: str, text: str) -> None:
    """Envia uma mensagem de texto via Evolution API (endpoint sendText)."""
    s = get_settings()
    url = f"{s.evolution_base_url}/message/sendText/{instance_name}"
    payload = {"number": phone, "text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=_headers())
        resp.raise_for_status()
    log.info(
        "Resposta enviada",
        extra={"fields": {"instance": instance_name, "phone": mask_phone(phone)}},
    )


async def send_presence(
    instance_name: str, phone: str, presence: str = "composing", delay_ms: int = 3000
) -> None:
    """Envia um estado de presenca (POST /chat/sendPresence).

    presence: "composing" (digitando...), "recording" (gravando audio...),
              "paused", "available", "unavailable".
    delay_ms: por quanto tempo o indicador fica visivel.

    Best-effort: qualquer falha so loga (warning) e nao propaga — o indicador
    e cosmetico e nao pode derrubar o processamento.
    """
    s = get_settings()
    url = f"{s.evolution_base_url}/chat/sendPresence/{instance_name}"
    payload = {"number": phone, "delay": delay_ms, "presence": presence}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=_headers())
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — presenca e cosmetica
        log.warning("Falha ao enviar presence", extra={"fields": {"err": str(exc)}})


@asynccontextmanager
async def typing(instance_name: str, phone: str):
    """Context manager que mantem "digitando..." enquanto o bloco executa.

    Inicia uma task que re-emite `composing` a cada ~80% do refresh, cobrindo
    geracoes de qualquer duracao. Ao sair, cancela a task; a chegada do texto
    limpa o indicador no WhatsApp.

        async with evolution.typing(instance, phone):
            ...  # geracao lenta (RAG + Gemini)
        await evolution.send_text(instance, phone, resposta)
    """
    s = get_settings()
    if not s.typing_indicator:
        yield
        return

    refresh_ms = max(1000, s.typing_refresh_ms)

    async def _pulse() -> None:
        try:
            while True:
                await send_presence(instance_name, phone, "composing", refresh_ms)
                await asyncio.sleep(refresh_ms / 1000 * 0.8)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(_pulse())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
