"""Validacao de autenticidade das requisicoes de entrada.

1) Webhook da Evolution -> HMAC SHA-256 do corpo cru, comparado em tempo
   constante com o header `x-hub-signature-256` (`sha256=...`). Se
   WEBHOOK_HMAC_SECRET estiver vazio, a verificacao e pulada (apenas dev).

2) Push do Pub/Sub -> token OIDC no header Authorization, validado contra a SA
   autorizada (PUBSUB_PUSH_SA_EMAIL). Garante que so o Pub/Sub invoca o
   processador.
"""

from __future__ import annotations

import hashlib
import hmac

from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    s = get_settings()
    if not s.webhook_hmac_secret:
        log.warning("WEBHOOK_HMAC_SECRET vazio — verificacao HMAC desabilitada (use so em dev)")
        return True
    if not signature_header:
        return False
    expected = hmac.new(
        s.webhook_hmac_secret.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


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
