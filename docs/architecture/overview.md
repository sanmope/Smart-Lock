# Architecture Overview

## Current State

The Smart Lock system is a FastAPI application managing IoT smart locks for shipment security. It currently uses SQLite as the operational database with a synchronous request-response pattern.

### Current Data Flow

```
Smart Lock Device --> FastAPI --> SQLite
                                    |
                                    v
                               GET endpoints (real-time queries)
```

### Current Data Models

- **Lock**: id, status (ACTIVE/INACTIVE/TAMPERED/OFFLINE), location (lat/lng), last_update
- **SecurityEvent**: id, lock_id, event_type, severity, event_time
- **Shipment**: id, shipment_id, status, last_update
- **LockAssignment**: id, lock_id, shipment_id, assigned_at, released_at

## Target Architecture

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Data flow pattern | Event-driven (not dual-write) | Eliminates inconsistency between DB and Kafka. API is stateless, scales horizontally. |
| Streaming layer | Apache Kafka | Durable, partitioned, replayable. Industry standard for IoT event streams. |
| Serialization | Avro + Schema Registry | Schema evolution with backward compatibility, 40-60% smaller than JSON. |
| Processing | PySpark Structured Streaming | Native Kafka connector, exactly-once semantics, same engine for batch and streaming. |
| Data warehouse | Amazon Redshift | Columnar MPP, optimized for analytical queries. Star schema with DISTKEY/SORTKEY. |
| Visualization | Superset + Grafana | Superset for analytics/BI dashboards. Grafana for real-time monitoring and alerts. |
| IDs | UUID (not autoincrement) | API generates IDs before producing to Kafka, since the DB no longer generates them. |
| API responses | 202 Accepted for writes | Data is in Kafka, not yet in DB. Eventual consistency (~1-2s). |

### End-to-End Data Flow

```
Smart Lock Device
    | (HTTPS)
    v
FastAPI (main.py) -- stateless, only produces to Kafka
    |
    '-->  Kafka (Avro + Schema Registry)
            |
            |-- smartlock.lock.status-changes      (12 partitions, key=lock_id)
            |-- smartlock.security.events           (12 partitions, key=lock_id)
            |-- smartlock.lock.location-updates     (24 partitions, key=lock_id)
            '-- smartlock.shipment.status-changes   (6 partitions, key=shipment_id)
                    |
                    |--> Consumer A (Python service)
                    |       |
                    |       v
                    |    PostgreSQL (operational DB)
                    |       |
                    |       |--> Superset (operational dashboards, port 8088)
                    |       '--> Grafana (real-time monitoring + alerts, port 3000)
                    |
                    '--> Consumer B: PySpark Structured Streaming (3 jobs)
                            |
                            |-- Deserialize Avro (Schema Registry)
                            |-- Watermarks (5-10 min for late data)
                            |-- Enrich with dimension data
                            '-- Transform (classify, compute deltas)
                                    |
                                    v
                            S3 Staging (Parquet) --> Redshift COPY
                                                        |
                                                        v
                                                Amazon Redshift
                                                    |-- Dimensions (dim_lock, dim_shipment, dim_date...)
                                                    |-- Facts (fact_security_events, fact_lock_status_changes...)
                                                    |-- Materialized Views
                                                    '-- Batch Aggregations
                                                            |
                                                            |--> Superset (deep analytics)
                                                            '--> Grafana (aggregated metrics)
```

### Why Event-Driven (not Dual-Write)?

The API only writes to Kafka. A separate consumer reads from Kafka and writes to PostgreSQL.

**Problem with dual-write** (API writes to both DB and Kafka):
- If Kafka fails after DB commit, the event is lost from the pipeline
- When scaling the API horizontally (multiple instances behind a load balancer), race conditions and ordering inconsistencies between DB and Kafka become hard to manage
- Each API instance has its own Kafka producer; if one dies between DB commit and Kafka produce, data diverges

**Event-driven solves this**:
- API is 100% stateless -- only produces to Kafka. Scaling to N instances is trivial
- Kafka guarantees order per partition (by lock_id), regardless of which API instance produced the message
- Consumers use Kafka consumer groups: each partition is read by exactly one consumer, eliminating race conditions on PostgreSQL writes
- If a consumer dies, Kafka reassigns its partitions to another consumer in the group (automatic rebalancing)

