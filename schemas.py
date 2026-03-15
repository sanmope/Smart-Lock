from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    CRITICAL = "critical"


class EventType(str, Enum):
    UNLOCK_ATTEMPT = "unlock_attempt"
    TAMPER_DETECTED = "tamper_detected"
    BATTERY_LOW = "battery_low"
    LOCATION_DEVIATION = "location_deviation"
    CONNECTION_LOST = "connection_lost"


WARNING_EVENTS = {EventType.BATTERY_LOW, EventType.CONNECTION_LOST}
CRITICAL_EVENTS = {EventType.UNLOCK_ATTEMPT, EventType.TAMPER_DETECTED, EventType.LOCATION_DEVIATION}


class HealthStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90, description="Latitud del dispositivo")
    longitude: float = Field(ge=-180, le=180, description="Longitud del dispositivo")


class LockStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TAMPERED = "tampered"
    OFFLINE = "offline"


class ShipmentStatus(str, Enum):
    IN_TRANSIT = "in_transit"
    LOADING = "loading"
    AT_DESTINATION = "at_destination"
    STOP = "stop"


class LockCreate(BaseModel):
    location: Location
    status: LockStatus = Field(default=LockStatus.ACTIVE, description="El estado del dispositivo de lock.")


class LockResponse(BaseModel):
    id: str
    location: Optional[Location] = None
    status: LockStatus
    last_update: datetime


class AcceptedResponse(BaseModel):
    id: str
    status: str = "accepted"


class ShipmentCreate(BaseModel):
    status: ShipmentStatus


class ShipmentResponse(BaseModel):
    id: int
    shipment_id: str
    status: ShipmentStatus
    last_update: datetime


class ShipmentAcceptedResponse(BaseModel):
    shipment_id: str
    status: str = "accepted"


class SecurityEventCreate(BaseModel):
    lock_id: str
    event_type: EventType = Field(..., description="El tipo de evento de seguridad.")
    severity: Severity = Field(default=Severity.MEDIUM, description="La severidad del evento de seguridad.")


class SecurityEventResponse(BaseModel):
    id: str
    lock_id: str
    event_type: EventType
    severity: Severity
    event_time: datetime


class ShipmentHealth(BaseModel):
    shipment_id: str
    total_locks: int
    compromised_locks: int
    critical_events_last_hour: int
    overall_status: HealthStatus
