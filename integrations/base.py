"""Cliente HTTP base para integracoes externas.

Traz o padrao do template: timeout, retry com backoff exponencial e leitura de
credenciais do Secret Manager (cacheada). O colaborador nao reimplementa nada
disso — so instancia HttpClient e chama get/post.

Credenciais NUNCA ficam hardcoded. Em runtime no Cloud Run, o Secret Manager
injeta o segredo como variavel de ambiente; aqui lemos via `secret()`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.config import get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=64)
def secret(name: str) -> str | None:
    """Le um segredo.

    1) Se existir uma variavel de ambiente com o mesmo nome (forma recomendada —
       o Cloud Run monta o segredo como env var), usa ela.
    2) Senao, busca direto no Secret Manager (latest version).
    """
    if name in os.environ:
        return os.environ[name]
    try:
        from google.cloud import secretmanager

        s = get_settings()
        client = secretmanager.SecretManagerServiceClient()
        path = f"projects/{s.gcp_project_id}/secrets/{name}/versions/latest"
        resp = client.access_secret_version(name=path)
        return resp.payload.data.decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("Segredo nao encontrado", extra={"fields": {"name": name, "err": str(exc)}})
        return None


class HttpClient:
    """Wrapper fino sobre httpx.AsyncClient com retry padronizado."""

    def __init__(
        self,
        base_url: str,
        *,
        default_headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {**self.default_headers, **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            resp = await client.request(method, path, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp

    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)