**Trade-off**: Eventual consistency. A `POST /locks` followed immediately by `GET /locks/{id}` may return 404 for ~1-2 seconds until the consumer writes to PostgreSQL. This is acceptable for IoT devices that send data and move on.

## Project Structure

```
smart_lock/
|-- main.py                          # Modify: only produce to Kafka (no DB writes)
|-- db_models.py                     # Unchanged (used by consumer)
|-- schemas.py                       # Unchanged
|-- database.py                      # Unchanged (used by consumer)
|
|-- kafka/
|   |-- __init__.py
|   |-- config.py                    # Broker URLs, topic names, producer settings
|   |-- producer.py                  # KafkaProducerService wrapper (confluent-kafka)
|   |-- consumer.py                  # Consumer service: Kafka -> PostgreSQL
|   |-- serializers.py               # Avro serialization/deserialization helpers
|   '-- schemas/
|       |-- lock_status_change.avsc
|       |-- security_event.avsc
|       |-- location_update.avsc
|       '-- shipment_status_change.avsc
|
|-- spark/
|   |-- config.py                    # SparkSession builder, Kafka/Redshift configs
|   |-- streaming/
|   |   |-- event_stream.py          # Kafka -> enrich -> Redshift
|   |   |-- lock_status_stream.py    # State transitions + duration
|   |   '-- location_stream.py       # GPS telemetry + deviation detection
|   |-- batch/
|   |   |-- daily_shipment_summary.py
|   |   |-- lock_utilization.py
|   |   '-- event_severity_rollup.py
|   '-- utils/
|       |-- redshift_writer.py       # JDBC + S3 staging for COPY
|       '-- schema_registry.py       # Schema Registry client
|
|-- redshift/
|   |-- migrations/
|   |   |-- 001_create_dim_tables.sql
|   |   |-- 002_create_fact_tables.sql
|   |   '-- 003_create_materialized_views.sql
|   '-- queries/
|       |-- shipment_health_dashboard.sql
|       '-- event_trend_analysis.sql
|
|-- grafana/
|   '-- provisioning/
|       |-- datasources/
|       |   '-- datasources.yml      # PostgreSQL and Redshift connections
|       '-- dashboards/
|           |-- lock_monitoring.json  # Real-time lock status
|           '-- security_alerts.json  # Security event alerts
|
|-- superset/
|   '-- superset_config.py           # Superset configuration
|
|-- docker/
|   |-- Dockerfile.api               # FastAPI (producer)
|   |-- Dockerfile.consumer          # Kafka consumer -> PostgreSQL
|   |-- Dockerfile.spark             # PySpark jobs
|   '-- spark-defaults.conf
|
|-- docker-compose.yml
|-- requirements.txt                 # API deps: fastapi, confluent-kafka, fastavro
|-- requirements-consumer.txt        # Consumer deps: confluent-kafka, sqlalchemy, psycopg2
'-- requirements-spark.txt           # Spark deps: pyspark + connectors
```

## Implementation Phases

| # | Phase | Key Files |
|---|-------|-----------|
| 1 | Docker Compose (Kafka, PostgreSQL, Schema Registry) | `docker-compose.yml`, `docker/Dockerfile.api` |
| 2 | Kafka Producer in FastAPI (event-driven) | `kafka/config.py`, `kafka/producer.py`, `kafka/serializers.py`, `main.py`, `kafka/schemas/*.avsc` |
| 3 | Kafka Consumer -> PostgreSQL | `kafka/consumer.py`, `docker/Dockerfile.consumer`, `requirements-consumer.txt` |
| 4 | Redshift DDL (star schema) | `redshift/migrations/001-003.sql` |
| 5 | PySpark Streaming Jobs | `spark/config.py`, `spark/streaming/*.py`, `spark/utils/*.py` |
| 6 | PySpark Batch Jobs + Materialized Views | `spark/batch/*.py`, `redshift/migrations/003_*.sql` |
| 7 | Superset + Grafana (dashboards and alerts) | `grafana/provisioning/**`, `superset/superset_config.py` |
| 8 | End-to-end testing | `tests/test_kafka_producer.py`, `tests/test_consumer.py`, `tests/test_spark_streaming.py` |
