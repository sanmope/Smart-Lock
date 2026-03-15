from abc import ABC, abstractmethod
from typing import Optional


class OutputBase(ABC):
    """Abstract base class for all simulator output backends."""

    @abstractmethod
    async def setup(self) -> None:
        """Initialize the output backend (connections, files, etc.)."""
        ...

    @abstractmethod
    async def send_lock_created(
        self,
        lock_id: str,
        status: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        """Emit a lock-created event."""
        ...

    @abstractmethod
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
        """Emit a lock status change."""
        ...

    @abstractmethod
    async def send_event(
        self,
        event_id: str,
        lock_id: str,
        event_type: str,
        severity: str,
        timestamp_ms: int,
    ) -> None:
        """Emit a security event."""
        ...

    @abstractmethod
    async def send_location(
        self,
        lock_id: str,
        latitude: float,
        longitude: float,
        timestamp_ms: int,
    ) -> None:
        """Emit a location update."""
        ...

    @abstractmethod
    async def send_shipment_created(
        self,
        shipment_id: str,
        status: str,
        timestamp_ms: int,
    ) -> None:
        """Emit a shipment-created event."""
        ...

    @abstractmethod
    async def send_lock_assigned(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        """Emit a lock-assigned-to-shipment event."""
        ...

    @abstractmethod
    async def send_lock_released(
        self,
        lock_id: str,
        shipment_id: str,
        timestamp_ms: int,
    ) -> None:
        """Emit a lock-released-from-shipment event."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        ...
