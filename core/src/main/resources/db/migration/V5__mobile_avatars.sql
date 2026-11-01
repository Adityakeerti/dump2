-- =====================================================================
-- CitySense V5: mobile app support
--   * email OTPs (4-digit) for account verification and password reset
--   * city service "avatars" shown on the Explore map
--   * per-user saved/liked avatars
-- Avatar rows are seeded by AvatarSeeder from a JSON resource (SEED_AVATARS),
-- not here, so the schema stays data-free.
-- =====================================================================

ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT false;
-- Accounts that existed before verification was introduced keep working.
UPDATE users SET email_verified = true;

CREATE TABLE email_otps (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose     VARCHAR(16) NOT NULL CHECK (purpose IN ('VERIFY_EMAIL','RESET_PASSWORD')),
    code_hash   VARCHAR(255) NOT NULL,          -- BCrypt; the plain code is never stored
    attempts    INT         NOT NULL DEFAULT 0,
    expires_at  TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_email_otps_user_purpose ON email_otps (user_id, purpose, created_at DESC);

CREATE TABLE avatars (
    id            UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    handle        VARCHAR(64)      NOT NULL UNIQUE,
    name          VARCHAR(120)     NOT NULL,
    title         VARCHAR(160)     NOT NULL,           -- e.g. "Paltan Bazaar guide"
    category      VARCHAR(32)      NOT NULL,
    persona       VARCHAR(32)      NOT NULL CHECK (persona IN ('CIVIC','TRAFFIC','EMERGENCY','TRANSIT')),
    intro         TEXT             NOT NULL,
    pricing       TEXT,
    website_url   VARCHAR(512),
    instagram_url VARCHAR(512),
    threads_url   VARCHAR(512),
    x_url         VARCHAR(512),
    pin_image     VARCHAR(255)     NOT NULL,           -- path under core's /avatars/ static folder
    hero_image    VARCHAR(255)     NOT NULL,
    rating        NUMERIC(3,2)     NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    review_count  INT              NOT NULL DEFAULT 0,
    latitude      DOUBLE PRECISION NOT NULL,
    longitude     DOUBLE PRECISION NOT NULL,
    geom          geography(Point,4326)
                  GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography) STORED,
    active        BOOLEAN          NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX idx_avatars_geom ON avatars USING GIST (geom);

CREATE TABLE avatar_saves (
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    avatar_id  UUID        NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, avatar_id)
);

CREATE TABLE avatar_likes (
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    avatar_id  UUID        NOT NULL REFERENCES avatars(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, avatar_id)
);
