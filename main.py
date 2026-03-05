from fastapi import FastAPI, HTTPException, Depends
from models import (LockResponse, LockCreate, SecurityEventResponse,
                    SecurityEventCreate, ShipmentHealth, ShipmentStatus,
                    LockStatus, Severity, WARNING_EVENTS, CRITICAL_EVENTS)
from database import (get_locks, get_events, get_shipments,
                      new_lock_id, new_event_id, get_events_by_locks)
from datetime import datetime, timedelta
from typing import List

app = FastAPI()



@app.post("/locks", response_model=LockResponse, status_code=201)
def create_lock(lock: LockCreate, db:  dict = Depends(get_locks)):

    new_lock = {
        "id": new_lock_id(),
        "location": lock.location.model_dump(),
        "status": lock.status,
        "last_update": datetime.now()
    }    

    db[new_lock["id"]] = new_lock
    return new_lock


@app.get("/locks/{lock_id}", response_model=LockResponse)
def get_lock(lock_id: int , db:  dict = Depends(get_locks)):
    
    lock = db.get(lock_id)
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    return lock

@app.patch("/locks/{lock_id}/status", response_model=LockResponse)
def update_lock_status(lock_id: int, status: LockStatus = None, db:  dict = Depends(get_locks)):
    lock = db.get(lock_id)
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    lock["status"] = status
    lock["last_update"] = datetime.now()
    db[lock_id] = lock
    return lock


@app.post("/events", response_model=SecurityEventResponse, status_code=201)
def create_event(
    event: SecurityEventCreate, 
    events_db: dict = Depends(get_events),
    locks_db: dict = Depends(get_locks)
):

    if event.lock_id not in locks_db:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    new_event = {
        "id": new_event_id(),
        "lock_id": event.lock_id,
        "event_type":event.event_type,
        "severity": event.severity,
        "event_time": datetime.now()
    }

    events_db[new_event["id"]] = new_event
    return new_event


@app.get("/events", response_model=List[SecurityEventResponse])
def get_events( 
    events_db: dict = Depends(get_events),
    severity: Severity = None
):
    if severity:
        return [
            event for event in events_db.values()
            if event.get("severity") == severity.value 
        ]
    
    return [*events_db.values()]


@app.post("/shipments/{shipment_id}/locks/{lock_id}", status_code=200)
def assign_lock_to_shipment(
    shipment_id: str,
    lock_id: int,
    locks_db: dict = Depends(get_locks),
    shipments_db: dict = Depends(get_shipments)
):

    shipment = shipments_db.get(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    
    shipment = shipments_db[shipment_id]

    lock = db.get(lock_id)
    if not lock:
        raise HTTPException(status_code=404, detail="Lock not found")
    
    shipment.get("lock_ids").append(lock) 

    return shipment


@app.get("/shipments/{shipment_id}/health", response_model=ShipmentHealth)
def get_shipment_health(
    shipment_id: str,
    locks_db: dict = Depends(get_locks),
    events_db: dict = Depends(get_events),
    shipments_db: dict = Depends(get_shipments)
):

    shipment = shipments_db.get(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    lock_ids = shipment.get("lock_ids")
    locks = [l for l in locks_db.values()
        if l.get("id") in lock_ids
    ]
    count_locks = len(locks)
    locks_compromized = [c["id"] for c in locks
        if c.get("status") in [LockStatus.TAMPERED.value,LockStatus.OFFLINE.value]
    ]
    count_compromized = len(locks_compromized)
    events = get_events_by_locks(lock_ids)
   

    #Filter events from the past hour of this specific shipment and lock
    one_hour_earlier = datetime.now() - timedelta(hours=1)
    recent_events = [
        e for e in get_events_by_locks(locks_compromized)
        if e["event_time"] > one_hour_earlier
    ]

    event_types = {e["event_type"] for e in recent_events}
    if event_types & CRITICAL_EVENTS:
        overall_status = ShipmentStatus.CRITICAL
    elif event_types & WARNING_EVENTS: 
        overall_status = ShipmentStatus.WARNING
    else:
        overall_status = ShipmentStatus.OK

    count_critical_events = len([e for e in recent_events
        if e["event_type"] in CRITICAL_EVENTS
    ])

    return {
        "shipment_id": shipment_id,
        "total_locks": count_locks,
        "compromised_locks": count_compromized,
        "critical_events_last_hour": count_critical_events,
        "overall_status": overall_status    
    }
    


