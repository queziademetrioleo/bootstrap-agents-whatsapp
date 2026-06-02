"""Camada de acesso ao PostgreSQL (Cloud SQL) com pool asyncpg.

Conexao:
- Em runtime no Cloud Run: Cloud SQL Python Connector (sem Auth Proxy binario,
  sem sidecar). A SA do agente precisa de `roles/cloudsql.client`.
- Em local: conexao TCP direta (DB_HOST/DB_PORT) quando USE_CLOUD_SQL=false.

Referencia: https://cloud.google.com/sql/docs/postgres/connect-run
"""

from __future__ import annotations

from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from agent.config import Settings, get_settings
from agent.logging_config import get_logger

log = get_logger(__name__)

_pool: asyncpg.Pool | None = None
_connector: Any = None  # google.cloud.sql.connector.Connector (lazy)


async def _init_vector(conn: asyncpg.Connection) -> None:
    await register_vector(conn)


async def _connect_cloud_sql(s: Settings) -> asyncpg.Connection:
    """Cria uma conexao asyncpg via Cloud SQL Python Connector."""
    global _connector
    if _connector is None:
        from google.cloud.sql.connector import Connector, IPTypes

        _connector = Connector(ip_type=IPTypes.PRIVATE)
    conn = await _connector.connect_async(
        s.db_instance_connection_name,
        "asyncpg",
        user=s.db_user,
        password=s.db_password,
        db=s.db_name,
    )
    return conn


async def get_pool() -> asyncpg.Pool:
    """Retorna o pool global, criando-o sob demanda."""
    global _pool
    if _pool is not None:
        return _pool

    s = get_settings()
    if s.use_cloud_sql and s.db_instance_connection_name:
        log.info("Inicializando pool via Cloud SQL Connector")
        _pool = await asyncpg.create_pool(
            connect=lambda: _connect_cloud_sql(s),
            min_size=1,
            max_size=5,
            init=_init_vector,
        )
    else:
        log.info("Inicializando pool TCP local", extra={"fields": {"host": s.db_host}})
        _pool = await asyncpg.create_pool(
            host=s.db_host,
            port=s.db_port,
            user=s.db_user,
            password=s.db_password,
            database=s.db_name,
            min_size=1,
            max_size=5,
            init=_init_vector,
        )
    return _pool


async def close_pool() -> None:
    global _pool, _connector
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _connector is not None:
        await _connector.close_async()
        _connector = None


# ------------------------------------------------------------------ helpers --


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
