"""Guardrails via Google Model Armor.

Camada de seguranca de IA: rastreia a mensagem do usuario (prompt injection,
jailbreak, conteudo perigoso, dados sensiveis, URLs maliciosas) e, opcionalmente,
a resposta do modelo, antes de ela sair. Tudo configurado num *template* do Model
Armor (criado via Terraform) — os filtros e limiares vivem la, nao no codigo.

Decisao de modo de falha:
  - MATCH_FOUND (o conteudo casou um filtro) -> BLOQUEIA (fail-closed). E o ponto
    do guardrail.
  - Erro da API do Model Armor (indisponibilidade) -> NAO bloqueia (fail-open),
    so loga. Um agente de atendimento nao deve cair porque o Model Armor piscou.
    Troque `fail_open` para False se preferir bloquear em caso de erro.

Auth por IAM (SA do Cloud Run com roles/modelarmor.user). Sem API key.
Endpoint regional: modelarmor.{location}.rep.googleapis.com
"""

from __future__ import annotations

from functools import lru_cache

from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


@lru_cache
def _client():
    from google.cloud import modelarmor_v1

    s = get_settings()
    return modelarmor_v1.ModelArmorClient(
        client_options={"api_endpoint": f"modelarmor.{s.gcp_location}.rep.googleapis.com"}
    )


def _template_path() -> str:
    s = get_settings()
    return (
        f"projects/{s.gcp_project_id}/locations/{s.gcp_location}"
        f"/templates/{s.model_armor_template}"
    )


def _matched(result) -> bool:
    from google.cloud import modelarmor_v1

    state = result.sanitization_result.filter_match_state
    return state == modelarmor_v1.FilterMatchState.MATCH_FOUND


async def check_user_prompt(text: str) -> bool:
    """True se a mensagem do usuario for SEGURA (pode prosseguir).

    False = bloqueada por algum filtro do Model Armor.
    """
    s = get_settings()
    if not s.model_armor_enabled or not s.model_armor_template:
        return True
    try:
        from google.cloud import modelarmor_v1

        resp = _client().sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=_template_path(),
                user_prompt_data=modelarmor_v1.DataItem(text=text),
            )
        )
        if _matched(resp):
            log.warning("Guardrail bloqueou o prompt do usuario (Model Armor)")
            return False
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Model Armor indisponivel (prompt)", extra={"fields": {"err": str(exc)}})
        return s.model_armor_fail_open  # fail-open: True segue; False bloqueia


async def check_model_response(text: str, user_prompt: str = "") -> bool:
    """True se a resposta do modelo for SEGURA para enviar. False = bloqueada."""
    s = get_settings()
    if not s.model_armor_enabled or not s.model_armor_template:
        return True
    try:
        from google.cloud import modelarmor_v1

        resp = _client().sanitize_model_response(
            request=modelarmor_v1.SanitizeModelResponseRequest(
                name=_template_path(),
                model_response_data=modelarmor_v1.DataItem(text=text),
                user_prompt=user_prompt or None,
            )
        )
        if _matched(resp):
            log.warning("Guardrail bloqueou a resposta do modelo (Model Armor)")
            return False
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open
        log.warning("Model Armor indisponivel (resposta) — seguindo", extra={"fields": {"err": str(exc)}})
        return True
