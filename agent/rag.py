"""RAG — busca automatica na base de conhecimento (PgVector).

A cada mensagem, gera o embedding da query e busca os pares Pergunta/Resposta
mais similares, filtrando por `agent_id` e por score >= threshold (0.75). O
resultado e injetado no system prompt — o modelo nao precisa chamar tool.

Distancia cosseno via pgvector: `embedding <=> query`. score = 1 - distancia.
"""

from __future__ import annotations

from agent import db
from agent.config import get_settings
from agent.embeddings import embed_text
from agent.logging_config import get_logger
from agent.models import RagHit

log = get_logger(__name__)

# Ver scripts/init_db.sql — score = 1 - (embedding <=> query) (cosine similarity)
_SEARCH_SQL = """
SELECT pergunta, resposta, 1 - (embedding <=> $1::vector) AS score
FROM knowledge_base
WHERE agent_id = $2
  AND 1 - (embedding <=> $1::vector) >= $3
ORDER BY embedding <=> $1::vector
LIMIT $4;
"""


async def retrieve(query: str, agent_id: str) -> list[RagHit]:
    """Retorna ate `rag_top_k` pares acima do threshold de similaridade."""
    s = get_settings()
    query_emb = embed_text(query, task_type="RETRIEVAL_QUERY")
    rows = await db.fetch(
        _SEARCH_SQL,
        query_emb,
        agent_id,
        s.rag_score_threshold,
        s.rag_top_k,
    )
    hits = [RagHit(pergunta=r["pergunta"], resposta=r["resposta"], score=float(r["score"])) for r in rows]
    log.info(
        "RAG retrieve",
        extra={"fields": {"agent_id": agent_id, "hits": len(hits), "query_len": len(query)}},
    )
    return hits


def format_context(hits: list[RagHit]) -> str:
    """Formata os hits para injecao no system prompt. Vazio se nao houver hits."""
    if not hits:
        return ""
    blocks = [
        "## Base de conhecimento (use quando relevante; nao invente alem disto)",
    ]
    for i, h in enumerate(hits, 1):
        blocks.append(f"{i}. P: {h.pergunta}\n   R: {h.resposta}")
    return "\n".join(blocks)
