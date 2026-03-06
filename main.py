from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import desc
from schemas import (LockCreate, LockResponse, SecurityEventCreate,
                     SecurityEventResponse, ShipmentResponse, ShipmentCreate, ShipmentHealth, ShipmentStatus, HealthStatus,
                     LockStatus, Severity, WARNING_EVENTS, CRITICAL_EVENTS)
from database import get_db, engine
from db_models import Base, Lock, SecurityEvent, Shipment, LockAssignment, Location
from datetime import datetime, timedelta
from typing import List

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI()



@app.post("/locks", response_model=LockResponse, status_code=201)
def create_lock(lock: LockCreate, db:  Session = Depends(get_db)):

    new_lock = Lock(
        status=LockStatus.INACTIVE,
        last_update=datetime.now()
    )
    new_location = Location(
        latitude=lock.location.latitude,
        longitude=lock.location.longitude,
        lock=new_lock  # SQLAlchemy conecta los dos automáticamente
    )

    db.add(new_lock)
    db.add(new_location)
    db.commit()
    db.refresh(new_lock)
    
    return new_lock


@app.get("/locks/{lock_id}", response_model=LockResponse)
def get_lock(lock_id: int , db:  Session = Depends(get_db)):
    
    lock = db.query(Lock).filter(Lock.id == lock_id).first()

    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    return lock

@app.patch("/locks/{lock_id}/status", response_model=LockResponse)
def update_lock_status(lock_id: int, status: LockStatus = None, db:  Session = Depends(get_db)):
    
    lock = db.query(Lock).filter(Lock.id == lock_id).first()
    
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")

    lock.status = status
    lock.last_update = datetime.now()

    db.commit()
    db.refresh(lock)

    return lock


@app.post("/events", response_model=SecurityEventResponse, status_code=201)
def create_event(
    event: SecurityEventCreate, 
    db: Session = Depends(get_db)
):
    lock = db.query(Lock).filter(Lock.id == event.lock_id).first()
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    new_event = SecurityEvent(
        lock_id = event.lock_id,
        event_type = event.event_type,
        severity = event.severity,
        event_time = datetime.now()
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return new_event


@app.get("/events", response_model=List[SecurityEventResponse])
def get_events( 
    db: Session = Depends(get_db),
    severity: Severity = None
):

    if severity:
        return db.query(SecurityEvent).filter(SecurityEvent.severity == severity.value).all()
    
    return db.query(SecurityEvent).all()


@app.post("/shipments", response_model=ShipmentResponse, status_code=201)
def create_shipment(
    shipment: ShipmentCreate, 
    db:  Session = Depends(get_db)):

    prefix = "SHIP"
    total_width = 10
    last_shipment = db.query(Shipment).order_by(desc(Shipment.id)).first()
    number = (last_shipment.id + 1) if last_shipment else 1
    shipment_number = f"{prefix}{number:0{total_width}d}"

    new_shipment = Shipment(
        status = ShipmentStatus.STOP,
        last_update = datetime.now(),
        shipment_id = shipment_number
    )

    db.add(new_shipment)
    db.commit()
    db.refresh(new_shipment)
    
    return new_shipment

@app.post("/shipments/{shipment_id}/locks/{lock_id}", status_code=200)
def assign_lock_to_shipment(
    shipment_id: str,
    lock_id: int,
    db: Session = Depends(get_db)
):

    shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    lock = db.query(Lock).filter(Lock.id == lock_id).first()
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    active_assignment = db.query(LockAssignment).filter(
        LockAssignment.lock_id == lock_id,
        LockAssignment.released_at == None
    ).first()
    if active_assignment:
        raise HTTPException(status_code=400, detail="Lock already assigned to a shipment")

    new_lockAssignment = LockAssignment(
        lock_id = lock_id,
        shipment_id = shipment.id
    )

    db.add(new_lockAssignment)
    db.commit()
    
    return {"message": f"Lock {lock_id} assigned to shipment {shipment_id}"}


@app.patch("/shipments/{shipment_id}/locks/{lock_id}/release", status_code=200)
def release_lock_from_shipment(
    shipment_id: str,
    lock_id: int,
    db: Session = Depends(get_db)
):

    shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    lock = db.query(Lock).filter(Lock.id == lock_id).first()
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    active_assignment = db.query(LockAssignment).filter(
        LockAssignment.shipment_id == shipment.id,
        LockAssignment.lock_id == lock_id,
        LockAssignment.released_at == None
    ).first()

    if not active_assignment:
        raise HTTPException(status_code=404, detail="No Assignment assigned to a shipment")
    
    active_assignment.released_at = datetime.now()

    db.commit()
    db.refresh(active_assignment)

    return {"message": f"Lock {lock_id} release at: {active_assignment.released_at}"}




@app.get("/shipments/{shipment_id}/health", response_model=ShipmentHealth)
def get_shipment_health(
    shipment_id: str,
    db: Session = Depends(get_db)
):

    shipment = db.query(Shipment).filter(Shipment.shipment_id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    locks = db.query(Lock).join(LockAssignment).filter(
    LockAssignment.shipment_id == shipment.id,
    LockAssignment.released_at == None
    ).all()
    
    count_locks = len(locks)
    
    if count_locks == 0:
        raise HTTPException(status_code=404, detail="No Locks Assigned")

    
    locks_compromized = [c for c in locks
        if c.status in [LockStatus.TAMPERED.value,LockStatus.OFFLINE.value]
    ]

    locks_compromized = [l.id for l in locks_compromized]

    count_compromized = len(locks_compromized)
    #Filter events from the past hour of this specific shipment and lock
    one_hour_earlier = datetime.now() - timedelta(hours=1)

    recent_events = db.query(SecurityEvent).join(Lock).filter(
        SecurityEvent.lock_id.in_(locks_compromized),
        SecurityEvent.event_time > one_hour_earlier
    ).all()


    event_types = {e.event_type for e in recent_events}
    if event_types & CRITICAL_EVENTS:
        overall_status = HealthStatus.CRITICAL.value
    elif event_types & WARNING_EVENTS: 
        overall_status = HealthStatus.WARNING.value
    else:
        overall_status = HealthStatus.OK.value

    count_critical_events = len([e for e in recent_events
        if e.event_type in CRITICAL_EVENTS
    ])

    return {
        "shipment_id": shipment_id,
        "total_locks": count_locks,
        "compromised_locks": count_compromized,
        "critical_events_last_hour": count_critical_events,
        "overall_status": overall_status
    }

    return new_shipmentHealth
    


