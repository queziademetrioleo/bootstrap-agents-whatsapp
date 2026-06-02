"""Validacao de autenticidade das requisicoes de entrada.

1) Webhook da Evolution -> token estatico no header `x-webhook-token`, comparado
   em tempo constante. A Evolution e configurada para enviar esse header (config
   de webhook -> headers). Se WEBHOOK_TOKEN estiver vazio, a verificacao e pulada
   (apenas dev). Escolha pragmatica: a Evolution nao assina o corpo (HMAC), entao
   um token compartilhado e a forma simples e efetiva de autenticar a origem.

2) Push do Pub/Sub e Cloud Scheduler -> token OIDC, validado contra a SA emissora.
"""

from __future__ import annotations

import hmac

from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


def verify_webhook_token(token_header: str | None) -> bool:
    """Confere o token do webhook (header `x-webhook-token`) em tempo constante."""
    s = get_settings()
    if not s.webhook_token:
        log.warning("WEBHOOK_TOKEN vazio — verificacao do webhook desabilitada (use so em dev)")
        return True
    if not token_header:
        return False
    provided = token_header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(s.webhook_token, provided)


async def _verify_oidc(authorization: str | None, expected_email: str, audience: str) -> bool:
    """Valida um token OIDC Bearer e confere o email da SA emissora.

    Se `expected_email` estiver vazio, pula (dev). Em prod, o invoker IAM do
    Cloud Run ja e a 1a barreira; esta checagem e defensiva.
    """
    if not expected_email:
        return True
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    token = authorization.split(" ", 1)[1]
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            token, g_requests.Request(), audience=audience or None
        )
        return claims.get("email") == expected_email and claims.get("email_verified", False)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao validar OIDC", extra={"fields": {"err": str(exc)}})
        return False


async def verify_pubsub_oidc(authorization: str | None) -> bool:
    """Valida o token OIDC do push do Pub/Sub (processador)."""
    s = get_settings()
    return await _verify_oidc(authorization, s.pubsub_push_sa_email, s.pubsub_audience)


async def verify_scheduler_oidc(authorization: str | None) -> bool:
    """Valida o token OIDC do Cloud Scheduler (sweep de follow-ups)."""
    s = get_settings()
    return await _verify_oidc(authorization, s.scheduler_sa_email, "")
