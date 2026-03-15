import logging
from typing import Optional

import httpx

from simulator.outputs.base import OutputBase

logger = logging.getLogger(__name__)


class ApiOutput(OutputBase):
    """Output backend that sends traffic to the FastAPI REST endpoints.

    Note: The API does not expose a dedicated location-update endpoint.
    Location updates are logged but not sent in API mode.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._sent = 0

    async def setup(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        )
        logger.info("ApiOutput connected to %s", self.base_url)

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
    ) -> Optional[str]:
        """POST /locks — returns the server-assigned lock_id."""
        resp = await self._client.post("/locks", json={
            "location": {"latitude": latitude, "longitude": longitude},
            "status": status,
        })
        resp.raise_for_status()
        data = resp.json()
        self._sent += 1
        return data.get("id")

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
        resp = await self._client.patch(
            f"/locks/{lock_id}/status",
            params={"status": status},
        )
        resp.raise_for_status()
        self._sent += 1

    async def send_event(
        self,
        event_id: str,
        lock_id: str,
        event_type: str,
        severity: str,
        timestamp_ms: int,
    ) -> None:
        resp = await self._client.post("/events", json={
            "lock_id": lock_id,
            "event_type": event_type,
            "severity": severity,
        })
        resp.raise_for_status()
        self._sent += 1

    async def send_location(
        self,
        lock_id: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        # The API does not have a dedicated location-update endpoint.
        # Location updates are only available in kafka and json output modes.
        pass

    # ------------------------------------------------------------------
    # Shipment lifecycle
    # ------------------------------------------------------------------

    async def send_shipment_created(
        self,
        shipment_id: str,
        status: str,
        timestamp_ms: int,
    ) -> Optional[str]:
        """POST /shipments — returns the server-assigned shipment_id."""
        resp = await self._client.post("/shipments", json={
            "status": status,
        })
        resp.raise_for_status()
        data = resp.json()
        self._sent += 1
        return data.get("shipment_id")

    async def send_lock_assigned(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        resp = await self._client.post(
            f"/shipments/{shipment_id}/locks/{lock_id}",
        )
        resp.raise_for_status()
        self._sent += 1

    async def send_lock_released(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        resp = await self._client.patch(
            f"/shipments/{shipment_id}/locks/{lock_id}/release",
        )
        resp.raise_for_status()
        self._sent += 1

    # ------------------------------------------------------------------

    @property
    def messages_sent(self) -> int:
        return self._sent

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            logger.info("ApiOutput closed — %d messages sent", self._sent)
