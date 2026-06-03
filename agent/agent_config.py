"""Carrega a configuracao do agente (single-tenant) de config/agent.yaml.

1 repositorio = 1 cliente = 1 agente. A persona, as tools ativas e o follow-up
vivem num unico arquivo YAML que o cliente edita — nao mais numa tabela do banco
com varias linhas. O arquivo e empacotado na imagem Docker e lido uma vez no
boot (cacheado).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from agent.config import get_settings
from agent.models import AgentConfig


@lru_cache
def load_agent_config() -> AgentConfig:
    path = Path(get_settings().agent_config_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    instance_name = data.get("instance_name", "default")
    system_prompt = (data.get("system_prompt") or "").strip()
    if not system_prompt:
        raise ValueError(f"system_prompt vazio em {path}")

    return AgentConfig(
        instance_name=instance_name,
        agent_id=data.get("agent_id", instance_name),
        system_prompt=system_prompt,
        tools_enabled=list(data.get("tools_enabled") or []),
        config={"followup": data.get("followup") or {}},
    )
