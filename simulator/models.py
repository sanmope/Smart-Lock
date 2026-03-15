from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimLock:
    """Simulation state for a single smart lock device."""

    lock_id: str
    status: str  # active, inactive, tampered, offline
    latitude: float
    longitude: float
    battery: float = 100.0
    route_index: int = 0  # index of current segment start waypoint
    waypoint_progress: float = 0.0  # overall route progress [0, 1]
    shipment_id: Optional[str] = None
    is_incident: bool = False
    _battery_20_fired: bool = field(default=False, repr=False)
    _battery_10_fired: bool = field(default=False, repr=False)
    _battery_5_fired: bool = field(default=False, repr=False)


@dataclass
class SimShipment:
    """Simulation state for a shipment."""

    shipment_id: str
    lock_ids: list = field(default_factory=list)
    route_name: str = ""
    status: str = "in_transit"
