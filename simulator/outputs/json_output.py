import json
import logging
import os
from typing import IO, Dict, Optional

from simulator.outputs.base import OutputBase

logger = logging.getLogger(__name__)

# File names mirror Kafka topic names
_FILES = {
    "lock_status": "smartlock.lock.status-changes.ndjson",
    "security_events": "smartlock.security.events.ndjson",
    "location_updates": "smartlock.lock.location-updates.ndjson",
    "shipment_status": "smartlock.shipment.status-changes.ndjson",
}


class JsonOutput(OutputBase):
    """Output backend that writes NDJSON files (one per topic)."""

    def __init__(self, output_dir: str = "./test_data"):
        self._output_dir = output_dir
        self._handles: Dict[str, IO] = {}
        self._sent = 0

    async def setup(self) -> None:
        os.makedirs(self._output_dir, exist_ok=True)
        for key, filename in _FILES.items():
            path = os.path.join(self._output_dir, filename)
            self._handles[key] = open(path, "w", encoding="utf-8")
        logger.info("JsonOutput writing to %s", self._output_dir)

    def _write(self, key: str, record: dict) -> None:
        fh = self._handles[key]
        fh.write(json.dumps(record, default=str) + "\n")
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
        self._write("lock_status", {
            "lock_id": lock_id,
            "action": "created",
            "status": status,
            "previous_status": None,
            "latitude": latitude,
            "longitude": longitude,
            "shipment_id": None,
            "timestamp": timestamp_ms,
        })

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
        self._write("lock_status", {
            "lock_id": lock_id,
            "action": "status_changed",
            "status": status,
            "previous_status": previous_status,
            "latitude": latitude,
            "longitude": longitude,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        })

    async def send_event(
        self,
        event_id: str,
        lock_id: str,
        event_type: str,
        severity: str,
        timestamp_ms: int,
    ) -> None:
        self._write("security_events", {
            "event_id": event_id,
            "lock_id": lock_id,
            "event_type": event_type,
            "severity": severity,
            "timestamp": timestamp_ms,
        })

    async def send_location(
        self,
        lock_id: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        self._write("location_updates", {
            "lock_id": lock_id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": timestamp_ms,
        })

    # ------------------------------------------------------------------
    # Shipment lifecycle
    # ------------------------------------------------------------------

    async def send_shipment_created(
        self,
        shipment_id: str,
        status: str,
        timestamp_ms: int,
    ) -> None:
        self._write("shipment_status", {
            "shipment_id": shipment_id,
            "action": "created",
            "status": status,
            "previous_status": None,
            "timestamp": timestamp_ms,
        })

    async def send_lock_assigned(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        self._write("lock_status", {
            "lock_id": lock_id,
            "action": "assigned",
            "status": None,
            "previous_status": None,
            "latitude": None,
            "longitude": None,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        })

    async def send_lock_released(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        self._write("lock_status", {
            "lock_id": lock_id,
            "action": "released",
            "status": None,
            "previous_status": None,
            "latitude": None,
            "longitude": None,
            "shipment_id": shipment_id,
            "timestamp": timestamp_ms,
        })

    # ------------------------------------------------------------------

    @property
    def messages_sent(self) -> int:
        return self._sent

    async def close(self) -> None:
        for key, fh in self._handles.items():
            fh.close()
        self._handles.clear()
        logger.info("JsonOutput closed — %d lines written to %s",
                     self._sent, self._output_dir)
