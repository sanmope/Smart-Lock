-- ============================================================
-- 003_create_materialized_views.sql
-- Materialized views for the SmartLock data warehouse.
-- ============================================================

-- ---------------------------------------------------------
-- mv_shipment_health
--
-- Joins fact tables with dimensions to show the current
-- health status of each shipment at a glance.
-- ---------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_shipment_health AS
SELECT
    ds.shipment_id,
    ds.status                                          AS shipment_status,
    COUNT(DISTINCT flsc.lock_id)                       AS active_locks,
    COUNT(fse.event_id)                                AS total_security_events,
    SUM(CASE WHEN fse.severity = 'critical' THEN 1
             ELSE 0 END)                               AS critical_events,
    SUM(CASE WHEN fse.severity = 'high' THEN 1
             ELSE 0 END)                               AS high_events,
    MAX(fse.event_time)                                AS last_security_event,
    MAX(flu.update_time)                               AS last_location_update,
    -- Health score: 100 minus penalty points for severity
    GREATEST(
        0,
        100
        - SUM(CASE WHEN fse.severity = 'critical' THEN 25
                   WHEN fse.severity = 'high'     THEN 10
                   WHEN fse.severity = 'medium'   THEN 3
                   ELSE 1 END)
    )                                                  AS health_score
FROM
    dim_shipment ds
    LEFT JOIN fact_lock_status_changes flsc
        ON flsc.shipment_id = ds.shipment_id
    LEFT JOIN fact_security_events fse
        ON fse.lock_id = flsc.lock_id
    LEFT JOIN fact_location_updates flu
        ON flu.lock_id = flsc.lock_id
WHERE
    ds.is_current = TRUE
GROUP BY
    ds.shipment_id,
    ds.status;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_shipment_health_pk
    ON mv_shipment_health (shipment_id);


-- ---------------------------------------------------------
-- mv_hourly_event_trend
--
-- Hourly counts of security events by type and severity.
-- ---------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_hourly_event_trend AS
SELECT
    DATE_TRUNC('hour', fse.event_time)   AS event_hour,
    dd.full_date                          AS event_date,
    fse.event_type,
    det.category                          AS event_category,
    fse.severity,
    COUNT(*)                              AS event_count
FROM
    fact_security_events fse
    JOIN dim_date dd
        ON fse.date_key = dd.date_key
    JOIN dim_event_type det
        ON fse.event_type = det.event_type
GROUP BY
    DATE_TRUNC('hour', fse.event_time),
    dd.full_date,
    fse.event_type,
    det.category,
    fse.severity;

CREATE INDEX IF NOT EXISTS idx_mv_hourly_event_trend_hour
    ON mv_hourly_event_trend (event_hour);

CREATE INDEX IF NOT EXISTS idx_mv_hourly_event_trend_type
    ON mv_hourly_event_trend (event_type, severity);
