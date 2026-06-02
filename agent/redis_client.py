"""Cliente Redis (Memorystore) para a sessao curta de conversa.

Chave por usuario: `session:{instance_name}:{phone}`.
Guarda os ultimos N turnos como uma lista JSON, com TTL de 1h (renovado a cada
gravacao). O acesso e controlado pela VPC — sem IAM, sem senha em runtime.
"""

from __future__ import annotations

import json

import redis.asyncio as redis

from agent.config import get_settings
from agent.models import Turn

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        s = get_settings()
        _client = redis.Redis(
            host=s.redis_host,
            port=s.redis_port,
            decode_responses=True,
        )
    return _client


def _key(instance_name: str, phone: str) -> str:
    return f"session:{instance_name}:{phone}"


async def get_history(instance_name: str, phone: str) -> list[Turn]:
    s = get_settings()
    raw = await get_client().get(_key(instance_name, phone))
    if not raw:
        return []
    items = json.loads(raw)
    turns = [Turn(**t) for t in items]
    return turns[-s.short_history_turns * 2 :]


async def append_turns(instance_name: str, phone: str, *turns: Turn) -> None:
    """Adiciona turnos ao historico curto e renova o TTL."""
    s = get_settings()
    client = get_client()
    history = await get_history(instance_name, phone)
    history.extend(turns)
    history = history[-s.short_history_turns * 2 :]
    await client.set(
        _key(instance_name, phone),
        json.dumps([t.model_dump() for t in history], ensure_ascii=False),
        ex=s.session_ttl_seconds,
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
