-- ============================================================
-- 002_create_fact_tables.sql
-- Fact tables for the SmartLock star schema.
-- Uses standard PostgreSQL syntax for local development.
-- ============================================================

-- ---------------------------------------------------------
-- fact_security_events
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_security_events (
    event_id     VARCHAR(64)        PRIMARY KEY,
    lock_id      VARCHAR(64)        NOT NULL,
    event_type   VARCHAR(64)        NOT NULL,
    severity     VARCHAR(32)        NOT NULL,
    event_time   TIMESTAMP          NOT NULL,
    date_key     INT                NOT NULL,

    CONSTRAINT fk_fse_date
        FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    CONSTRAINT fk_fse_event_type
        FOREIGN KEY (event_type) REFERENCES dim_event_type (event_type)
);

CREATE INDEX IF NOT EXISTS idx_fse_lock_id
    ON fact_security_events (lock_id);

CREATE INDEX IF NOT EXISTS idx_fse_event_time
    ON fact_security_events (event_time);

CREATE INDEX IF NOT EXISTS idx_fse_date_key
    ON fact_security_events (date_key);

CREATE INDEX IF NOT EXISTS idx_fse_severity
    ON fact_security_events (severity);


-- ---------------------------------------------------------
-- fact_lock_status_changes
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_lock_status_changes (
    id               SERIAL            PRIMARY KEY,
    lock_id          VARCHAR(64)       NOT NULL,
    action           VARCHAR(32)       NOT NULL,
    status           VARCHAR(32),
    previous_status  VARCHAR(32),
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    shipment_id      VARCHAR(64),
    change_time      TIMESTAMP         NOT NULL,
    date_key         INT               NOT NULL,

    CONSTRAINT fk_flsc_date
        FOREIGN KEY (date_key) REFERENCES dim_date (date_key)
);

CREATE INDEX IF NOT EXISTS idx_flsc_lock_id
    ON fact_lock_status_changes (lock_id);

CREATE INDEX IF NOT EXISTS idx_flsc_change_time
    ON fact_lock_status_changes (change_time);

CREATE INDEX IF NOT EXISTS idx_flsc_date_key
    ON fact_lock_status_changes (date_key);

CREATE INDEX IF NOT EXISTS idx_flsc_shipment_id
    ON fact_lock_status_changes (shipment_id);


-- ---------------------------------------------------------
-- fact_location_updates
-- ---------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_location_updates (
    id            SERIAL             PRIMARY KEY,
    lock_id       VARCHAR(64)        NOT NULL,
    latitude      DOUBLE PRECISION   NOT NULL,
    longitude     DOUBLE PRECISION   NOT NULL,
    update_time   TIMESTAMP          NOT NULL,
    date_key      INT                NOT NULL,

    CONSTRAINT fk_flu_date
        FOREIGN KEY (date_key) REFERENCES dim_date (date_key)
);

CREATE INDEX IF NOT EXISTS idx_flu_lock_id
    ON fact_location_updates (lock_id);

CREATE INDEX IF NOT EXISTS idx_flu_update_time
    ON fact_location_updates (update_time);

CREATE INDEX IF NOT EXISTS idx_flu_date_key
    ON fact_location_updates (date_key);
