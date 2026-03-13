# Visualization: Superset + Grafana

Two complementary tools covering different use cases.

| Aspect | Superset | Grafana |
|--------|----------|---------|
| Purpose | Analytics, BI dashboards, ad-hoc queries | Real-time monitoring, operational alerts |
| Audience | Analysts, management | Operations, on-call engineers |
| Refresh rate | Minutes / hours | Seconds (10s) |
| Alerts | No | Yes (Slack, email, PagerDuty) |
| Maps | Yes (deck.gl, rich geospatial) | Basic (Geomap plugin) |
| SQL | Full SQL editor for ad-hoc queries | Limited |

## Superset (Port 8088)

### Data Sources

| Source | Connection | Use Case |
|--------|-----------|----------|
| Redshift | SQLAlchemy `redshift+psycopg2://` | Deep analytics, historical trends, aggregations |
| PostgreSQL | SQLAlchemy `postgresql://` | Operational data, current state queries |

### Proposed Dashboards

**1. Shipment Health Overview**
- Map showing all locks with color-coded status (green=ok, yellow=warning, red=critical)
- Table of shipments with health status, total locks, compromised count
- Trend line: events per hour over last 7 days
- Data source: Redshift (`mv_shipment_health`, `fact_security_events`)

**2. Security Events Analysis**
- Bar chart: events by type and severity (last 30 days)
- Time series: event frequency trends
- Top 10 locks by incident count
- Heatmap: geographic concentration of CRITICAL events
- Data source: Redshift (`fact_security_events`, `mv_hourly_event_trend`)

**3. Lock Utilization**
- Average assignment duration by lock
- Utilization rate distribution
- MTBF (mean time between failures) ranking
- Data source: Redshift (`agg_daily_shipment_summary`)

**4. Historical Route Tracking**
- Select a lock and date range
- deck.gl map showing the GPS trajectory
- Speed graph along the route
- Data source: Redshift (`fact_location_updates`)

## Grafana (Port 3000)

### Data Sources

| Source | Plugin | Use Case |
|--------|--------|----------|
| PostgreSQL | Built-in PostgreSQL | Real-time operational data |
| Redshift | PostgreSQL plugin (compatible) | Aggregated metrics |

### Proposed Dashboards

**1. Lock Status Monitor**
- Geomap: current location of all locks, color by status
- Stat panels: total active, inactive, tampered, offline
- Table: locks with status changes in last hour
- Auto-refresh: every 10 seconds
- Data source: PostgreSQL

```sql
-- Current lock positions for Geomap
SELECT l.id, loc.latitude, loc.longitude, l.status
FROM locks l
JOIN locations loc ON l.id = loc.lock_id;
```

**2. Security Alerts Dashboard**
- Time series: events per minute (last 6 hours)
- Alert list: recent CRITICAL events with lock and shipment details
- Gauge: overall system health (% of locks in OK status)
- Data source: PostgreSQL

### Alert Rules

| Alert | Condition | Severity | Notification |
|-------|-----------|----------|--------------|
| Tamper Detected | `event_type = 'TAMPER_DETECTED'` | Critical | Slack + PagerDuty |
| Mass Offline | `> 20% locks offline in 5 min` | Critical | Slack + PagerDuty |
| Critical Event Spike | `> 5 CRITICAL events in 10 min` | High | Slack |
| Battery Low | `> 20% locks with BATTERY_LOW` | Warning | Email |
| Connection Lost | `lock offline > 30 min` | Warning | Slack |

### Alert Configuration

Grafana alerts are configured via provisioning YAML:

```yaml
# grafana/provisioning/alerting/rules.yml
groups:
  - name: security_alerts
    rules:
      - alert: TamperDetected
        expr: |
          SELECT COUNT(*) FROM security_events
          WHERE event_type = 'TAMPER_DETECTED'
          AND event_time > NOW() - INTERVAL '1 minute'
        for: 0m
        labels:
          severity: critical
        annotations:
          summary: "Tamper detected on lock"
```

## Which Data Source for Maps?

| Map Type | Source | Tool |
|----------|--------|------|
| Live lock positions | PostgreSQL | Grafana Geomap |
| Historical route/trajectory | Redshift (`fact_location_updates`) | Superset (deck.gl) |
| Event heatmap | Redshift (`fact_security_events`) | Superset (deck.gl) |
| Zones with offline locks | PostgreSQL | Grafana Geomap |

Never read from Kafka directly for visualization. Kafka is a transport stream, not a query engine. Always read from a database that has already consumed and stored the data.

## Docker Setup

```yaml
# In docker-compose.yml
superset:
  image: apache/superset:3.1.0
  ports:
    - "8088:8088"
  environment:
    - SUPERSET_SECRET_KEY=your-secret-key
  volumes:
    - ./superset/superset_config.py:/app/pythonpath/superset_config.py

grafana:
  image: grafana/grafana:10.3.0
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
  volumes:
    - ./grafana/provisioning:/etc/grafana/provisioning
```
