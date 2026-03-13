# Kafka Design

## Topics

| Topic | Partition Key | Partitions | Retention | Cleanup |
|-------|--------------|------------|-----------|---------|
| `smartlock.lock.status-changes` | `lock_id` | 12 | 7 days | delete |
| `smartlock.security.events` | `lock_id` | 12 | 30 days | delete |
| `smartlock.lock.location-updates` | `lock_id` | 24 | 3 days | delete |
| `smartlock.shipment.status-changes` | `shipment_id` | 6 | 14 days | delete |

### Partitioning Strategy

All lock-related topics use `lock_id` as the partition key. This guarantees:

1. **Per-lock ordering**: All events for the same lock land in the same partition, preserving chronological order.
2. **Data co-location**: PySpark consumers get all data for a given lock in one partition, making stateful operations (delta calculations, duration tracking) efficient.
3. **Parallelism**: 12 partitions allow up to 12 parallel consumers per topic.

The location topic has 24 partitions because GPS telemetry has significantly higher throughput (~100x more messages than security events).

The shipment topic uses `shipment_id` as key since those events are shipment-centric and lower volume.

### Retention Rationale

- **Security events (30 days)**: Compliance audit trail before data reaches Redshift.
- **Status changes (7 days)**: Enough for replay if a consumer needs to reprocess.
- **Location updates (3 days)**: High-volume ephemeral data. Redshift holds the long-term history.
- **Shipment changes (14 days)**: Moderate volume, useful for debugging shipment lifecycle issues.

## Avro Schemas

Using Confluent Schema Registry with **BACKWARD** compatibility mode. New schemas can add optional fields (with defaults) but cannot remove existing required fields. Consumers using older schemas can still read newer messages.

### lock_status_change.avsc

```json
{
  "type": "record",
  "name": "LockStatusChange",
  "namespace": "com.smartlock.events",
  "fields": [
    {"name": "lock_id", "type": "string", "doc": "UUID of the lock"},
    {"name": "previous_status", "type": ["null", "string"], "default": null},
    {"name": "new_status", "type": "string"},
    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "shipment_id", "type": ["null", "string"], "default": null},
    {"name": "metadata", "type": ["null", {"type": "map", "values": "string"}], "default": null}
  ]
}
```

### security_event.avsc

```json
{
  "type": "record",
  "name": "SecurityEvent",
  "namespace": "com.smartlock.events",
  "fields": [
    {"name": "event_id", "type": "string", "doc": "UUID of the event"},
    {"name": "lock_id", "type": "string"},
    {"name": "event_type", "type": {"type": "enum", "name": "EventType", "symbols": ["UNLOCK_ATTEMPT", "TAMPER_DETECTED", "BATTERY_LOW", "LOCATION_DEVIATION", "CONNECTION_LOST"]}},
    {"name": "severity", "type": {"type": "enum", "name": "Severity", "symbols": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]}},
    {"name": "event_time", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "shipment_id", "type": ["null", "string"], "default": null},
    {"name": "latitude", "type": ["null", "double"], "default": null},
    {"name": "longitude", "type": ["null", "double"], "default": null}
  ]
}
```

### location_update.avsc

```json
{
  "type": "record",
  "name": "LocationUpdate",
  "namespace": "com.smartlock.events",
  "fields": [
    {"name": "lock_id", "type": "string"},
    {"name": "latitude", "type": "double"},
    {"name": "longitude", "type": "double"},
    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}},
    {"name": "speed_kmh", "type": ["null", "float"], "default": null},
    {"name": "battery_pct", "type": ["null", "int"], "default": null}
  ]
}
```

### shipment_status_change.avsc

```json
{
  "type": "record",
  "name": "ShipmentStatusChange",
  "namespace": "com.smartlock.events",
  "fields": [
    {"name": "shipment_id", "type": "string"},
    {"name": "previous_status", "type": ["null", "string"], "default": null},
    {"name": "new_status", "type": "string"},
    {"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}}
  ]
}
```

### Schema Evolution

All new fields must have a default value (Avro union with `null`). This ensures backward compatibility:

```
Schema v1: {"lock_id": "abc", "event_type": "TAMPER_DETECTED", "severity": "CRITICAL"}
Schema v2: {"lock_id": "abc", "event_type": "TAMPER_DETECTED", "severity": "CRITICAL", "battery_level": null}
```

A consumer using v1 ignores `battery_level`. Nothing breaks.

## Producer Design

### KafkaProducerService (`kafka/producer.py`)

Singleton wrapper around `confluent_kafka.SerializingProducer`:

- Initialized on FastAPI startup via `lifespan` context manager.
- Uses `AvroSerializer` from `confluent_kafka.schema_registry.avro` for automatic schema registration.
- Exposes methods: `produce_lock_status_change()`, `produce_security_event()`, `produce_location_update()`, `produce_shipment_status_change()`.
- Implements delivery callback for error handling and logging.
- Calls `producer.flush()` on FastAPI shutdown.

### Producer Configuration

```python
PRODUCER_CONFIG = {
    "bootstrap.servers": "kafka:9092",
    "acks": "all",                                  # strongest durability
    "enable.idempotence": True,                     # exactly-once producer
    "max.in.flight.requests.per.connection": 5,     # safe with idempotence
    "retries": 10,
    "linger.ms": 5,                                 # micro-batching
    "compression.type": "snappy",                   # good speed/ratio for IoT
}
```

### API Integration

Write endpoints no longer write to the database. They produce to Kafka and return `202 Accepted`:

```
POST /locks       --> produce to smartlock.lock.status-changes   --> 202 + UUID
POST /events      --> produce to smartlock.security.events       --> 202 + UUID
PATCH /locks/status --> produce to smartlock.lock.status-changes --> 202
POST /shipments   --> produce to smartlock.shipment.status-changes --> 202 + UUID
```

Read endpoints still query PostgreSQL (populated by the consumer):

```
GET /locks/{id}           --> PostgreSQL
GET /events               --> PostgreSQL
GET /shipments/{id}/health --> PostgreSQL
```

## Consumer Design

### DB Writer Consumer (`kafka/consumer.py`)

Separate Python process running in its own container.

- Uses `confluent_kafka.DeserializingConsumer` with Avro.
- Consumer group: `smartlock-db-writer`.
- Subscribes to all 4 topics.
- Writes to PostgreSQL using SQLAlchemy (reuses `db_models.py` and `database.py`).
- Commits offsets **after** confirming the write to PostgreSQL (at-least-once delivery).
- Dead-letter topic (`smartlock.dead-letter`) for messages that fail after N retries.

### Consumer Scaling

- Each partition is read by exactly one consumer in the group.
- To scale: add more consumer instances (up to the number of partitions).
- Kafka automatically rebalances partitions across consumers.

```
Consumer group: smartlock-db-writer
  Consumer 1: partitions 0-3  (lock.status-changes)
  Consumer 2: partitions 4-7  (lock.status-changes)
  Consumer 3: partitions 8-11 (lock.status-changes)
```

### Error Handling

1. Transient errors (DB timeout, connection reset): retry with exponential backoff (max 3 retries).
2. Permanent errors (schema mismatch, invalid data): send to dead-letter topic, commit offset, continue.
3. Consumer crash: Kafka reassigns partitions to surviving consumers. On restart, resumes from last committed offset.
