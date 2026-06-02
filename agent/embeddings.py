"""Geracao de embeddings via Vertex AI (`text-embedding-004`, 768 dims).

Usado tanto na ingestao (embedding da Pergunta) quanto em runtime (embedding da
mensagem do usuario). Mesmo modelo nos dois lados — coerencia do espaco vetorial.
"""

from __future__ import annotations

from google.genai import types

from agent.config import get_settings
from agent.genai_client import get_client


def embed_text(text: str, *, task_type: str = "RETRIEVAL_QUERY") -> list[float]:
    """Gera o embedding de um unico texto.

    task_type:
      - "RETRIEVAL_QUERY"    -> embedding da mensagem do usuario (busca)
      - "RETRIEVAL_DOCUMENT" -> embedding da Pergunta na ingestao
    """
    s = get_settings()
    resp = get_client().models.embed_content(
        model=s.embedding_model,
        contents=text,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=s.embedding_dim,
        ),
    )
    return list(resp.embeddings[0].values)


def embed_batch(texts: list[str], *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Gera embeddings para varios textos numa unica chamada."""
    if not texts:
        return []
    s = get_settings()
    resp = get_client().models.embed_content(
        model=s.embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=s.embedding_dim,
        ),
    )
    return [list(e.values) for e in resp.embeddings]
