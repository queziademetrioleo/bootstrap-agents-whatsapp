"""Aplicacao FastAPI — uma unica imagem, dois papeis.

A MESMA imagem roda como dois servicos no Cloud Run:
  - webhook receiver  -> usa POST /webhook
  - processador       -> usa POST /pubsub/push

Manter os dois endpoints no mesmo app simplifica o build (uma imagem so). O
roteamento de responsabilidade e feito pela infra (qual servico recebe o que).

Fluxo:
  Evolution --POST /webhook--> publica no Pub/Sub --push--> POST /pubsub/push --> core
"""

from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request, Response

from agent import core, db, pubsub_client, redis_client, security
from agent.logging_config import get_logger
from agent.models import InboundMessage
from agent.webhook_parse import parse_evolution_event

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_pool()  # aquece o pool no boot (reduz latencia da 1a request)
    yield
    await db.close_pool()
    await redis_client.close()


app = FastAPI(title="WhatsApp AI Agent", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ----------------------------------------------------------- webhook receiver --


@app.post("/webhook")
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> Response:
    """Recebe o evento da Evolution, valida, normaliza e publica no Pub/Sub.

    Responde 200 imediatamente — nunca processa de forma sincrona aqui.
    """
    raw = await request.body()
    if not security.verify_webhook_signature(raw, x_hub_signature_256):
        log.warning("Webhook com assinatura invalida — rejeitado")
        return Response(status_code=401)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return Response(status_code=400)

    msg = parse_evolution_event(payload)
    if msg is None:
        return Response(status_code=204)  # evento ignorado (grupo, fromMe, sem texto)

    try:
        pubsub_client.publish_message(msg)
    except Exception:  # noqa: BLE001
        log.exception("Falha ao publicar no Pub/Sub")
        # 500 faz a Evolution reenviar; a idempotencia protege contra duplicata.
        return Response(status_code=500)

    return Response(status_code=200)


# ---------------------------------------------------------------- processador --


@app.post("/pubsub/push")
async def pubsub_push(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    """Consome o push do Pub/Sub e roda o core do agente.

    Sempre retorna 200 quando a mensagem foi tratada (ou descartada de propósito)
    para o Pub/Sub dar ack. Em erro transitorio, retorna 500 -> retry automatico.
    """
    if not await security.verify_pubsub_oidc(authorization):
        return Response(status_code=401)

    envelope = await request.json()
    message = envelope.get("message", {})
    data_b64 = message.get("data")
    if not data_b64:
        return Response(status_code=204)

    try:
        payload = json.loads(base64.b64decode(data_b64).decode("utf-8"))
        msg = InboundMessage(**payload)
    except Exception:  # noqa: BLE001 — payload malformado nao deve voltar pra fila
        log.exception("Payload Pub/Sub invalido — descartado")
        return Response(status_code=200)

    try:
        await core.process_message(msg)
    except Exception:  # noqa: BLE001
        log.exception("Erro no processamento — retry via Pub/Sub")
        return Response(status_code=500)

    return Response(status_code=200)
