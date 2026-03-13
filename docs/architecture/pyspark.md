# PySpark Processing

PySpark handles two types of processing:
- **Streaming jobs**: Read from Kafka in real-time, write to Redshift.
- **Batch jobs**: Read from PostgreSQL on a schedule, write aggregations to Redshift.

## How PySpark Connects to Kafka

PySpark has a built-in Kafka connector (`spark-sql-kafka`). The connection is straightforward:

```python
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka:9092") \
    .option("subscribe", "smartlock.security.events") \
    .option("startingOffsets", "latest") \
    .load()
```

This returns a DataFrame with columns: `key`, `value` (binary), `topic`, `partition`, `offset`, `timestamp`.

### What PySpark handles automatically

- Connecting to Kafka brokers
- Managing offsets (what's already been read)
- Partition rebalancing
- Retries on Kafka failures
- Parallelism (1 task per partition)
- Continuous reading (readStream is an infinite loop)

### What you write

1. **Deserialization**: Convert `value` bytes to structured columns (Avro or JSON)
2. **Transformations**: Your business logic
3. **Output destination**: Where to write results (Redshift, S3, etc.)

## Streaming Jobs

Each streaming job reads from a Kafka topic, processes the data through 4 stages, and writes to Redshift.

### Processing Pipeline

```
Kafka (raw bytes)
  |
  v
[1] Deserialize    ->  {"lock_id": "abc-123", "event_type": "TAMPER_DETECTED"}
  |
  v
[2] Watermark      ->  "this event is 7 min late, but I accept it"
  |
  v
[3] Enrich         ->  + shipment_id, + lat/lng, + severity_category
  |
  v
[4] Transform      ->  + duration_seconds, + distance_delta_m
  |
  v
Redshift (complete row, ready for analytics)
```

### Stage Details

**1. Deserialize Avro**

Messages arrive from Kafka as raw binary (Avro format). The Schema Registry tells PySpark what structure those bytes have.

```python
from pyspark.sql.avro.functions import from_avro

parsed = df.select(
    from_avro(col("value"), avro_schema_string).alias("data")
).select("data.*")
```

**2. Watermarks (for late-arriving data)**

IoT devices may lose signal (tunnels, cellular gaps). An event that happened at 14:00:00 might arrive at Kafka at 14:07:00.

The watermark tells Spark: "wait up to N minutes for late data before closing a time window."

```
Without watermark:
  14:05:01 -> Spark closes the window. Final result.
  14:07:00 -> event from 14:03 arrives -> LOST

With 10-min watermark:
  14:05:01 -> Spark keeps the window open...
  14:07:00 -> event from 14:03 arrives -> INCLUDED
  14:15:01 -> Spark closes the window (14:05 + 10min). Final result.
```

**3. Enrich with dimensions**

Raw Kafka messages only have IDs. Analytics needs context. Enrichment adds dimension data via broadcast joins:

```
Raw message:       {"lock_id": "abc", "event_type": "TAMPER_DETECTED"}
After enrichment:  {"lock_id": "abc", "event_type": "TAMPER_DETECTED",
                    "lock_status": "ACTIVE", "shipment_id": "SHIP-015",
                    "severity_category": "CRITICAL"}
```

Dimension tables are loaded into memory (small tables) and refreshed every ~5 minutes.

**4. Transform (classify, compute deltas)**

Business logic applied before writing to Redshift:

- **Classify**: Same logic as `schemas.py` -- categorize events as WARNING or CRITICAL.
- **Compute deltas**:
  - Location: distance from previous reading, speed calculation.
  - Status: duration in previous status before transition.

### Job 1: event_stream.py

Security events processing.

```
Kafka(smartlock.security.events)
  -> Deserialize Avro
  -> Watermark: 10 minutes
  -> Enrich with dim_lock, dim_lock_assignment
  -> Classify severity category
  -> Write to fact_security_events
  -> Trigger: processingTime="30 seconds"
  -> Output mode: append
```

Watermark of 10 minutes because security events are high-value -- worth waiting for late arrivals.

### Job 2: lock_status_stream.py

Lock status transition tracking.

```
Kafka(smartlock.lock.status-changes)
  -> Deserialize Avro
  -> Watermark: 5 minutes
  -> Compute state transition duration (time between consecutive changes per lock)
  -> Detect anomalous transitions (e.g., ACTIVE -> TAMPERED)
  -> Write to fact_lock_status_changes
  -> Trigger: processingTime="15 seconds"
```

Uses stateful processing to track per-lock state and compute durations.

### Job 3: location_stream.py

GPS telemetry processing.

```
Kafka(smartlock.lock.location-updates)
  -> Deserialize Avro
  -> Watermark: 5 minutes
  -> mapGroupsWithState by lock_id: compute distance delta from previous location
  -> Detect location deviation (speed > threshold or geofence breach)
  -> Write to fact_location_updates
  -> Trigger: processingTime="60 seconds"
```

Higher trigger interval (60s) because location data is the highest volume stream.

## Writing to Redshift

PySpark cannot write directly to Redshift efficiently. The standard pattern:

1. Spark writes Parquet files to S3 staging bucket.
2. Redshift `COPY` command loads from S3 (massively parallel, uses Redshift's MPP architecture).
3. The `spark-redshift` connector automates this workflow.

```python
df.write \
    .format("io.github.spark_redshift_community.spark.redshift") \
    .option("url", REDSHIFT_JDBC_URL) \
    .option("dbtable", "fact_security_events") \
    .option("tempdir", "s3://smartlock-staging/temp/") \
    .option("aws_iam_role", IAM_ROLE) \
    .mode("append") \
    .save()
```

## Exactly-Once Semantics

Achieved through three layers:

1. **Producer**: Kafka idempotent producer (`enable.idempotence=True`) prevents duplicate messages.
2. **Streaming**: Spark checkpointing stores offsets and partial state. On restart, resumes from last checkpoint.
3. **Redshift**: COPY command with staging table + MERGE pattern for dimension updates. Append-only for facts.

## Batch Jobs

Run on a schedule. Read from PostgreSQL (data already consolidated by the consumer).

### daily_shipment_summary.py (Daily at 02:00 UTC)

Reads from `fact_security_events`, `fact_lock_status_changes`, `dim_shipment`, `dim_lock`.

Computes per-shipment daily aggregates:
- Total events by severity
- Total status transitions
- Time in each status
- Compromised lock count

Writes to `agg_daily_shipment_summary`.

### event_severity_rollup.py (Hourly)

Pre-aggregates event counts by hour, event_type, and severity for dashboard queries.

Writes to `agg_hourly_event_counts`.

### lock_utilization.py (Daily at 03:00 UTC)

Computes:
- Average assignment duration
- Utilization rate (time assigned / total time)
- MTBF (mean time between failures/tamper events)

## Dependencies

```
# requirements-spark.txt
pyspark==3.5.4
confluent-kafka[avro]==2.6.1
fastavro==1.9.7
boto3==1.35.0
```

Spark packages (loaded at runtime via `--packages`):
- `org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4` (Kafka connector)
- `org.apache.spark:spark-avro_2.12:3.5.4` (Avro support)
- `io.github.spark_redshift_community:spark-redshift_2.12:6.2.0` (Redshift connector)
