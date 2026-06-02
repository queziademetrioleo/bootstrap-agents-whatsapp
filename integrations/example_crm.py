"""Integracao de EXEMPLO com um CRM/ERP ficticio.

EXEMPLO DIDATICO — mostra o padrao de uma integracao real:
  - base_url por variavel de ambiente
  - credencial via Secret Manager (nunca hardcoded)
  - cliente HTTP base com retry/timeout

A funcao retorna dados simulados quando nao ha CRM_BASE_URL configurado, para o
template funcionar end-to-end sem dependencia externa. Numa integracao real,
remova o bloco de simulacao.
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import quote

from integrations.base import HttpClient, secret
from agent.tool_base import ToolContext


@lru_cache
def _client() -> HttpClient | None:
    base_url = os.getenv("CRM_BASE_URL", "")
    if not base_url:
        return None  # modo simulado
    token = secret("CRM_API_TOKEN") or ""
    return HttpClient(base_url, default_headers={"Authorization": f"Bearer {token}"})


async def get_order(ctx: ToolContext, numero_pedido: str) -> dict | None:
    client = _client()
    if client is None:
        # Simulacao para o template rodar sem CRM real.
        if numero_pedido.strip().lower() in {"0", "naoexiste"}:
            return None
        return {
            "numero_pedido": numero_pedido,
            "status": "em transporte",
            "previsao_entrega": "2 dias uteis",
            "itens": ["Item exemplo A", "Item exemplo B"],
            "_simulado": True,
        }

    # quote() evita path traversal/SSRF se o numero vier com "/" ou ".." do modelo.
    resp = await client.get(f"/orders/{quote(numero_pedido, safe='')}")
    if resp.status_code == 404:
        return None
    return resp.json()
