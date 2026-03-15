import os

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")

TOPICS = {
    "lock_status_changes": "smartlock.lock.status-changes",
    "security_events": "smartlock.security.events",
    "location_updates": "smartlock.lock.location-updates",
    "shipment_status_changes": "smartlock.shipment.status-changes",
}

TOPIC_CONFIGS = {
    "smartlock.lock.status-changes": {"partitions": 12, "retention.ms": 604800000},       # 7 days
    "smartlock.security.events": {"partitions": 12, "retention.ms": 2592000000},           # 30 days
    "smartlock.lock.location-updates": {"partitions": 24, "retention.ms": 259200000},      # 3 days
    "smartlock.shipment.status-changes": {"partitions": 6, "retention.ms": 1209600000},    # 14 days
}

PRODUCER_CONFIG = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "acks": "all",
    "enable.idempotence": True,
    "compression.type": "snappy",
    "linger.ms": 5,
    "batch.size": 16384,
}

CONSUMER_CONFIG = {
    "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
    "group.id": "smartlock-db-writer",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
}
