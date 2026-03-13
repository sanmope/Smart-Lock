# Redshift Schema Design

## Why Star Schema?

The operational database (PostgreSQL) uses a normalized model optimized for writes and transactional consistency (OLTP). The data warehouse (Redshift) uses a star schema optimized for analytical queries (OLAP).

| Aspect | Normalized (PostgreSQL) | Star Schema (Redshift) |
|--------|------------------------|----------------------|
| Optimized for | INSERT, UPDATE (single rows) | SELECT + GROUP BY (millions of rows) |
| Joins | Multiple levels (chained) | 1 level (star) |
| Redundancy | Minimal | Intentional (denormalized) |
| Example | "save this event" | "how many events per day per shipment?" |

### Why Star Schema Works Well with Redshift

1. **Simple joins**: Fact table in the center, dimensions around it. At most 1 JOIN per dimension. No chained joins.
2. **Columnar storage**: Redshift reads only the columns needed. Fact tables with few columns (IDs + metrics) minimize I/O.
3. **DISTKEY co-location**: Setting `DISTKEY(lock_id)` on both fact and dimension tables ensures JOINs happen locally on each node without network shuffling.
4. **Small dimensions, large facts**: Dimensions replicated to all nodes (`DISTSTYLE ALL`), facts distributed by key. JOINs never move data.

## Dimension Tables

### dim_lock (SCD Type 2)

