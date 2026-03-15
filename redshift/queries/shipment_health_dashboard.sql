-- ============================================================
-- shipment_health_dashboard.sql
--
-- Dashboard query: current health status of every shipment.
-- Uses the mv_shipment_health materialized view for speed;
-- falls back to a live join when the view is not yet refreshed.
-- ============================================================

-- ---- Option A: Fast path — read the materialized view ------
SELECT
    shipment_id,
    shipment_status,
    active_locks,
    total_security_events,
    critical_events,
    high_events,
    health_score,
    last_security_event,
    last_location_update,
    CASE
        WHEN health_score >= 80 THEN 'HEALTHY'
        WHEN health_score >= 50 THEN 'WARNING'
        ELSE                         'CRITICAL'
    END AS health_label
FROM
    mv_shipment_health
ORDER BY
    health_score ASC,        -- worst first
    critical_events DESC;


-- ---- Option B: Live query (slower, always up-to-date) ------
/*
SELECT
    ds.shipment_id,
    ds.status                                          AS shipment_status,
    COUNT(DISTINCT flsc.lock_id)                       AS active_locks,
    COUNT(fse.event_id)                                AS total_security_events,
    SUM(CASE WHEN fse.severity = 'critical' THEN 1
             ELSE 0 END)                               AS critical_events,
    SUM(CASE WHEN fse.severity = 'high' THEN 1
             ELSE 0 END)                               AS high_events,
    GREATEST(
        0,
        100
        - SUM(CASE WHEN fse.severity = 'critical' THEN 25
                   WHEN fse.severity = 'high'     THEN 10
                   WHEN fse.severity = 'medium'   THEN 3
                   ELSE 1 END)
    )                                                  AS health_score,
    MAX(fse.event_time)                                AS last_security_event,
    MAX(flu.update_time)                               AS last_location_update
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
    ds.status
ORDER BY
    health_score ASC,
    critical_events DESC;
*/


-- ---- Per-shipment detail: recent events for a given shipment
-- Replace :shipment_id with the desired value.
/*
SELECT
    fse.event_id,
    fse.lock_id,
    fse.event_type,
    det.category,
    fse.severity,
    fse.event_time,
    flu.latitude,
    flu.longitude
FROM
    fact_security_events fse
    JOIN dim_event_type det ON fse.event_type = det.event_type
    JOIN fact_lock_status_changes flsc
        ON fse.lock_id = flsc.lock_id
        AND flsc.shipment_id = :shipment_id
    LEFT JOIN fact_location_updates flu
        ON flu.lock_id = fse.lock_id
        AND flu.update_time = (
            SELECT MAX(flu2.update_time)
            FROM fact_location_updates flu2
            WHERE flu2.lock_id = fse.lock_id
              AND flu2.update_time <= fse.event_time
        )
ORDER BY
    fse.event_time DESC
LIMIT 100;
*/
