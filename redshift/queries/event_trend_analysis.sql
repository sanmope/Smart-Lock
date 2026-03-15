-- ============================================================
-- event_trend_analysis.sql
--
-- Queries for analysing security-event trends over time.
-- ============================================================

-- ---------------------------------------------------------
-- 1. Hourly trend — last 24 hours
-- ---------------------------------------------------------
SELECT
    event_hour,
    event_type,
    event_category,
    severity,
    event_count
FROM
    mv_hourly_event_trend
WHERE
    event_hour >= NOW() - INTERVAL '24 hours'
ORDER BY
    event_hour DESC,
    event_count DESC;


-- ---------------------------------------------------------
-- 2. Daily totals — last 30 days, by severity
-- ---------------------------------------------------------
SELECT
    dd.full_date,
    fse.severity,
    COUNT(*)                          AS event_count
FROM
    fact_security_events fse
    JOIN dim_date dd ON fse.date_key = dd.date_key
WHERE
    dd.full_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY
    dd.full_date,
    fse.severity
ORDER BY
    dd.full_date DESC,
    fse.severity;


-- ---------------------------------------------------------
-- 3. Top event types — last 7 days
-- ---------------------------------------------------------
SELECT
    fse.event_type,
    det.category,
    fse.severity,
    COUNT(*)                          AS event_count,
    COUNT(DISTINCT fse.lock_id)       AS affected_locks
FROM
    fact_security_events fse
    JOIN dim_event_type det ON fse.event_type = det.event_type
WHERE
    fse.event_time >= NOW() - INTERVAL '7 days'
GROUP BY
    fse.event_type,
    det.category,
    fse.severity
ORDER BY
    event_count DESC;


-- ---------------------------------------------------------
-- 4. Hour-of-day heatmap (all time)
--    Shows which hours of the day have the most events.
-- ---------------------------------------------------------
SELECT
    EXTRACT(HOUR FROM fse.event_time)::INT  AS hour_of_day,
    EXTRACT(DOW  FROM fse.event_time)::INT  AS day_of_week,  -- 0=Sun
    fse.severity,
    COUNT(*)                                 AS event_count
FROM
    fact_security_events fse
GROUP BY
    hour_of_day,
    day_of_week,
    fse.severity
ORDER BY
    day_of_week,
    hour_of_day;


-- ---------------------------------------------------------
-- 5. Critical-event spike detection
--    Flags hours where critical events exceed 2x the
--    rolling 24-hour average.
-- ---------------------------------------------------------
WITH hourly_critical AS (
    SELECT
        DATE_TRUNC('hour', fse.event_time) AS event_hour,
        COUNT(*)                            AS critical_count
    FROM
        fact_security_events fse
    WHERE
        fse.severity = 'critical'
    GROUP BY
        DATE_TRUNC('hour', fse.event_time)
),
with_rolling_avg AS (
    SELECT
        event_hour,
        critical_count,
        AVG(critical_count) OVER (
            ORDER BY event_hour
            ROWS BETWEEN 24 PRECEDING AND 1 PRECEDING
        ) AS rolling_avg_24h
    FROM
        hourly_critical
)
SELECT
    event_hour,
    critical_count,
    ROUND(rolling_avg_24h::NUMERIC, 2) AS rolling_avg_24h,
    ROUND(
        (critical_count / NULLIF(rolling_avg_24h, 0))::NUMERIC, 2
    ) AS spike_ratio
FROM
    with_rolling_avg
WHERE
    critical_count > 2 * COALESCE(rolling_avg_24h, 0)
    AND rolling_avg_24h > 0
ORDER BY
    event_hour DESC;
