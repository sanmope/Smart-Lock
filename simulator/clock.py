import asyncio
import time
from datetime import datetime, timedelta


class SimClock:
    """Virtual clock with time acceleration for the simulator.

    If acceleration=10, one virtual hour passes in 6 real minutes.
    """

    def __init__(self, acceleration: float = 1.0):
        self.acceleration = max(acceleration, 0.01)
        self._real_start: float = 0.0
        self._virtual_start: datetime = datetime.utcnow()

    def start(self) -> None:
        """Record the real start time and virtual epoch."""
        self._real_start = time.monotonic()
        self._virtual_start = datetime.utcnow()

    def elapsed(self) -> float:
        """Return virtual seconds elapsed since start."""
        real_elapsed = time.monotonic() - self._real_start
        return real_elapsed * self.acceleration

    def now(self) -> datetime:
        """Return the current accelerated virtual datetime."""
        return self._virtual_start + timedelta(seconds=self.elapsed())

    def now_ms(self) -> int:
        """Return the current virtual time as epoch milliseconds."""
        dt = self.now()
        return int(dt.timestamp() * 1000)

    async def sleep(self, virtual_seconds: float) -> None:
        """Sleep for virtual_seconds of virtual time (real sleep is shorter
        when acceleration > 1)."""
        real_seconds = virtual_seconds / self.acceleration
        if real_seconds > 0:
            await asyncio.sleep(real_seconds)
