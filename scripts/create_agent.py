#!/usr/bin/env python3
"""Registra um novo agente (novo cliente) no banco.

Insere/atualiza um registro em agent_configs. Cada agente = uma instancia da
Evolution (numero de WhatsApp) + um agent_id (isola a base de conhecimento) +
um system prompt + a lista de tools ativas.

Uso:
    python scripts/create_agent.py \
        --instance loja-acme \
        --agent-id acme \
        --system-prompt "Voce e a atendente da Loja Acme..." \
        --tools check_order_status

Depois, ingira a base de conhecimento desse agente:
    python scripts/ingest.py --csv knowledge/acme.csv --agent-id acme
"""

from __future__ import annotations

import argparse
import asyncio
import json

from agent import db
from agent.logging_config import get_logger

log = get_logger("create_agent")


async def upsert_agent(
    instance: str, agent_id: str, system_prompt: str, tools: list[str], config: dict
) -> None:
    await db.execute(
        """INSERT INTO agent_configs (instance_name, agent_id, system_prompt, tools_enabled, config)
           VALUES ($1, $2, $3, $4, $5::jsonb)
           ON CONFLICT (instance_name)
           DO UPDATE SET agent_id = EXCLUDED.agent_id,
                         system_prompt = EXCLUDED.system_prompt,
                         tools_enabled = EXCLUDED.tools_enabled,
                         config = EXCLUDED.config""",
        instance, agent_id, system_prompt, tools, json.dumps(config),
    )
    log.info("Agente registrado", extra={"fields": {"instance": instance, "agent_id": agent_id}})
    await db.close_pool()


def main() -> None:
    p = argparse.ArgumentParser(description="Registra/atualiza um agente em agent_configs.")
    p.add_argument("--instance", required=True, help="Nome da instancia Evolution")
    p.add_argument("--agent-id", required=True, help="ID do agente (isola a base RAG)")
    p.add_argument("--system-prompt", required=True, help="System prompt / persona")
    p.add_argument("--tools", nargs="*", default=[], help="Tools de dominio ativas (universais ja entram)")
    p.add_argument("--config", default="{}", help="JSON de configuracoes extras")
    args = p.parse_args()

    asyncio.run(
        upsert_agent(
            args.instance, args.agent_id, args.system_prompt, args.tools, json.loads(args.config)
        )
    )


if __name__ == "__main__":
    main()
