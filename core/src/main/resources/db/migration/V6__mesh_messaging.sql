-- =====================================================================
-- CitySense V5: Offline Mesh Messaging Schema (Knit-compatible zero-internet mesh)
-- =====================================================================

CREATE TABLE mesh_messages (
    id              VARCHAR(64) PRIMARY KEY,
    type            VARCHAR(32) NOT NULL,
    sender_id       VARCHAR(64) NOT NULL,
    recipient_id    VARCHAR(64),
    group_id        VARCHAR(64),
    payload_json    TEXT NOT NULL,
    wire_signature  VARCHAR(128) NOT NULL,
    hops            INT NOT NULL DEFAULT 0,
    ttl             INT NOT NULL DEFAULT 8,
    is_relayed      BOOLEAN NOT NULL DEFAULT TRUE,
    sent_at         TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mesh_messages_sent_at ON mesh_messages (sent_at DESC);
CREATE INDEX idx_mesh_messages_type ON mesh_messages (type);
CREATE INDEX idx_mesh_messages_sender ON mesh_messages (sender_id);
CREATE INDEX idx_mesh_messages_recipient ON mesh_messages (recipient_id);

CREATE TABLE mesh_peers (
    node_id         VARCHAR(64) PRIMARY KEY,
    display_name    VARCHAR(120) NOT NULL,
    role            VARCHAR(32) NOT NULL,
    hops            INT NOT NULL DEFAULT 1,
    capabilities    VARCHAR(255),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mesh_peers_last_seen ON mesh_peers (last_seen_at DESC);
