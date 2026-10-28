CREATE TABLE IF NOT EXISTS calls (
    call_id VARCHAR(36) PRIMARY KEY,
    api_key_hash VARCHAR(64) NOT NULL,
    caller VARCHAR(100) NOT NULL,
    callee VARCHAR(100) NOT NULL,
    state VARCHAR(20) NOT NULL,
    metadata JSONB,
    recording_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_calls_api_key_hash ON calls(api_key_hash);
CREATE INDEX IF NOT EXISTS ix_calls_state ON calls(state);

CREATE TABLE IF NOT EXISTS api_key_configs (
    api_key_hash VARCHAR(64) PRIMARY KEY,
    concurrent_limit INTEGER NOT NULL DEFAULT 3,
    cps_limit INTEGER NOT NULL DEFAULT 2
);
