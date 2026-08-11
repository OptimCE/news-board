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
    email         VARCHAR(256) NOT NULL,
    -- Preferred language, resolved onto every queued email at enqueue time.
    locale        VARCHAR(8)   NULL,
    -- Denormalised onto the queued row as the recipient display name.
    first_name    TEXT         NULL,
    last_name     TEXT         NULL
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

-- Mirrors crm-backend/database_script/2026-08-03_notification_delivery.sql.
-- `core/notifications` writes one outbound_message per emailable recipient and
-- reads notification_preference to decide what is deliverable. Sending and the
-- suppression check belong to the notification-dispatch worker; email_suppression
-- is mirrored here only so the schema stays a faithful copy.
CREATE TABLE IF NOT EXISTS outbound_message (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_notification BIGINT NULL REFERENCES notification(id) ON DELETE SET NULL,
    id_community    INTEGER NULL REFERENCES community(id) ON DELETE CASCADE,
    channel         SMALLINT     NOT NULL CHECK (channel IN (1, 2)),
    recipient       VARCHAR(320) NOT NULL,
    recipient_name  VARCHAR(255) NULL,
    locale          VARCHAR(8)   NOT NULL DEFAULT '',
    type            VARCHAR(128) NOT NULL,
    category        SMALLINT     NOT NULL CHECK (category IN (1, 2)),
    data            JSONB        NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key      VARCHAR(200) NOT NULL,
    status          SMALLINT     NOT NULL DEFAULT 1 CHECK (status IN (1, 2, 3, 4, 5)),
    attempts        SMALLINT     NOT NULL DEFAULT 0,
    last_error      TEXT         NULL,
    scheduled_for   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    claimed_at      TIMESTAMPTZ  NULL,
    sent_at         TIMESTAMPTZ  NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_outbound_message_dedupe
    ON outbound_message (dedupe_key);
CREATE INDEX IF NOT EXISTS ix_outbound_message_due
    ON outbound_message (scheduled_for) WHERE status = 1;
CREATE INDEX IF NOT EXISTS ix_outbound_message_stale
    ON outbound_message (claimed_at) WHERE status = 5;

CREATE TABLE IF NOT EXISTS email_suppression (
    email      VARCHAR(320) PRIMARY KEY,
    reason     SMALLINT     NOT NULL CHECK (reason IN (1, 2, 3, 4)),
    detail     TEXT         NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notification_preference (
    id_user     INTEGER      NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    type_prefix VARCHAR(128) NOT NULL,
    channel     SMALLINT     NOT NULL CHECK (channel IN (1, 2)),
    mode        SMALLINT     NOT NULL CHECK (mode IN (1, 3)),

    PRIMARY KEY (id_user, type_prefix, channel)
);
