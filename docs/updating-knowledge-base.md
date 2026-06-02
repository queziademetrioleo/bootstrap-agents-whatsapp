# Como adicionar ou atualizar a base de conhecimento (RAG)

A base de conhecimento é um **CSV** com duas colunas: `Pergunta` e `Resposta`.
Você edita o CSV — sem precisar entender embeddings ou banco de dados.

## Formato

`knowledge/<agente>.csv`:

```csv
Pergunta,Resposta
Quais os horarios de atendimento?,"Funcionamos de seg a sex, 8h-18h."
Como rastreio meu pedido?,"Me informe o numero do pedido que eu consulto."
```

- Uma linha = um par completo.
- Use aspas duplas para respostas com vírgulas/quebras.
- A **busca é por similaridade da Pergunta** (intenção), então escreva as perguntas
  como o usuário realmente perguntaria.

## Ingerir / atualizar

Sempre que editar o CSV, rode o `ingest.py`:

```bash
python scripts/ingest.py --csv knowledge/acme.csv --agent-id acme
# ou: make ingest CSV=knowledge/acme.csv AGENT=acme
```

O script sincroniza de forma inteligente (zero downtime — o agente continua
respondendo durante a ingestão):

| Mudança no CSV | O que acontece |
|---|---|
| linha nova | gera embedding da Pergunta e insere |
| Resposta alterada | atualiza o texto (sem re-embedar) |
| Pergunta alterada | trata como nova (re-embeda) |
| linha removida | deleta do banco |

## Como o RAG funciona em runtime

A cada mensagem, o sistema:
1. gera o embedding da mensagem do usuário (`text-embedding-004`, 768 dims);
2. busca no PgVector os pares mais próximos do `agent_id`;
3. retorna até **5** resultados com **score ≥ 0.75** (cosine similarity);
4. injeta as respostas encontradas no system prompt — **sem** o modelo precisar
   chamar tool.

Se nada passar do threshold, nenhum contexto é injetado e o agente responde só com
o system prompt. Ajuste o threshold/top-k em `RAG_SCORE_THRESHOLD` / `RAG_TOP_K`.

## Múltiplos agentes

Cada agente tem `agent_id` próprio → bases isoladas no mesmo banco. Um CSV por
agente: `knowledge/acme.csv` (`--agent-id acme`), `knowledge/loja2.csv`
(`--agent-id loja2`), etc.

## Dica de performance

Após uma ingestão grande, vale recriar o índice ivfflat (já criado em
`init_db.sql`). Para bases muito grandes, considere aumentar `lists`.
