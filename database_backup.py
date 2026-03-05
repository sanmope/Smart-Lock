from datetime import datetime
from typing import Dict, List
from models import Severity

# Simulamos tablas como dicts
locks: Dict[int, dict] = {}
events: Dict[int, dict] = {}
shipments: Dict[str, dict] = {
    "SHIP001": {"shipment_id": "SHIP001", "lock_ids": []},
    "SHIP002": {"shipment_id": "SHIP002", "lock_ids": []},
}

# Contadores para IDs autoincrementales
lock_counter = 0
event_counter = 0

def get_locks() -> Dict[int, dict]: 
    return locks

def get_events() -> Dict[int, dict]:
    return events

def get_events_by_locks(locks: List[int]) -> List[events]:
    events_by_locks = [e for e in events.values()
        if e.get("lock_id") in locks
    ]
    return events_by_locks

def get_events_by_severity(severity: Severity) -> Dict[int, dict]:
    events["severity"]
    return events

def get_shipments()-> Dict[str, dict]:
    return shipments

def new_lock_id() -> int:
    global lock_counter
    lock_counter += 1
    return lock_counter
    
def new_event_id() -> int:
    global event_counter
    event_counter += 1
    return event_counter