-- Test-only DDL for the CRM tables this service reads and writes.
--
-- The real CRM schema is owned by crm-backend. Tests run against a single
-- Postgres instance, so we mirror only the minimum CRM DDL the suite needs:
-- community + community_subscription (auth + activation), app_user (author/voter
-- email resolution), audit_log (write trail), community_user (the membership
-- roster a published post/poll notifies), and notification (the fan-out target).
--
-- Mirrors core/database/models.py and shared/models/crm_models.py.

CREATE TABLE IF NOT EXISTS community (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name              VARCHAR(255) NOT NULL UNIQUE,
    auth_community_id VARCHAR(255) NOT NULL UNIQUE,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS community_subscription (
    id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_community INTEGER     NOT NULL,
    feature      VARCHAR(64) NOT NULL,
    is_active    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_community_subscription_community_feature
        UNIQUE (id_community, feature)
);

CREATE INDEX IF NOT EXISTS idx_community_subscription_id_community
    ON community_subscription (id_community);


-- Mirrors shared/models/crm_models.py::AppUserModel. Only the columns the news
-- service reads — auth_user_id -> (id, email) — are present.
CREATE TABLE IF NOT EXISTS app_user (
    id            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    auth_user_id  VARCHAR(255) NOT NULL UNIQUE,
    email         VARCHAR(256) NOT NULL
);


-- Mirrors core/database/models.py::AuditLogModel and the production DDL in
-- crm-backend. Append-only by convention.
CREATE TABLE IF NOT EXISTS audit_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_community INTEGER REFERENCES community(id) ON DELETE CASCADE,
    timestamp    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    action       VARCHAR(128) NOT NULL,
    source       VARCHAR(32)  NOT NULL,
    entity_type  VARCHAR(64)  NOT NULL,
    entity_id    VARCHAR(64),
    user_id      INTEGER,
    user_email   VARCHAR(256),
    payload      JSONB        NOT NULL DEFAULT '{}'::jsonb
);


-- Mirrors crm-backend's community_user join table. Read by the News service to
-- resolve a community's membership when fanning out a "published" notification.
CREATE TABLE IF NOT EXISTS community_user (
    id_community INTEGER REFERENCES community(id) ON DELETE CASCADE,
    id_user      INTEGER REFERENCES app_user(id) ON DELETE CASCADE,
    role         VARCHAR(50) NOT NULL,
    PRIMARY KEY (id_community, id_user)
);


-- Mirrors crm-backend's notification table (the production DDL). The News
-- service only INSERTs one row per recipient; reads are served by crm-backend.
CREATE TABLE IF NOT EXISTS notification (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_community INTEGER REFERENCES community(id) ON DELETE CASCADE,
    id_user      INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    type         VARCHAR(128) NOT NULL,
    data         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    read_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
