import logging
from confluent_kafka import Producer
from kafka.config import PRODUCER_CONFIG, TOPICS
from kafka.serializers import AvroSerializer

logger = logging.getLogger(__name__)


class KafkaProducerService:
    _instance = None

    def __init__(self):
        self._producer = Producer(PRODUCER_CONFIG)
        self._serializers = {
            "lock_status_change": AvroSerializer("lock_status_change"),
            "security_event": AvroSerializer("security_event"),
            "location_update": AvroSerializer("location_update"),
            "shipment_status_change": AvroSerializer("shipment_status_change"),
        }

    @classmethod
    def get_instance(cls) -> "KafkaProducerService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None

    def _on_delivery(self, err, msg):
        if err:
            logger.error("Delivery failed for %s: %s", msg.topic(), err)
        else:
            logger.debug("Delivered to %s [%d] @ %d", msg.topic(), msg.partition(), msg.offset())

    def produce_lock_status_change(self, data: dict):
        value = self._serializers["lock_status_change"].serialize(data)
        self._producer.produce(
            topic=TOPICS["lock_status_changes"],
            key=data["lock_id"].encode(),
            value=value,
            callback=self._on_delivery,
        )
        self._producer.poll(0)

    def produce_security_event(self, data: dict):
        value = self._serializers["security_event"].serialize(data)
        self._producer.produce(
            topic=TOPICS["security_events"],
            key=data["lock_id"].encode(),
            value=value,
            callback=self._on_delivery,
        )
        self._producer.poll(0)

    def produce_location_update(self, data: dict):
        value = self._serializers["location_update"].serialize(data)
        self._producer.produce(
            topic=TOPICS["location_updates"],
            key=data["lock_id"].encode(),
            value=value,
            callback=self._on_delivery,
        )
        self._producer.poll(0)

    def produce_shipment_status_change(self, data: dict):
        value = self._serializers["shipment_status_change"].serialize(data)
        self._producer.produce(
            topic=TOPICS["shipment_status_changes"],
            key=data["shipment_id"].encode(),
            value=value,
            callback=self._on_delivery,
        )
        self._producer.poll(0)

    def flush(self, timeout: float = 10):
        self._producer.flush(timeout)

    def close(self):
        self.flush()
