CREATE TABLE IF NOT EXISTS chat_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    message_count INTEGER NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('active', 'archived'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    mode TEXT,
    answer_structured JSONB,
    sources JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    search_document tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, ''))
    ) STORED,
    CHECK (role IN ('user', 'assistant', 'system', 'tool'))
);

CREATE TABLE IF NOT EXISTS chat_memory_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repo_id UUID REFERENCES repositories(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES chat_conversations(id) ON DELETE CASCADE,
    source_message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    memory_scope TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.500,
    source_payload JSONB,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    search_document tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(kind, '') || ' ' || coalesce(key, '') || ' ' || coalesce(value, ''))
    ) STORED,
    CHECK (memory_scope IN ('user', 'repo', 'conversation'))
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_repo_last
    ON chat_conversations(user_id, repo_id, COALESCE(last_message_at, created_at) DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages(conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_repo_created
    ON chat_messages(user_id, repo_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_search
    ON chat_messages USING GIN (search_document);
CREATE INDEX IF NOT EXISTS idx_chat_memory_items_user_repo
    ON chat_memory_items(user_id, repo_id, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_memory_items_scope_kind
    ON chat_memory_items(memory_scope, kind, last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_memory_items_search
    ON chat_memory_items USING GIN (search_document);
