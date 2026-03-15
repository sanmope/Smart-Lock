import asyncio
import logging
import random
import uuid
from typing import List

from simulator.clock import SimClock
from simulator.config import SimulatorConfig
from simulator.models import SimLock, SimShipment
from simulator.outputs.base import OutputBase
from simulator.patterns import normal_tick, trigger_incident, check_route_deviation
from simulator.routes import ROUTES, get_random_route, interpolate

logger = logging.getLogger(__name__)


class Fleet:
    """Main orchestrator — manages simulated locks and shipments.

    Runs three concurrent async loops:
      1. Location loop  — updates lock GPS positions along routes
      2. Status loop    — periodically changes lock statuses
      3. Event loop     — generates security events and incidents
    """

    def __init__(self, config: SimulatorConfig, output: OutputBase):
        self.config = config
        self.output = output
        self.clock = SimClock(acceleration=config.acceleration)

        self.locks: List[SimLock] = []
        self.shipments: List[SimShipment] = []

        self._total_sent = 0
        self._running = False

    # ------------------------------------------------------------------
    # Setup — create entities and register them with the output backend
    # ------------------------------------------------------------------

    async def setup(self) -> None:
        """Create locks and shipments, assign locks to shipments."""
        logger.info(
            "Setting up fleet: %d locks, %d shipments",
            self.config.num_locks, self.config.num_shipments,
        )

        ts = self.clock.now_ms()

        # --- Create shipments ---
        for i in range(self.config.num_shipments):
            shipment_id = f"SHIP{i + 1:010d}"
            route_name = get_random_route()
            shipment = SimShipment(
                shipment_id=shipment_id,
                route_name=route_name,
                status="in_transit",
            )
            self.shipments.append(shipment)

            result = await self.output.send_shipment_created(
                shipment_id=shipment_id,
                status="stop",
                timestamp_ms=ts,
            )
            # If the API returns a server-assigned shipment_id, use that
            if result and isinstance(result, str):
                shipment.shipment_id = result

            self._total_sent += 1

        # --- Create locks and distribute across shipments ---
        for i in range(self.config.num_locks):
            lock_id = str(uuid.uuid4())

            # Assign to a shipment (round-robin)
            shipment = self.shipments[i % self.config.num_shipments]
            route = ROUTES[shipment.route_name]

            # Start at a random point along the route
            initial_progress = random.uniform(0.0, 0.3)
            lat, lon = interpolate(route, initial_progress, noise_m=0)

            lock = SimLock(
                lock_id=lock_id,
                status="active",
                latitude=lat,
                longitude=lon,
                shipment_id=shipment.shipment_id,
                waypoint_progress=initial_progress,
            )
            self.locks.append(lock)
            shipment.lock_ids.append(lock_id)

            # Register with output
            result = await self.output.send_lock_created(
                lock_id=lock_id,
                status="active",
                latitude=lat,
                longitude=lon,
                timestamp_ms=ts,
            )
            # If the API returns a server-assigned lock_id, update references
            if result and isinstance(result, str) and result != lock_id:
                old_id = lock_id
                lock.lock_id = result
                idx = shipment.lock_ids.index(old_id)
                shipment.lock_ids[idx] = result

            self._total_sent += 1

        # --- Assign locks to shipments ---
        for shipment in self.shipments:
            for lid in shipment.lock_ids:
                await self.output.send_lock_assigned(
                    lock_id=lid,
                    shipment_id=shipment.shipment_id,
                    timestamp_ms=ts,
                )
                self._total_sent += 1

        logger.info(
            "Fleet setup complete: %d locks across %d shipments (%d messages)",
            len(self.locks), len(self.shipments), self._total_sent,
        )

    # ------------------------------------------------------------------
    # Simulation loops
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the simulation for the configured duration."""
        self.clock.start()
        self._running = True

        logger.info(
            "Simulation started — duration=%ds, acceleration=%.1fx",
            self.config.duration, self.config.acceleration,
        )

        try:
            await asyncio.gather(
                self._location_loop(),
                self._status_loop(),
                self._event_loop(),
                self._progress_loop(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            logger.info(
                "Simulation ended — %d total messages sent", self._total_sent,
            )

    async def _location_loop(self) -> None:
        """Update each lock's position along its route at location_interval."""
        # Map lock -> its shipment's route for fast lookup
        lock_routes = {}
        for shipment in self.shipments:
            route = ROUTES[shipment.route_name]
            for lid in shipment.lock_ids:
                lock_routes[lid] = route

        while self.clock.elapsed() < self.config.duration:
            ts = self.clock.now_ms()

            # Speed: how much progress per location interval
            # A full route takes roughly `duration` virtual seconds
            progress_step = self.config.location_interval / self.config.duration

            tasks = []
            for lock in self.locks:
                route = lock_routes.get(lock.lock_id)
                if route is None:
                    continue

                # Advance along route
                lock.waypoint_progress = min(
                    1.0, lock.waypoint_progress + progress_step
                )
                lat, lon = interpolate(route, lock.waypoint_progress)
                lock.latitude = lat
                lock.longitude = lon

                tasks.append(self.output.send_location(
                    lock_id=lock.lock_id,
                    latitude=lat,
                    longitude=lon,
                    timestamp_ms=ts,
                ))

            if tasks:
                await asyncio.gather(*tasks)
                self._total_sent += len(tasks)

            await self.clock.sleep(self.config.location_interval)

    async def _status_loop(self) -> None:
        """Periodically change some lock statuses."""
        statuses = ["active", "inactive", "offline"]

        while self.clock.elapsed() < self.config.duration:
            await self.clock.sleep(self.config.status_interval)
            ts = self.clock.now_ms()

            tasks = []
            for lock in self.locks:
                # ~10% chance of status change per interval
                if random.random() > 0.10:
                    continue
                if lock.is_incident:
                    continue  # don't override incident status

                old_status = lock.status
                new_status = random.choice(
                    [s for s in statuses if s != old_status]
                )
                lock.status = new_status

                tasks.append(self.output.send_status_change(
                    lock_id=lock.lock_id,
                    status=new_status,
                    previous_status=old_status,
                    latitude=lock.latitude,
                    longitude=lock.longitude,
                    shipment_id=lock.shipment_id,
                    timestamp_ms=ts,
                ))

            if tasks:
                await asyncio.gather(*tasks)
                self._total_sent += len(tasks)

    async def _event_loop(self) -> None:
        """Every virtual second, check each lock for events and incidents."""
        # Track elapsed time for battery drain calculations
        last_elapsed = 0.0

        while self.clock.elapsed() < self.config.duration:
            await self.clock.sleep(1.0)  # 1 virtual second
            current_elapsed = self.clock.elapsed()
            tick_s = current_elapsed - last_elapsed
            last_elapsed = current_elapsed
            ts = self.clock.now_ms()

            tasks = []
            for lock in self.locks:
                # --- normal tick (battery, connection_lost) ---
                if random.random() < self.config.event_probability:
                    events = normal_tick(
                        lock, tick_s, ts,
                        late_event_ratio=self.config.late_event_ratio,
                    )
                    for evt in events:
                        tasks.append(self.output.send_event(
                            event_id=evt["event_id"],
                            lock_id=evt["lock_id"],
                            event_type=evt["event_type"],
                            severity=evt["severity"],
                            timestamp_ms=evt["timestamp_ms"],
                        ))

                # --- random incident ---
                if (not lock.is_incident
                        and random.random() < self.config.incident_probability):
                    events = trigger_incident(
                        lock, ts,
                        late_event_ratio=self.config.late_event_ratio,
                    )
                    for evt in events:
                        tasks.append(self.output.send_event(
                            event_id=evt["event_id"],
                            lock_id=evt["lock_id"],
                            event_type=evt["event_type"],
                            severity=evt["severity"],
                            timestamp_ms=evt["timestamp_ms"],
                        ))
                    # Also send a status change to tampered
                    tasks.append(self.output.send_status_change(
                        lock_id=lock.lock_id,
                        status="tampered",
                        previous_status=lock.status,
                        latitude=lock.latitude,
                        longitude=lock.longitude,
                        shipment_id=lock.shipment_id,
                        timestamp_ms=ts,
                    ))

            if tasks:
                await asyncio.gather(*tasks)
                self._total_sent += len(tasks)

    async def _progress_loop(self) -> None:
        """Log progress every 10 real seconds."""
        import time
        start = time.monotonic()
        while self.clock.elapsed() < self.config.duration:
            await asyncio.sleep(10.0)  # real seconds
            elapsed_virtual = self.clock.elapsed()
            pct = min(100.0, (elapsed_virtual / self.config.duration) * 100)
            real_elapsed = time.monotonic() - start
            logger.info(
                "Progress: %.1f%% | virtual=%.0fs/%.0fs | real=%.0fs | messages=%d",
                pct, elapsed_virtual, self.config.duration,
                real_elapsed, self._total_sent,
            )
