"""
Kafka Consumer Service: reads from all 4 topics and writes to PostgreSQL.

Run as a standalone process:
    python -m kafka.consumer
"""

import logging
import signal
import sys
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError

from kafka.config import CONSUMER_CONFIG, TOPICS
from kafka.serializers import AvroDeserializer
from database import SessionLocal, engine
from db_models import Base, Lock, Location, SecurityEvent, Shipment, LockAssignment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("kafka.consumer")

# Deserializers per topic
DESERIALIZERS = {
    TOPICS["lock_status_changes"]: AvroDeserializer("lock_status_change"),
    TOPICS["security_events"]: AvroDeserializer("security_event"),
    TOPICS["location_updates"]: AvroDeserializer("location_update"),
    TOPICS["shipment_status_changes"]: AvroDeserializer("shipment_status_change"),
}

MAX_RETRIES = 3
_running = True


def _ts_to_datetime(ts_millis) -> datetime:
    if isinstance(ts_millis, datetime):
        return ts_millis.replace(tzinfo=None)
    return datetime.fromtimestamp(ts_millis / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def handle_lock_status_change(data: dict, session):
    action = data["action"]
    lock_id = data["lock_id"]
    ts = _ts_to_datetime(data["timestamp"])

    if action == "created":
        lock = Lock(
            id=lock_id,
            status=data["status"],
            last_update=ts,
        )
        session.add(lock)
        session.flush()
        if data.get("latitude") is not None and data.get("longitude") is not None:
            loc = Location(lock_id=lock_id, latitude=data["latitude"], longitude=data["longitude"])
            session.add(loc)

    elif action == "status_changed":
        lock = session.query(Lock).filter(Lock.id == lock_id).first()
        if lock:
            lock.status = data["status"]
            lock.last_update = ts
        else:
            logger.warning("Lock %s not found for status_changed", lock_id)

    elif action == "assigned":
        shipment_id_str = data.get("shipment_id")
        if not shipment_id_str:
            logger.warning("No shipment_id in assigned event for lock %s", lock_id)
            return
        shipment = session.query(Shipment).filter(Shipment.shipment_id == shipment_id_str).first()
        if not shipment:
            logger.warning("Shipment %s not found for assignment of lock %s", shipment_id_str, lock_id)
            return
        active = session.query(LockAssignment).filter(
            LockAssignment.lock_id == lock_id,
            LockAssignment.released_at == None,
        ).first()
        if active:
            logger.warning("Lock %s already assigned, skipping", lock_id)
            return
        assignment = LockAssignment(lock_id=lock_id, shipment_id=shipment.id, assigned_at=ts)
        session.add(assignment)

    elif action == "released":
        shipment_id_str = data.get("shipment_id")
        if not shipment_id_str:
            return
        shipment = session.query(Shipment).filter(Shipment.shipment_id == shipment_id_str).first()
        if not shipment:
            logger.warning("Shipment %s not found for release of lock %s", shipment_id_str, lock_id)
            return
        active = session.query(LockAssignment).filter(
            LockAssignment.shipment_id == shipment.id,
            LockAssignment.lock_id == lock_id,
            LockAssignment.released_at == None,
        ).first()
        if active:
            active.released_at = ts
        else:
            logger.warning("No active assignment for lock %s in shipment %s", lock_id, shipment_id_str)


def handle_security_event(data: dict, session):
    event = SecurityEvent(
        id=data["event_id"],
        lock_id=data["lock_id"],
        event_type=data["event_type"],
        severity=data["severity"],
        event_time=_ts_to_datetime(data["timestamp"]),
    )
    session.add(event)


def handle_location_update(data: dict, session):
    lock_id = data["lock_id"]
    loc = session.query(Location).filter(Location.lock_id == lock_id).first()
    if loc:
        loc.latitude = data["latitude"]
        loc.longitude = data["longitude"]
    else:
        loc = Location(lock_id=lock_id, latitude=data["latitude"], longitude=data["longitude"])
        session.add(loc)


def handle_shipment_status_change(data: dict, session):
    action = data["action"]
    shipment_id = data["shipment_id"]
    ts = _ts_to_datetime(data["timestamp"])

    if action == "created":
        shipment = Shipment(
            shipment_id=shipment_id,
            status=data["status"],
            last_update=ts,
        )
        session.add(shipment)

    elif action == "status_changed":
        shipment = session.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
        if shipment:
            shipment.status = data["status"]
            shipment.last_update = ts
        else:
            logger.warning("Shipment %s not found for status_changed", shipment_id)


HANDLERS = {
    TOPICS["lock_status_changes"]: handle_lock_status_change,
    TOPICS["security_events"]: handle_security_event,
    TOPICS["location_updates"]: handle_location_update,
    TOPICS["shipment_status_changes"]: handle_shipment_status_change,
}


def run_consumer():
    global _running

    Base.metadata.create_all(bind=engine)

    consumer = Consumer(CONSUMER_CONFIG)
    consumer.subscribe(list(TOPICS.values()))
    logger.info("Consumer subscribed to topics: %s", list(TOPICS.values()))

    def shutdown(signum, frame):
        global _running
        logger.info("Shutting down consumer...")
        _running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while _running:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            logger.error("Consumer error: %s", msg.error())
            continue

        topic = msg.topic()
        deserializer = DESERIALIZERS.get(topic)
        handler = HANDLERS.get(topic)

        if not deserializer or not handler:
            logger.warning("No handler for topic %s", topic)
            continue

        retries = 0
        while retries < MAX_RETRIES:
            session = SessionLocal()
            try:
                data = deserializer.deserialize(msg.value())
                handler(data, session)
                session.commit()
                consumer.commit(message=msg)
                break
            except Exception:
                session.rollback()
                retries += 1
                logger.exception("Error processing message from %s (attempt %d/%d)", topic, retries, MAX_RETRIES)
            finally:
                session.close()

        if retries >= MAX_RETRIES:
            logger.error("Message from %s dropped after %d retries: key=%s", topic, MAX_RETRIES, msg.key())

    consumer.close()
    logger.info("Consumer stopped.")


if __name__ == "__main__":
    run_consumer()
