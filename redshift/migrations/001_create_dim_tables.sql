-- ============================================================
-- 001_create_dim_tables.sql
-- Dimension tables for the SmartLock star schema.
-- Uses standard PostgreSQL syntax for local development.
-- ============================================================

-- ---------------------------------------------------------
-- dim_lock  (SCD Type 2)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_lock (
    lock_sk          SERIAL       PRIMARY KEY,
    lock_id          VARCHAR(64)  NOT NULL,
    status           VARCHAR(32),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    created_at       TIMESTAMP,
    updated_at       TIMESTAMP,
    effective_from   TIMESTAMP    NOT NULL DEFAULT NOW(),
    effective_to     TIMESTAMP    DEFAULT '9999-12-31 23:59:59',
    is_current       BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_dim_lock_lock_id
    ON dim_lock (lock_id);

CREATE INDEX IF NOT EXISTS idx_dim_lock_current
    ON dim_lock (lock_id, is_current)
    WHERE is_current = TRUE;


-- ---------------------------------------------------------
-- dim_shipment  (SCD Type 2)
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_shipment (
    shipment_sk      SERIAL       PRIMARY KEY,
    shipment_id      VARCHAR(64)  NOT NULL,
    status           VARCHAR(32),
    created_at       TIMESTAMP,
    updated_at       TIMESTAMP,
    effective_from   TIMESTAMP    NOT NULL DEFAULT NOW(),
    effective_to     TIMESTAMP    DEFAULT '9999-12-31 23:59:59',
    is_current       BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_dim_shipment_shipment_id
    ON dim_shipment (shipment_id);

CREATE INDEX IF NOT EXISTS idx_dim_shipment_current
    ON dim_shipment (shipment_id, is_current)
    WHERE is_current = TRUE;


-- ---------------------------------------------------------
-- dim_event_type
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_event_type (
    event_type   VARCHAR(64)  PRIMARY KEY,
    category     VARCHAR(64),
    description  TEXT
);

-- Seed the known event types
INSERT INTO dim_event_type (event_type, category, description)
VALUES
    ('unlock_attempt',     'security',    'An attempt to unlock the device was detected'),
    ('tamper_detected',    'security',    'Physical tampering with the lock was detected'),
    ('battery_low',        'maintenance', 'Battery level dropped below the safe threshold'),
    ('location_deviation', 'logistics',   'Lock moved outside the expected geofence'),
    ('connection_lost',    'connectivity','Lock lost its network connection')
ON CONFLICT (event_type) DO NOTHING;


-- ---------------------------------------------------------
-- dim_date
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_date (
    date_key     INT          PRIMARY KEY,   -- YYYYMMDD
    full_date    DATE         NOT NULL UNIQUE,
    year         SMALLINT     NOT NULL,
    quarter      SMALLINT     NOT NULL,
    month        SMALLINT     NOT NULL,
    day          SMALLINT     NOT NULL,
    day_of_week  SMALLINT     NOT NULL,      -- 0=Sun … 6=Sat (ISO: 1=Mon)
    is_weekend   BOOLEAN      NOT NULL
);

-- Populate dim_date for 2024-01-01 through 2027-12-31
INSERT INTO dim_date (date_key, full_date, year, quarter, month, day, day_of_week, is_weekend)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT                       AS date_key,
    d                                                   AS full_date,
    EXTRACT(YEAR  FROM d)::SMALLINT                    AS year,
    EXTRACT(QUARTER FROM d)::SMALLINT                  AS quarter,
    EXTRACT(MONTH FROM d)::SMALLINT                    AS month,
    EXTRACT(DAY   FROM d)::SMALLINT                    AS day,
    EXTRACT(DOW   FROM d)::SMALLINT                    AS day_of_week,
    EXTRACT(DOW   FROM d) IN (0, 6)                    AS is_weekend
FROM generate_series('2024-01-01'::DATE, '2027-12-31'::DATE, '1 day'::INTERVAL) AS gs(d)
ON CONFLICT (date_key) DO NOTHING;
