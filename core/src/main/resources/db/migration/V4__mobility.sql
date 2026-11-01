-- =====================================================================
-- CitySense V4: Intelligent Mobility & Emergency Routing Schema (Member D)
-- =====================================================================

CREATE TABLE route_plans (
    id                      UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    mission_id              VARCHAR(64)      NOT NULL,
    emergency_type          VARCHAR(32)      NOT NULL DEFAULT 'ACCIDENT',
    origin_node             VARCHAR(64)      NOT NULL,
    destination_node        VARCHAR(64)      NOT NULL,
    selected_path           JSONB            NOT NULL DEFAULT '{}'::jsonb,
    nominal_time_minutes    DOUBLE PRECISION NOT NULL,
    effective_time_minutes  DOUBLE PRECISION NOT NULL,
    rerouted                BOOLEAN          NOT NULL DEFAULT FALSE,
    weather_rerouted        BOOLEAN          NOT NULL DEFAULT FALSE,
    status                  VARCHAR(24)      NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED')),
    created_at              TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_route_plans_mission_id ON route_plans (mission_id);
CREATE INDEX idx_route_plans_created_at ON route_plans (created_at DESC);

CREATE TABLE weather_observations (
    id                UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    city              VARCHAR(64)      NOT NULL DEFAULT 'Dehradun',
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    geom              geography(Point,4326)
                      GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    temperature_c     DOUBLE PRECISION NOT NULL,
    relative_humidity DOUBLE PRECISION NOT NULL DEFAULT 60.0,
    precipitation_mm  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    rain_mm           DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    flood_depth_cm    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    risk_level        VARCHAR(16)      NOT NULL DEFAULT 'NORMAL' CHECK (risk_level IN ('NORMAL','MODERATE','HIGH','CRITICAL')),
    condition_text    VARCHAR(128)     NOT NULL DEFAULT 'Clear Sky',
    source            VARCHAR(64)      NOT NULL DEFAULT 'Open-Meteo Free API',
    observed_at       TIMESTAMPTZ      NOT NULL,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_weather_observations_geom ON weather_observations USING GIST (geom);
CREATE INDEX idx_weather_observations_city ON weather_observations (city, observed_at DESC);

CREATE TABLE traffic_junctions (
    id                     UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    junction_id            VARCHAR(64)      NOT NULL UNIQUE,
    name                   VARCHAR(128)     NOT NULL,
    latitude               DOUBLE PRECISION NOT NULL,
    longitude              DOUBLE PRECISION NOT NULL,
    current_mode           VARCHAR(32)      NOT NULL DEFAULT 'ADAPTIVE_RL' CHECK (current_mode IN ('FIXED_TIME','ADAPTIVE_RL','GREEN_CORRIDOR','MANUAL')),
    green_corridor_active  BOOLEAN          NOT NULL DEFAULT FALSE,
    congestion_level       DOUBLE PRECISION NOT NULL DEFAULT 0.0 CHECK (congestion_level BETWEEN 0 AND 1),
    updated_at             TIMESTAMPTZ      NOT NULL DEFAULT now()
);

CREATE INDEX idx_traffic_junctions_junction_id ON traffic_junctions (junction_id);
