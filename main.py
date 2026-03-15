import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List

from schemas import (
    LockCreate, LockResponse, SecurityEventCreate, SecurityEventResponse,
    ShipmentResponse, ShipmentCreate, ShipmentHealth, ShipmentStatus,
    HealthStatus, LockStatus, Severity, WARNING_EVENTS, CRITICAL_EVENTS,
    AcceptedResponse, ShipmentAcceptedResponse,
)
from database import get_db, engine
from db_models import Base, Lock, SecurityEvent, Shipment, LockAssignment, Location
from kafka.producer import KafkaProducerService


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    KafkaProducerService.get_instance()
    yield
    KafkaProducerService.reset()


app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# Write endpoints — produce to Kafka, return 202 Accepted
# ---------------------------------------------------------------------------

@app.post("/locks", response_model=AcceptedResponse, status_code=202)
def create_lock(lock: LockCreate):
    lock_id = str(uuid.uuid4())
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_lock_status_change({
        "lock_id": lock_id,
        "action": "created",
        "status": LockStatus.INACTIVE.value,
        "previous_status": None,
        "latitude": lock.location.latitude,
        "longitude": lock.location.longitude,
        "shipment_id": None,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"id": lock_id, "status": "accepted"}


@app.patch("/locks/{lock_id}/status", response_model=AcceptedResponse, status_code=202)
def update_lock_status(lock_id: str, status: LockStatus):
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_lock_status_change({
        "lock_id": lock_id,
        "action": "status_changed",
        "status": status.value,
        "previous_status": None,
        "latitude": None,
        "longitude": None,
        "shipment_id": None,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"id": lock_id, "status": "accepted"}


@app.post("/events", response_model=AcceptedResponse, status_code=202)
def create_event(event: SecurityEventCreate):
    event_id = str(uuid.uuid4())
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_security_event({
        "event_id": event_id,
        "lock_id": event.lock_id,
        "event_type": event.event_type.value,
        "severity": event.severity.value,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"id": event_id, "status": "accepted"}


@app.post("/shipments", response_model=ShipmentAcceptedResponse, status_code=202)
def create_shipment(shipment: ShipmentCreate, db: Session = Depends(get_db)):
    # Generate shipment_id (SHIP0000000001 format) — read last from DB for sequencing
    from sqlalchemy import desc
    last = db.query(Shipment).order_by(desc(Shipment.id)).first()
    number = (last.id + 1) if last else 1
    shipment_id = f"SHIP{number:010d}"
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_shipment_status_change({
        "shipment_id": shipment_id,
        "action": "created",
        "status": ShipmentStatus.STOP.value,
        "previous_status": None,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"shipment_id": shipment_id, "status": "accepted"}


@app.post("/shipments/{shipment_id}/locks/{lock_id}", status_code=202)
def assign_lock_to_shipment(shipment_id: str, lock_id: str):
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_lock_status_change({
        "lock_id": lock_id,
        "action": "assigned",
        "status": None,
        "previous_status": None,
        "latitude": None,
        "longitude": None,
        "shipment_id": shipment_id,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"message": f"Lock {lock_id} assignment to {shipment_id} accepted", "status": "accepted"}


@app.patch("/shipments/{shipment_id}/locks/{lock_id}/release", status_code=202)
def release_lock_from_shipment(shipment_id: str, lock_id: str):
    now = datetime.utcnow()

    KafkaProducerService.get_instance().produce_lock_status_change({
        "lock_id": lock_id,
        "action": "released",
        "status": None,
        "previous_status": None,
        "latitude": None,
        "longitude": None,
        "shipment_id": shipment_id,
        "timestamp": int(now.timestamp() * 1000),
    })

    return {"message": f"Lock {lock_id} release from {shipment_id} accepted", "status": "accepted"}


# ---------------------------------------------------------------------------
# Read endpoints — query PostgreSQL (fed by Kafka consumer)
# ---------------------------------------------------------------------------

@app.get("/locks/{lock_id}", response_model=LockResponse)
def get_lock(lock_id: str, db: Session = Depends(get_db)):
    lock = db.query(Lock).filter(Lock.id == lock_id).first()
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    return lock


@app.get("/events", response_model=List[SecurityEventResponse])
def get_events(db: Session = Depends(get_db), severity: Severity = None):
    if severity:
        return db.query(SecurityEvent).filter(SecurityEvent.severity == severity.value).all()
    return db.query(SecurityEvent).all()


@app.get("/shipments/{shipment_id}", response_model=ShipmentResponse)
def get_shipment(shipment_id: str, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment


@app.get("/shipments/{shipment_id}/health", response_model=ShipmentHealth)
def get_shipment_health(shipment_id: str, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    locks = db.query(Lock).join(LockAssignment).filter(
        LockAssignment.shipment_id == shipment.id,
        LockAssignment.released_at == None,
    ).all()

    count_locks = len(locks)
    if count_locks == 0:
        raise HTTPException(status_code=404, detail="No Locks Assigned")

    locks_compromized = [c for c in locks
        if c.status in [LockStatus.TAMPERED.value, LockStatus.OFFLINE.value]
    ]
    locks_compromized_ids = [l.id for l in locks_compromized]
    count_compromized = len(locks_compromized_ids)

    one_hour_earlier = datetime.utcnow() - timedelta(hours=1)
    recent_events = db.query(SecurityEvent).join(Lock).filter(
        SecurityEvent.lock_id.in_(locks_compromized_ids),
        SecurityEvent.event_time > one_hour_earlier,
    ).all()

    event_types = {e.event_type for e in recent_events}
    if event_types & CRITICAL_EVENTS:
        overall_status = HealthStatus.CRITICAL.value
    elif event_types & WARNING_EVENTS:
        overall_status = HealthStatus.WARNING.value
    else:
        overall_status = HealthStatus.OK.value

    count_critical_events = len([e for e in recent_events if e.event_type in CRITICAL_EVENTS])

    return {
        "shipment_id": shipment_id,
        "total_locks": count_locks,
        "compromised_locks": count_compromized,
        "critical_events_last_hour": count_critical_events,
        "overall_status": overall_status,
    }
