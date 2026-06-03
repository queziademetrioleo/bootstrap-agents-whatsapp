#!/usr/bin/env python3
"""Pipeline de ingestao do RAG (single-tenant: uma unica base por deploy).

Le um CSV (colunas `Pergunta`, `Resposta`) e faz upsert na knowledge_base.
Estrategia de sincronizacao (zero downtime):

  - linha NOVA            -> gera embedding da Pergunta e insere
  - Resposta ALTERADA     -> atualiza a resposta (Pergunta = chave, embedding mantido)
  - Pergunta ALTERADA     -> conta como nova (embedding regenerado); a antiga vira "removida"
  - linha REMOVIDA do CSV -> deletada do banco

So embeda a Pergunta (busca por similaridade de intencao), nunca a Resposta.

Uso:
    python scripts/ingest.py --csv knowledge/default.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path

from agent import db
from agent.embeddings import embed_batch
from agent.logging_config import get_logger

log = get_logger("ingest")


def _read_csv(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        if "pergunta" not in cols or "resposta" not in cols:
            raise SystemExit("CSV precisa ter as colunas 'Pergunta' e 'Resposta'.")
        rows: list[tuple[str, str]] = []
        for row in reader:
            pergunta = (row[cols["pergunta"]] or "").strip()
            resposta = (row[cols["resposta"]] or "").strip()
            if pergunta and resposta:
                rows.append((pergunta, resposta))
    return rows


async def ingest(csv_path: Path) -> None:
    source_file = csv_path.name
    rows = _read_csv(csv_path)
    log.info("CSV lido", extra={"fields": {"linhas": len(rows)}})

    # Estado atual no banco para ESTE arquivo (sync escopado por source_file —
    # permite dividir o FAQ em varios CSVs sem um apagar o do outro).
    existing = await db.fetch(
        "SELECT pergunta, resposta FROM knowledge_base WHERE source_file = $1", source_file
    )
    existing_map = {r["pergunta"]: r["resposta"] for r in existing}
    csv_perguntas = {p for p, _ in rows}

    to_embed: list[tuple[str, str]] = []  # (pergunta, resposta) novos ou pergunta nova
    to_update_text: list[tuple[str, str]] = []  # (pergunta, resposta) — so resposta mudou

    for pergunta, resposta in rows:
        if pergunta not in existing_map:
            to_embed.append((pergunta, resposta))
        elif existing_map[pergunta] != resposta:
            to_update_text.append((pergunta, resposta))

    to_delete = [p for p in existing_map if p not in csv_perguntas]

    # 1) Embeddings em batch apenas das perguntas novas.
    if to_embed:
        embeddings = embed_batch([p for p, _ in to_embed], task_type="RETRIEVAL_DOCUMENT")
        for (pergunta, resposta), emb in zip(to_embed, embeddings, strict=True):
            await db.execute(
                """INSERT INTO knowledge_base (pergunta, resposta, embedding, source_file)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (pergunta)
                   DO UPDATE SET resposta = EXCLUDED.resposta,
                                 embedding = EXCLUDED.embedding,
                                 source_file = EXCLUDED.source_file""",
                pergunta, resposta, emb, source_file,
            )

    # 2) Atualizacao de texto sem re-embed.
    for pergunta, resposta in to_update_text:
        await db.execute(
            "UPDATE knowledge_base SET resposta = $2 WHERE pergunta = $1",
            pergunta, resposta,
        )

    # 3) Remocoes.
    for pergunta in to_delete:
        await db.execute("DELETE FROM knowledge_base WHERE pergunta = $1", pergunta)

    # ANALYZE atualiza as estatisticas do planner apos mudancas em massa.
    await db.execute("ANALYZE knowledge_base")

    log.info(
        "Ingestao concluida",
        extra={"fields": {
            "novas": len(to_embed),
            "atualizadas": len(to_update_text),
            "removidas": len(to_delete),
        }},
    )
    await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingestao da base de conhecimento (RAG).")
    parser.add_argument("--csv", required=True, help="Caminho do CSV (Pergunta,Resposta)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"Arquivo nao encontrado: {csv_path}")

    asyncio.run(ingest(csv_path))


if __name__ == "__main__":
    main()
