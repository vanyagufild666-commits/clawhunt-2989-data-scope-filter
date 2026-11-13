-- 0001_probe_records.sql — test-only table (PostgreSQL 16 baseline)
-- probe_records exists ONLY in the test database; production schemas are owned
-- by their feature tickets (platform convention: id/org_id/site_id/created_at...).

CREATE TABLE IF NOT EXISTS probe_records (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,
    site_id    UUID NOT NULL,
    owner_id   UUID NOT NULL,
    title      VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_probe_org   ON probe_records (org_id);
CREATE INDEX IF NOT EXISTS ix_probe_site  ON probe_records (site_id);
CREATE INDEX IF NOT EXISTS ix_probe_owner ON probe_records (owner_id);
