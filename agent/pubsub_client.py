"""Publicacao no Pub/Sub. Autenticacao por ADC (SA do Cloud Run)."""

from __future__ import annotations

import json
from functools import lru_cache

from google.cloud import pubsub_v1

from agent.config import get_settings
from agent.models import InboundMessage


@lru_cache
def _publisher() -> pubsub_v1.PublisherClient:
    return pubsub_v1.PublisherClient()


@lru_cache
def _topic_path() -> str:
    s = get_settings()
    return _publisher().topic_path(s.gcp_project_id, s.pubsub_topic)


def publish_message(msg: InboundMessage) -> str:
    """Publica a mensagem normalizada. Retorna o message_id do Pub/Sub.

    `ordering_key` por telefone mantem a ordem das mensagens de um mesmo usuario
    (requer enable_message_ordering na subscription).
    """
    data = json.dumps(msg.model_dump(), ensure_ascii=False).encode("utf-8")
    future = _publisher().publish(_topic_path(), data=data, ordering_key=msg.phone)
    return future.result(timeout=10)
