"""Configuracao central via variaveis de ambiente (pydantic-settings).

Toda configuracao do core passa por aqui. Em runtime no Cloud Run, os valores
vem de variaveis de ambiente injetadas pelo Terraform / Secret Manager. Em local,
de um arquivo `.env`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- GCP / Vertex AI ---
    gcp_project_id: str = "local-project"
    gcp_location: str = "southamerica-east1"
    gemini_model: str = "gemini-3.5-flash"
    embedding_model: str = "text-embedding-004"
    embedding_dim: int = 768

    # --- Cloud SQL ---
    db_instance_connection_name: str = ""
    db_name: str = "agent"
    db_user: str = "agent"
    db_password: str = ""
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    use_cloud_sql: bool = True

    # --- Redis ---
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    session_ttl_seconds: int = 3600
    short_history_turns: int = 10

    # --- Pub/Sub ---
    pubsub_topic: str = "agent-messages"
    pubsub_push_sa_email: str = ""
    pubsub_audience: str = ""

    # --- Evolution API ---
    evolution_base_url: str = "http://127.0.0.1:8080"
    evolution_api_key: str = ""
    webhook_hmac_secret: str = ""

    # --- RAG ---
    rag_score_threshold: float = 0.75
    rag_top_k: int = 5

    # --- Debounce / agrupamento de mensagens ---
    # Janela de silencio (segundos) para agrupar mensagens quebradas em bolhas.
    # 0 desabilita o agrupamento (processa cada mensagem na hora).
    debounce_seconds: float = 8.0
    # TTL do buffer no Redis (seguranca contra lixo orfao).
    debounce_buffer_ttl_seconds: int = 300

    # --- Indicador "digitando..." (presence composing) ---
    # Mostra "digitando..." no WhatsApp enquanto o agente gera a resposta.
    typing_indicator: bool = True
    # Tempo (ms) que cada pulso de presence dura; e re-emitido ate a resposta sair.
    typing_refresh_ms: int = 3000

    # --- Follow-up (re-engajamento) ---
    # A config por agente fica em agent_configs.config["followup"]. Aqui ficam
    # apenas os parametros do mecanismo de sweep.
    scheduler_sa_email: str = ""        # SA do Cloud Scheduler autorizada no sweep
    followup_sweep_batch: int = 100     # quantas conversas reivindicar por sweep
    followup_lease_minutes: int = 10    # backoff/lease ao reivindicar (anti corrida)

    # --- Runtime ---
    default_agent_id: str = "default"
    max_tool_iterations: int = 6
    env: str = "dev"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Retorna a instancia unica de Settings (cacheada)."""
    return Settings()
