-- Run explicitly before deploying the mobile-compatible backend.
BEGIN;
SELECT pg_advisory_xact_lock(39173001);
CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS auth_sessions (
 id UUID PRIMARY KEY, parent_id BIGINT REFERENCES parents(id) ON DELETE CASCADE,
 password_admin BOOLEAN NOT NULL DEFAULT FALSE, access_hash TEXT UNIQUE NOT NULL,
 refresh_hash TEXT UNIQUE, csrf_token TEXT NOT NULL,
 access_expires_at TIMESTAMPTZ NOT NULL, refresh_expires_at TIMESTAMPTZ NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), revoked_at TIMESTAMPTZ,
 CHECK ((parent_id IS NOT NULL) <> password_admin)
);
CREATE TABLE IF NOT EXISTS used_refresh_tokens (
 token_hash TEXT PRIMARY KEY, session_id UUID NOT NULL REFERENCES auth_sessions(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS web_handoffs (
 code_hash TEXT PRIMARY KEY, session_id UUID NOT NULL REFERENCES auth_sessions(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
ALTER TABLE parents ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE parents ALTER COLUMN line_user_id DROP NOT NULL;
CREATE TABLE IF NOT EXISTS auth_identities (
 parent_id BIGINT NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
 provider TEXT NOT NULL, provider_subject TEXT NOT NULL,
 PRIMARY KEY(provider,provider_subject)
);
INSERT INTO auth_identities(parent_id,provider,provider_subject)
 SELECT id,'line',line_user_id FROM parents WHERE line_user_id IS NOT NULL AND deleted_at IS NULL
 ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS apple_challenges (
 challenge_hash TEXT PRIMARY KEY, nonce TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
ALTER TABLE auth_identities ADD COLUMN IF NOT EXISTS encrypted_refresh_token TEXT;
CREATE TABLE IF NOT EXISTS provider_revocations (
 id BIGSERIAL PRIMARY KEY, encrypted_token TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE attendance ADD COLUMN IF NOT EXISTS updated_by_parent_id BIGINT REFERENCES parents(id) ON DELETE SET NULL;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
CREATE TABLE IF NOT EXISTS audit_logs (
 id BIGSERIAL PRIMARY KEY, parent_id BIGINT REFERENCES parents(id) ON DELETE SET NULL,
 action TEXT NOT NULL, resource_id TEXT NOT NULL, details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS details JSONB NOT NULL DEFAULT '{}'::jsonb;
CREATE TABLE IF NOT EXISTS api_rate_limits (
 bucket TEXT PRIMARY KEY, window_start TIMESTAMPTZ NOT NULL, requests INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS auth_sessions_parent ON auth_sessions(parent_id);
INSERT INTO schema_migrations(version) VALUES ('001_mobile') ON CONFLICT DO NOTHING;
COMMIT;
