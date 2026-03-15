import asyncio
import io
import json
import logging
import os
from typing import Any, Dict, Optional

import fastavro
from confluent_kafka import Producer

from simulator.outputs.base import OutputBase

logger = logging.getLogger(__name__)

# Topic names
TOPIC_LOCK_STATUS = "smartlock.lock.status-changes"
TOPIC_SECURITY_EVENTS = "smartlock.security.events"
TOPIC_LOCATION_UPDATES = "smartlock.lock.location-updates"
TOPIC_SHIPMENT_STATUS = "smartlock.shipment.status-changes"

# Default path to Avro schema files (relative to project root)
_DEFAULT_SCHEMA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "kafka", "schemas",
)


def _load_avro_schema(path: str) -> Dict[str, Any]:
    """Load and parse an Avro schema (.avsc) file."""
    with open(path, "r") as f:
        return fastavro.parse_schema(json.load(f))


def _serialize_avro(schema: Dict[str, Any], record: Dict[str, Any]) -> bytes:
    """Serialize a single record using fastavro schemaless writer."""
    buf = io.BytesIO()
    fastavro.schemaless_writer(buf, schema, record)
    return buf.getvalue()


class KafkaOutput(OutputBase):
    """Output backend that produces Avro-encoded messages to Kafka."""

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        schema_dir: Optional[str] = None,
    ):
        self._bootstrap = bootstrap_servers
        self._schema_dir = schema_dir or _DEFAULT_SCHEMA_DIR
        self._producer: Optional[Producer] = None
        self._schemas: Dict[str, Any] = {}
        self._sent = 0

    async def setup(self) -> None:
        self._producer = Producer({
            "bootstrap.servers": self._bootstrap,
            "linger.ms": 5,
            "batch.num.messages": 1000,
            "queue.buffering.max.messages": 100000,
        })

        # Load Avro schemas
        self._schemas[TOPIC_LOCK_STATUS] = _load_avro_schema(
            os.path.join(self._schema_dir, "lock_status_change.avsc")
        )
        self._schemas[TOPIC_SECURITY_EVENTS] = _load_avro_schema(
            os.path.join(self._schema_dir, "security_event.avsc")
        )
        self._schemas[TOPIC_LOCATION_UPDATES] = _load_avro_schema(
            os.path.join(self._schema_dir, "location_update.avsc")
        )
        self._schemas[TOPIC_SHIPMENT_STATUS] = _load_avro_schema(
            os.path.join(self._schema_dir, "shipment_status_change.avsc")
        )
        logger.info(
            "KafkaOutput ready — broker=%s, schemas loaded from %s",
            self._bootstrap, self._schema_dir,
        )

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Kafka delivery failed: %s", err)

    def _produce(self, topic: str, key: str, record: Dict[str, Any]) -> None:
        """Serialize and produce a message. Non-blocking (uses poll(0))."""
        schema = self._schemas[topic]
        value = _serialize_avro(schema, record)
        self._producer.produce(
            topic,
            key=key.encode("utf-8"),
            value=value,
            callback=self._delivery_callback,
        )
        self._producer.poll(0)
        self._sent += 1

    # ------------------------------------------------------------------
    # Lock lifecycle
    # ------------------------------------------------------------------

    async def send_lock_created(
        self,
        lock_id: str,
        status: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        record = {
            "lock_id": lock_id,
            "action": "created",
            "status": status,
            "previous_status": None,
            "latitude": latitude,
            "longitude": longitude,
            "shipment_id": None,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(self._produce, TOPIC_LOCK_STATUS, lock_id, record)

    async def send_status_change(
        self,
        lock_id: str,
        status: str,
        previous_status: Optional[str],
        latitude: Optional[float],
        longitude: Optional[float],
        shipment_id: Optional[str],
        timestamp_ms: int,
    ) -> None:
        record = {
            "lock_id": lock_id,
            "action": "status_changed",
            "status": status,
            "previous_status": previous_status,
            "latitude": latitude,
            "longitude": longitude,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(self._produce, TOPIC_LOCK_STATUS, lock_id, record)

    async def send_event(
        self,
        event_id: str,
        lock_id: str,
        event_type: str,
        severity: str,
        timestamp_ms: int,
    ) -> None:
        record = {
            "event_id": event_id,
            "lock_id": lock_id,
            "event_type": event_type,
            "severity": severity,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(
            self._produce, TOPIC_SECURITY_EVENTS, lock_id, record,
        )

    async def send_location(
        self,
        lock_id: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        record = {
            "lock_id": lock_id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(
            self._produce, TOPIC_LOCATION_UPDATES, lock_id, record,
        )

    # ------------------------------------------------------------------
    # Shipment lifecycle
    # ------------------------------------------------------------------

    async def send_shipment_created(
        self,
        shipment_id: str,
        status: str,
        timestamp_ms: int,
    ) -> None:
        record = {
            "shipment_id": shipment_id,
            "action": "created",
            "status": status,
            "previous_status": None,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(
            self._produce, TOPIC_SHIPMENT_STATUS, shipment_id, record,
        )

    async def send_lock_assigned(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        record = {
            "lock_id": lock_id,
            "action": "assigned",
            "status": None,
            "previous_status": None,
            "latitude": None,
            "longitude": None,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(self._produce, TOPIC_LOCK_STATUS, lock_id, record)

    async def send_lock_released(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        record = {
            "lock_id": lock_id,
            "action": "released",
            "status": None,
            "previous_status": None,
            "latitude": None,
            "longitude": None,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        }
        await asyncio.to_thread(self._produce, TOPIC_LOCK_STATUS, lock_id, record)

    # ------------------------------------------------------------------

    @property
    def messages_sent(self) -> int:
        return self._sent

    async def close(self) -> None:
        if self._producer:
            remaining = self._producer.flush(timeout=10)
            if remaining > 0:
                logger.warning("Kafka flush: %d messages still in queue", remaining)
            logger.info("KafkaOutput closed — %d messages produced", self._sent)
