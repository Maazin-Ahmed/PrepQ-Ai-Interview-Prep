-- PrepQ Initial Schema Migration
-- Run once against your Supabase PostgreSQL instance
-- Requires: pgvector extension enabled in Supabase dashboard (Database → Extensions → vector)

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'pro')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);

-- ─────────────────────────────────────────────
-- SESSIONS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company     TEXT,
    role        TEXT,
    days_left   INTEGER,
    round       TEXT,
    level       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions (created_at DESC);

-- ─────────────────────────────────────────────
-- MESSAGES
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages (created_at ASC);

-- ─────────────────────────────────────────────
-- PLANS
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tier1           JSONB NOT NULL DEFAULT '[]',
    tier2           JSONB NOT NULL DEFAULT '[]',
    tier3           JSONB NOT NULL DEFAULT '[]',
    daily_breakdown JSONB NOT NULL DEFAULT '[]',
    red_flags       JSONB NOT NULL DEFAULT '[]',
    mock_question   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plans_session_id ON plans (session_id);

-- ─────────────────────────────────────────────
-- COMPANY PATTERNS (pgvector for semantic search)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS company_patterns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company     TEXT NOT NULL,
    role        TEXT NOT NULL,
    source_url  TEXT,
    content     TEXT NOT NULL,
    embedding   vector(1536),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_patterns_company_role
    ON company_patterns (company, role);

-- Approximate nearest-neighbour index (IVFFlat) for semantic search
-- Only create if you have data; otherwise create after first insert batch
-- CREATE INDEX ON company_patterns USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─────────────────────────────────────────────
-- ROW LEVEL SECURITY
-- ─────────────────────────────────────────────
ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages       ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE company_patterns ENABLE ROW LEVEL SECURITY;

-- Users can only read/update their own row
CREATE POLICY "users_self_only"
    ON users FOR ALL
    USING (id = auth.uid());

-- Sessions belong to authenticated owner
CREATE POLICY "sessions_owner_only"
    ON sessions FOR ALL
    USING (user_id = auth.uid());

-- Messages accessible via session ownership
CREATE POLICY "messages_via_session"
    ON messages FOR ALL
    USING (
        session_id IN (
            SELECT id FROM sessions WHERE user_id = auth.uid()
        )
    );

-- Plans accessible via session ownership
CREATE POLICY "plans_via_session"
    ON plans FOR ALL
    USING (
        session_id IN (
            SELECT id FROM sessions WHERE user_id = auth.uid()
        )
    );

-- Company patterns are read-only for authenticated users (backend writes via service key)
CREATE POLICY "company_patterns_read_only"
    ON company_patterns FOR SELECT
    USING (auth.role() = 'authenticated');

-- ─────────────────────────────────────────────
-- UPDATED_AT TRIGGER
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
