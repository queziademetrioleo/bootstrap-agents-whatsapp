"""Modelos de dados internos do agente (Pydantic)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InboundMessage(BaseModel):
    """Mensagem normalizada que trafega no Pub/Sub.

    O webhook receiver normaliza o payload cru da Evolution para este formato
    antes de publicar. O processador consome exatamente isto.
    """

    message_id: str
    instance_name: str = Field(description="Nome da instancia Evolution = identidade do agente")
    phone: str = Field(description="Numero do remetente (sem sufixo @s.whatsapp.net)")
    name: str | None = None
    text: str
    timestamp: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class UserProfile(BaseModel):
    id: int
    phone: str
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class Turn(BaseModel):
    role: str  # "user" | "agent"
    content: str


class RagHit(BaseModel):
    pergunta: str
    resposta: str
    score: float


class AgentConfig(BaseModel):
    id: int | None = None
    instance_name: str
    system_prompt: str
    tools_enabled: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    agent_id: str
