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
python scripts/ingest.py --csv knowledge/default.csv
# ou: make ingest CSV=knowledge/default.csv
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
2. busca no PgVector os pares mais próximos na base de conhecimento;
3. retorna até **5** resultados com **score ≥ 0.75** (cosine similarity);
4. injeta as respostas encontradas no system prompt — **sem** o modelo precisar
   chamar tool.

Se nada passar do threshold, nenhum contexto é injetado e o agente responde só com
o system prompt. Ajuste o threshold/top-k em `RAG_SCORE_THRESHOLD` / `RAG_TOP_K`.

## Vários CSVs

Como é single-tenant (uma base por cliente), você pode dividir o FAQ em vários
arquivos e ingerir cada um — todos caem na mesma base. A sincronização é por
`source_file`, então rodar `ingest.py` para um CSV não apaga o que veio de outro.

## Índice de similaridade

O `init_db.sql` cria um índice **HNSW** sobre a coluna `embedding`. Ele foi
escolhido em vez do ivfflat porque mantém boa recall tanto em bases pequenas
quanto grandes — o ivfflat com `lists` alto numa base pequena pode retornar zero
resultados (listas vazias) e quebrar o RAG silenciosamente. O HNSW não exige
ajuste de `lists`/`probes` e funciona bem desde as primeiras linhas.