Tracks lock state history. A new row is inserted on each status change (previous row's `effective_to` is updated).

```sql
CREATE TABLE dim_lock (
    lock_key        INT IDENTITY(1,1) PRIMARY KEY,
    lock_id         VARCHAR(36) NOT NULL,     -- UUID
    status          VARCHAR(20) NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    effective_from  TIMESTAMP NOT NULL,
    effective_to    TIMESTAMP DEFAULT '9999-12-31',
    is_current      BOOLEAN DEFAULT TRUE
)
DISTSTYLE KEY
DISTKEY (lock_id)
SORTKEY (lock_id, effective_from);
```

### dim_shipment (SCD Type 2)

```sql
CREATE TABLE dim_shipment (
    shipment_key    INT IDENTITY(1,1) PRIMARY KEY,
    shipment_id     VARCHAR(36) NOT NULL,     -- UUID
    status          VARCHAR(20) NOT NULL,
    effective_from  TIMESTAMP NOT NULL,
    effective_to    TIMESTAMP DEFAULT '9999-12-31',
    is_current      BOOLEAN DEFAULT TRUE
)
DISTSTYLE KEY
DISTKEY (shipment_id)
SORTKEY (shipment_id, effective_from);
```

### dim_lock_assignment

```sql
CREATE TABLE dim_lock_assignment (
    assignment_key  INT IDENTITY(1,1) PRIMARY KEY,
    lock_id         VARCHAR(36) NOT NULL,
    shipment_id     VARCHAR(36) NOT NULL,
    assigned_at     TIMESTAMP NOT NULL,
    released_at     TIMESTAMP,
    is_active       BOOLEAN DEFAULT TRUE
)
DISTSTYLE KEY
DISTKEY (lock_id)
SORTKEY (assigned_at);
```

### dim_event_type (Static)

Small reference table, replicated to all nodes.

```sql
CREATE TABLE dim_event_type (
    event_type_key      INT IDENTITY(1,1) PRIMARY KEY,
    event_type          VARCHAR(30) NOT NULL,
    severity_category   VARCHAR(10) NOT NULL,     -- 'WARNING' or 'CRITICAL'
    description         VARCHAR(200)
)
DISTSTYLE ALL;

-- Seed data
INSERT INTO dim_event_type (event_type, severity_category, description) VALUES
('UNLOCK_ATTEMPT',    'CRITICAL', 'Unauthorized unlock attempt detected'),
('TAMPER_DETECTED',   'CRITICAL', 'Physical tampering detected on device'),
('LOCATION_DEVIATION','CRITICAL', 'Lock location deviates from expected route'),
('BATTERY_LOW',       'WARNING',  'Battery level below threshold'),
('CONNECTION_LOST',   'WARNING',  'Device lost connectivity');
```

### dim_date (Static)

Standard date dimension, replicated to all nodes.

```sql
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,        -- YYYYMMDD
    full_date       DATE NOT NULL,
    year            INT,
    quarter         INT,
    month           INT,
    week            INT,
    day_of_week     INT,
    is_weekend      BOOLEAN
)
DISTSTYLE ALL;
```

## Fact Tables

### fact_security_events

Grain: one row per security event.

```sql
CREATE TABLE fact_security_events (
    event_id        VARCHAR(36) NOT NULL,     -- UUID
    lock_id         VARCHAR(36) NOT NULL,
    shipment_id     VARCHAR(36),
    event_type      VARCHAR(30) NOT NULL,
    severity        VARCHAR(10) NOT NULL,
    event_time      TIMESTAMP NOT NULL,
    date_key        INT NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    ingestion_time  TIMESTAMP DEFAULT GETDATE()
)
DISTSTYLE KEY
DISTKEY (lock_id)
SORTKEY (event_time);
```

### fact_lock_status_changes

Grain: one row per status transition.

```sql
CREATE TABLE fact_lock_status_changes (
    lock_id             VARCHAR(36) NOT NULL,
    shipment_id         VARCHAR(36),
    previous_status     VARCHAR(20),
    new_status          VARCHAR(20) NOT NULL,
    change_time         TIMESTAMP NOT NULL,
    date_key            INT NOT NULL,
    duration_seconds    BIGINT               -- time spent in previous status
)
DISTSTYLE KEY
DISTKEY (lock_id)
SORTKEY (change_time);
```

### fact_location_updates

Grain: one row per GPS reading.

```sql
CREATE TABLE fact_location_updates (
    lock_id         VARCHAR(36) NOT NULL,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    speed_kmh       REAL,
    battery_pct     INT,
    update_time     TIMESTAMP NOT NULL,
    date_key        INT NOT NULL,
    distance_delta_m DOUBLE PRECISION        -- meters from previous reading
)
DISTSTYLE KEY
DISTKEY (lock_id)
SORTKEY (update_time);
```

## Distribution and Sort Key Rationale

| Key Type | Choice | Why |
|----------|--------|-----|
| DISTKEY | `lock_id` on all fact + dim_lock | Most queries join facts with dim_lock and filter/group by lock. Co-locates data on same Redshift slice. |
| SORTKEY | Timestamp columns (`event_time`, `change_time`, `update_time`) | Range queries on time are the dominant access pattern. Zone maps skip entire blocks of sorted data. |
| DISTSTYLE ALL | `dim_event_type`, `dim_date` | Small tables (<1000 rows). Replicating avoids broadcast joins. |

## Materialized Views

### mv_shipment_health

Replaces the Python-computed `/shipments/{id}/health` endpoint logic. Refresh every 5 minutes.

```sql
CREATE MATERIALIZED VIEW mv_shipment_health AS
SELECT
    da.shipment_id,
    COUNT(DISTINCT da.lock_id) AS total_locks,
    COUNT(DISTINCT CASE
        WHEN dl.status IN ('tampered', 'offline') THEN dl.lock_id
    END) AS compromised_locks,
    COUNT(CASE
        WHEN fe.severity IN ('critical', 'high')
        AND fe.event_time > DATEADD(hour, -1, GETDATE()) THEN 1
    END) AS critical_events_last_hour,
    CASE
        WHEN COUNT(CASE
            WHEN fe.event_type IN ('unlock_attempt','tamper_detected','location_deviation')
            AND fe.event_time > DATEADD(hour, -1, GETDATE()) THEN 1
        END) > 0 THEN 'critical'
        WHEN COUNT(CASE
            WHEN fe.event_type IN ('battery_low','connection_lost')
            AND fe.event_time > DATEADD(hour, -1, GETDATE()) THEN 1
        END) > 0 THEN 'warning'
        ELSE 'ok'
    END AS overall_status,
    GETDATE() AS computed_at
FROM dim_lock_assignment da
JOIN dim_lock dl ON da.lock_id = dl.lock_id AND dl.is_current = TRUE
LEFT JOIN fact_security_events fe ON fe.lock_id = da.lock_id
WHERE da.is_active = TRUE
GROUP BY da.shipment_id;
```

### mv_hourly_event_trend

Pre-aggregated for dashboard queries. Last 30 days.

```sql
CREATE MATERIALIZED VIEW mv_hourly_event_trend AS
SELECT
    DATE_TRUNC('hour', event_time) AS event_hour,
    event_type,
    severity,
    COUNT(*) AS event_count
FROM fact_security_events
WHERE event_time > DATEADD(day, -30, GETDATE())
GROUP BY 1, 2, 3;
```

## Aggregate Tables (Batch Jobs)

### agg_daily_shipment_summary

Populated by `daily_shipment_summary.py` batch job (daily at 02:00 UTC).

```sql
CREATE TABLE agg_daily_shipment_summary (
    date_key            INT NOT NULL,
    shipment_id         VARCHAR(36) NOT NULL,
    total_events        INT,
    critical_events     INT,
    warning_events      INT,
    status_changes      INT,
    time_in_transit_min INT,
    compromised_locks   INT,
    total_locks         INT
)
DISTSTYLE KEY
DISTKEY (shipment_id)
SORTKEY (date_key);
```

### agg_hourly_event_counts

Populated by `event_severity_rollup.py` batch job (hourly).

```sql
CREATE TABLE agg_hourly_event_counts (
    date_key        INT NOT NULL,
    hour            INT NOT NULL,
    event_type      VARCHAR(30) NOT NULL,
    severity        VARCHAR(10) NOT NULL,
    event_count     INT NOT NULL
)
DISTSTYLE ALL
SORTKEY (date_key, hour);
```

## Local Development

For local development, PostgreSQL 16 on port 5439 substitutes Redshift. The DDL scripts should omit Redshift-specific syntax (DISTKEY, SORTKEY, DISTSTYLE) when running locally. Use conditional SQL or a separate set of local DDLs that strip these clauses.
