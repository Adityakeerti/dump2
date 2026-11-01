-- =====================================================================
-- CitySense V3: Civic Services, Complaints & Escalation Schema (Member C)
-- =====================================================================

CREATE TABLE complaints (
    id                UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    tracking_id       VARCHAR(32)      NOT NULL UNIQUE,
    user_id           UUID             NULL REFERENCES users(id) ON DELETE SET NULL,
    citizen_name      VARCHAR(120),
    title             VARCHAR(255)     NOT NULL,
    description       TEXT             NOT NULL,
    category          VARCHAR(64)      NOT NULL DEFAULT 'CIVIC',
    department        VARCHAR(64)      NOT NULL DEFAULT 'MUNICIPAL',
    priority          VARCHAR(16)      NOT NULL DEFAULT 'MEDIUM' CHECK (priority IN ('LOW','MEDIUM','HIGH','URGENT')),
    status            VARCHAR(24)      NOT NULL DEFAULT 'FILED' CHECK (status IN ('FILED','ASSIGNED','IN_PROGRESS','RESOLVED','REJECTED','ESCALATED')),
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    geom              geography(Point,4326)
                      GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    photo_url         VARCHAR(512),
    escalation_level  INT              NOT NULL DEFAULT 0,
    assigned_worker   VARCHAR(120),
    resolution_notes  TEXT,
    resolved_at       TIMESTAMPTZ,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_complaints_geom             ON complaints USING GIST (geom);
CREATE INDEX idx_complaints_tracking_id      ON complaints (tracking_id);
CREATE INDEX idx_complaints_status_dept      ON complaints (status, department);
CREATE INDEX idx_complaints_created_at       ON complaints (created_at DESC);

CREATE TABLE city_events (
    id          UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(255)     NOT NULL,
    description TEXT,
    category    VARCHAR(64)      NOT NULL DEFAULT 'COMMUNITY',
    severity    VARCHAR(16)      NOT NULL DEFAULT 'INFO' CHECK (severity IN ('INFO','WARNING','ALERT','CRITICAL')),
    latitude    DOUBLE PRECISION NOT NULL,
    longitude   DOUBLE PRECISION NOT NULL,
    geom        geography(Point,4326)
                GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    starts_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    ends_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_city_events_geom ON city_events USING GIST (geom);

CREATE TABLE complaint_escalations (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_id  UUID        NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    from_level    INT         NOT NULL,
    to_level      INT         NOT NULL,
    reason        TEXT        NOT NULL,
    triggered_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_complaint_escalations_complaint_id ON complaint_escalations (complaint_id);
