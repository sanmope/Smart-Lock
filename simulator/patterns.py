import math
import random
import uuid
import time
from typing import List, Dict

from simulator.models import SimLock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EVENT_TYPES = ["unlock_attempt", "tamper_detected", "battery_low",
               "location_deviation", "connection_lost"]
SEVERITIES = ["low", "medium", "high", "critical"]

# Battery thresholds (percentage)
_BATTERY_THRESHOLDS = [
    (20, "_battery_20_fired"),
    (10, "_battery_10_fired"),
    (5,  "_battery_5_fired"),
]


def _make_event(
    lock: SimLock,
    event_type: str,
    severity: str,
    timestamp_ms: int,
    late_event_ratio: float = 0.05,
) -> Dict:
    """Build an event dict, optionally applying a late-event timestamp shift."""
    ts = timestamp_ms
    if random.random() < late_event_ratio:
        # Subtract 1-15 minutes (in ms) to simulate late/out-of-order arrival
        delay_ms = random.randint(60_000, 900_000)
        ts = max(0, ts - delay_ms)

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "severity": severity,
        "lock_id": lock.lock_id,
        "timestamp_ms": ts,
    }


# ---------------------------------------------------------------------------
# Normal tick — called every event-loop cycle for each lock
# ---------------------------------------------------------------------------

def normal_tick(
    lock: SimLock,
    elapsed_s: float,
    timestamp_ms: int,
    late_event_ratio: float = 0.05,
) -> List[Dict]:
    """Simulate normal per-tick behaviour for a lock.

    * Battery drains ~1% per 10 virtual minutes.
    * Emits battery_low events at 20%, 10%, 5% thresholds.
    * Random connection_lost at 0.5% probability per tick.

    Returns a list of event dicts (may be empty).
    """
    events: List[Dict] = []

    # --- battery drain ---
    # 1% per 600 virtual seconds => drain_per_s = 1/600
    drain = elapsed_s * (1.0 / 600.0)
    lock.battery = max(0.0, lock.battery - drain)

    for threshold, flag_attr in _BATTERY_THRESHOLDS:
        if lock.battery <= threshold and not getattr(lock, flag_attr):
            setattr(lock, flag_attr, True)
            severity = "critical" if threshold <= 5 else (
                "high" if threshold <= 10 else "medium"
            )
            events.append(_make_event(
                lock, "battery_low", severity, timestamp_ms, late_event_ratio,
            ))

    # --- random connection_lost ---
    if random.random() < 0.005:
        events.append(_make_event(
            lock, "connection_lost", "medium", timestamp_ms, late_event_ratio,
        ))

    return events


# ---------------------------------------------------------------------------
# Incident — triggered randomly or externally
# ---------------------------------------------------------------------------

def trigger_incident(
    lock: SimLock,
    timestamp_ms: int,
    late_event_ratio: float = 0.05,
) -> List[Dict]:
    """Simulate a security incident on the lock.

    Sets the lock status to 'tampered' and generates a burst of 15 events
    (mix of tamper_detected and unlock_attempt) with high/critical severity.

    Returns the list of generated events.
    """
    lock.status = "tampered"
    lock.is_incident = True

    events: List[Dict] = []
    for i in range(15):
        event_type = random.choice(["tamper_detected", "unlock_attempt"])
        severity = random.choice(["high", "critical"])
        # Spread burst events over a small time window (0-30 seconds)
        offset_ms = random.randint(0, 30_000)
        events.append(_make_event(
            lock, event_type, severity, timestamp_ms + offset_ms,
            late_event_ratio,
        ))

    return events


# ---------------------------------------------------------------------------
# Route deviation check
# ---------------------------------------------------------------------------

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in metres between two lat/lon points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def check_route_deviation(
    lock: SimLock,
    expected_lat: float,
    expected_lon: float,
    timestamp_ms: int,
    threshold_m: float = 500.0,
    late_event_ratio: float = 0.05,
) -> List[Dict]:
    """If the lock has deviated >threshold_m from the expected route position,
    generate a location_deviation event.

    Returns a list with zero or one event dict.
    """
    dist = _haversine_m(lock.latitude, lock.longitude, expected_lat, expected_lon)
    if dist > threshold_m:
        return [_make_event(
            lock, "location_deviation", "high", timestamp_ms, late_event_ratio,
        )]
    return []
