"""Memoria longa e persistencia no Postgres: usuarios, conversas, idempotencia,
configuracao de agente. A sessao curta (Redis) vive em agent/redis_client.py.
"""

from __future__ import annotations

import json

from agent import db
from agent.models import AgentConfig, Turn, UserProfile

# --------------------------------------------------------------- idempotencia --


async def already_processed(message_id: str) -> bool:
    """True se o message_id ja foi registrado (evita reprocessar duplicatas)."""
    row = await db.fetchrow(
        "SELECT 1 FROM processed_messages WHERE message_id = $1", message_id
    )
    return row is not None


async def mark_processed(message_id: str) -> bool:
    """Registra o message_id. Retorna False se ja existia (corrida entre instancias)."""
    result = await db.execute(
        "INSERT INTO processed_messages (message_id) VALUES ($1) ON CONFLICT DO NOTHING",
        message_id,
    )
    return result.endswith("1")


async def cleanup_processed(older_than_days: int) -> None:
    """Remove registros de idempotencia antigos (evita crescimento sem fim)."""
    await db.execute(
        "DELETE FROM processed_messages WHERE processed_at < now() - make_interval(days => $1)",
        older_than_days,
    )


# ---------------------------------------------------------------------- users --


async def get_or_create_user(phone: str, name: str | None) -> UserProfile:
    row = await db.fetchrow("SELECT * FROM users WHERE phone = $1", phone)
    if row is None:
        row = await db.fetchrow(
            """INSERT INTO users (phone, name) VALUES ($1, $2)
               ON CONFLICT (phone) DO UPDATE SET name = COALESCE(users.name, EXCLUDED.name)
               RETURNING *""",
            phone,
            name,
        )
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return UserProfile(
        id=row["id"],
        phone=row["phone"],
        name=row["name"],
        metadata=metadata or {},
        created_at=row["created_at"],
    )


async def update_user_metadata(user_id: int, patch: dict) -> None:
    """Merge raso no JSONB de metadata do usuario."""
    await db.execute(
        "UPDATE users SET metadata = metadata || $2::jsonb WHERE id = $1",
        user_id,
        json.dumps(patch),
    )


# ---------------------------------------------------------------- conversas --


async def save_turn(user_id: int, role: str, content: str) -> None:
    await db.execute(
        "INSERT INTO conversations (user_id, role, content) VALUES ($1, $2, $3)",
        user_id,
        role,
        content,
    )


async def recent_long_history(user_id: int, limit: int = 20) -> list[Turn]:
    rows = await db.fetch(
        """SELECT role, content FROM conversations
           WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2""",
        user_id,
        limit,
    )
    return [Turn(role=r["role"], content=r["content"]) for r in reversed(rows)]


# ------------------------------------------------------------- agent_configs --


async def get_agent_config(instance_name: str) -> AgentConfig | None:
    row = await db.fetchrow(
        "SELECT * FROM agent_configs WHERE instance_name = $1", instance_name
    )
    if row is None:
        return None
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    return AgentConfig(
        id=row["id"],
        instance_name=row["instance_name"],
        system_prompt=row["system_prompt"],
        tools_enabled=list(row["tools_enabled"] or []),
        config=config or {},
        agent_id=row["agent_id"],
    )
