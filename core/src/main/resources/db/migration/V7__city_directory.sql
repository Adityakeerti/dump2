-- =====================================================================
-- CitySense V7: city directory for the Townhall feed and every agent
--   * businesses: popular local businesses that agents can recommend
--   * city_events: venue / organizer / source for real-world events
-- Rows are seeded by CityDirectorySeeder from JSON resources (seed/businesses.json,
-- seed/events.json) keyed by seed_key, so the schema stays data-free and
-- re-seeding updates rows instead of duplicating them.
-- =====================================================================

CREATE TABLE businesses (
    id                UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    seed_key          VARCHAR(80)      UNIQUE,                 -- stable id for seeded rows
    name              VARCHAR(160)     NOT NULL,
    category          VARCHAR(48)      NOT NULL,               -- cafe, bakery, restaurant, sweets, bookstore, shopping…
    locality          VARCHAR(120)     NOT NULL,               -- e.g. "Clement Town / Bell Road"
    description       TEXT             NOT NULL,
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    geom              geography(Point,4326)
                      GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    coords_precision  VARCHAR(16)      NOT NULL DEFAULT 'approximate' CHECK (coords_precision IN ('exact','approximate')),
    source_url        TEXT,                                    -- where the listing was verified
    featured          BOOLEAN          NOT NULL DEFAULT true,
    active            BOOLEAN          NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX idx_businesses_geom ON businesses USING GIST (geom);
CREATE INDEX idx_businesses_locality ON businesses (locality);
CREATE INDEX idx_businesses_category ON businesses (category);

ALTER TABLE city_events
    ADD COLUMN venue       VARCHAR(200),
    ADD COLUMN organizer   VARCHAR(200),
    ADD COLUMN source_url  TEXT,
    ADD COLUMN seed_key    VARCHAR(80) UNIQUE;
CREATE INDEX idx_city_events_starts_at ON city_events (starts_at);
