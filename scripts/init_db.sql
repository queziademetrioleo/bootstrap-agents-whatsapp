-- =============================================================================
-- Schema do agente — PostgreSQL + PgVector (Cloud SQL)
-- Aplicar uma vez por banco do agente. Idempotente (IF NOT EXISTS).
-- Referencia pgvector: https://github.com/pgvector/pgvector
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ----------------------------------------------------------------- users -----
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    phone       TEXT NOT NULL UNIQUE,
    name        TEXT,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ conversations --
-- Historico longo permanente (analise, auditoria, compactacao de memoria).
CREATE TABLE IF NOT EXISTS conversations (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'agent')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_conversations_user_time
    ON conversations (user_id, created_at DESC);

-- ----------------------------------------------------------- knowledge_base --
-- Base do RAG (single-tenant: uma unica base por deploy/cliente).
-- embedding com 768 dims (text-embedding-004, output_dimensionality=768).
CREATE TABLE IF NOT EXISTS knowledge_base (
    id           BIGSERIAL PRIMARY KEY,
    pergunta     TEXT NOT NULL UNIQUE,
    resposta     TEXT NOT NULL,
    embedding    vector(768) NOT NULL,
    source_file  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Indice de similaridade por cosseno (HNSW). Escolhido em vez de ivfflat porque
-- da boa recall de poucas a muitas linhas — ivfflat com lists alto numa base
-- pequena retorna 0 resultados (listas vazias), quebrando o RAG.
CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON knowledge_base USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------ conversation_state --
-- Estado por conversa (phone) para a cadencia de follow-up.
-- next_followup_at e pre-calculado: o sweep so faz WHERE next_followup_at <= now().
CREATE TABLE IF NOT EXISTS conversation_state (
    phone                TEXT PRIMARY KEY,
    user_id              BIGINT REFERENCES users(id) ON DELETE CASCADE,
    last_interaction_at  TIMESTAMPTZ NOT NULL DEFAULT now(),  -- ultima msg do usuario
    followup_stage       INT NOT NULL DEFAULT 0,              -- proximo stage a enviar
    next_followup_at     TIMESTAMPTZ,                         -- quando disparar (NULL = nada)
    last_followup_at     TIMESTAMPTZ,
    followup_paused      BOOLEAN NOT NULL DEFAULT false,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Indice parcial: o sweep so olha linhas agendadas e nao pausadas.
CREATE INDEX IF NOT EXISTS idx_convstate_due
    ON conversation_state (next_followup_at)
    WHERE next_followup_at IS NOT NULL AND NOT followup_paused;

-- ------------------------------------------------------- processed_messages --
-- Idempotencia: claim atomico de message_id (ON CONFLICT DO NOTHING).
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id   TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Indice para a limpeza periodica por idade (evita crescimento sem fim).
CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_messages (processed_at);

-- Trigger para manter updated_at em knowledge_base.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_kb_updated_at ON knowledge_base;
CREATE TRIGGER trg_kb_updated_at BEFORE UPDATE ON knowledge_base
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- A persona/tools/follow-up do agente NAO ficam no banco — vivem em
-- config/agent.yaml (single-tenant: 1 repo = 1 cliente).
