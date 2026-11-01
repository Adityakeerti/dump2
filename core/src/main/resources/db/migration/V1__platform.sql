-- =====================================================================
-- CitySense V1: core platform schema (public schema)
-- Requires PostGIS + pgvector (see db/Dockerfile).
-- JPA entities in core are mapped against this exact schema; do not
-- rename/add/remove columns here -- add a new V<n>__*.sql migration.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

CREATE SCHEMA IF NOT EXISTS ai;   -- reserved for Member B RAG tables

-- ---------------------------------------------------------------------
-- users: platform accounts (seeded by the Java side at startup)
-- ---------------------------------------------------------------------
CREATE TABLE users (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    full_name      VARCHAR(120) NOT NULL,
    role           VARCHAR(20)  NOT NULL CHECK (role IN ('CITIZEN','ADMIN','CREW')),
    language       VARCHAR(8)   NOT NULL DEFAULT 'en',
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------
-- incidents: correlated clusters of observations
-- geom is derived from latitude/longitude; never write it directly.
-- ---------------------------------------------------------------------
CREATE TABLE incidents (
    id                 UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    type               VARCHAR(32)      NOT NULL,
    title              VARCHAR(200)     NOT NULL,
    summary            TEXT,
    severity           INT              NOT NULL CHECK (severity BETWEEN 1 AND 5),
    urgency_score      DOUBLE PRECISION NOT NULL DEFAULT 0,
    latitude           DOUBLE PRECISION NOT NULL,
    longitude          DOUBLE PRECISION NOT NULL,
    geom               geography(Point,4326)
                       GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    status             VARCHAR(20)      NOT NULL DEFAULT 'OPEN'
                       CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
    observation_count  INT              NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_incidents_geom              ON incidents USING GIST (geom);
CREATE INDEX idx_incidents_status_updated_at ON incidents (status, updated_at DESC);

-- ---------------------------------------------------------------------
-- observations: raw signals from sensors, citizens, agents, simulators
-- ---------------------------------------------------------------------
CREATE TABLE observations (
    id           UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    type         VARCHAR(32)      NOT NULL
                 CHECK (type IN ('cv_density','complaint','flood','crash','event','agent_finding','rain','congestion')),
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    geom         geography(Point,4326)
                 GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    observed_at  TIMESTAMPTZ      NOT NULL,
    source       VARCHAR(64)      NOT NULL,
    confidence   DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    status       VARCHAR(20)      NOT NULL DEFAULT 'UNVERIFIED'
                 CHECK (status IN ('UNVERIFIED','VERIFIED','SIMULATED','PREDICTED','STALE')),
    payload      JSONB            NOT NULL DEFAULT '{}'::jsonb,
    incident_id  UUID             NULL REFERENCES incidents(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_observations_geom        ON observations USING GIST (geom);
CREATE INDEX idx_observations_observed_at ON observations (observed_at DESC);
CREATE INDEX idx_observations_incident_id ON observations (incident_id);
CREATE INDEX idx_observations_type        ON observations (type);

-- ---------------------------------------------------------------------
-- agent_actions: actions proposed by agents; human-in-the-loop approval
-- version is the JPA @Version optimistic-lock column.
-- ---------------------------------------------------------------------
CREATE TABLE agent_actions (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id      UUID        NULL REFERENCES incidents(id) ON DELETE SET NULL,
    agent            VARCHAR(64) NOT NULL,
    action_type      VARCHAR(40) NOT NULL
                     CHECK (action_type IN ('NOTIFY_CITIZENS','SIGNAL_OVERRIDE','ROAD_CLOSURE','DISPATCH','EVACUATION','GREEN_CORRIDOR')),
    summary          TEXT,
    payload          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    risk_level       VARCHAR(10) NOT NULL CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
    approval_status  VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                     CHECK (approval_status IN ('PENDING','APPROVED','REJECTED','AUTO_EXECUTED')),
    decided_by       UUID        NULL REFERENCES users(id),
    decided_at       TIMESTAMPTZ NULL,
    decision_reason  TEXT        NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    version          BIGINT      NOT NULL DEFAULT 0
);

CREATE INDEX idx_agent_actions_status_created_at ON agent_actions (approval_status, created_at DESC);
CREATE INDEX idx_agent_actions_incident_id       ON agent_actions (incident_id);

-- ---------------------------------------------------------------------
-- audit_log: append-only record of every security-relevant decision
-- ---------------------------------------------------------------------
CREATE TABLE audit_log (
    id           BIGSERIAL    PRIMARY KEY,
    actor        VARCHAR(255) NOT NULL,
    action       VARCHAR(64)  NOT NULL,
    entity_type  VARCHAR(40),
    entity_id    VARCHAR(64),
    outcome      VARCHAR(20)  NOT NULL,
    evidence     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_created_at ON audit_log (created_at DESC);
CREATE INDEX idx_audit_log_entity     ON audit_log (entity_type, entity_id);

-- Enforce append-only semantics at the database level.
CREATE OR REPLACE FUNCTION audit_log_block_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$;

CREATE TRIGGER audit_log_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_block_mutation();

CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_block_mutation();
