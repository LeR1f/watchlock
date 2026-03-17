"""Main daemon: wires scanner, signal processor, state machine, and platform adapter."""

from __future__ import annotations

import asyncio
import logging

from unlock_pc.config import Config
from unlock_pc.platform import get_platform_adapter
from unlock_pc.platform.base import PlatformAdapter
from unlock_pc.scanner import BleScanner, RssiReading
from unlock_pc.signal_proc import ProximityState, RssiProcessor
from unlock_pc.state import Event, SessionState, StateMachine, proximity_to_event

logger = logging.getLogger(__name__)


class Daemon:
    """Main daemon orchestrating BLE scanning, signal processing, and lock/unlock."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._platform: PlatformAdapter = get_platform_adapter()
        self._rssi_queue: asyncio.Queue[RssiReading] = asyncio.Queue(maxsize=100)
        self._scanner = BleScanner(config.device_address, self._rssi_queue)
        self._processor = RssiProcessor(
            alpha=config.smoothing_alpha,
            tx_power=config.tx_power,
            path_loss_exponent=config.path_loss_exponent,
            unlock_max_distance=config.unlock_max_distance,
            lock_min_distance=config.lock_min_distance,
            absence_timeout=config.absence_timeout,
            max_rssi_jump=config.max_rssi_jump,
            stability_count=config.stability_readings,
        )
        self._state_machine = StateMachine()
        self._grace_task: asyncio.Task | None = None
        self._device_seen = False  # True once watch is seen NEAR in current session

    async def run(self) -> None:
        """Run the daemon until cancelled."""
        logger.info(
            "Starting daemon — target: %s (%s), unlock < %.1fm, lock > %.1fm",
            self._config.device_address,
            self._config.device_name,
            self._config.unlock_max_distance,
            self._config.lock_min_distance,
        )

        # Sync initial state with actual session state
        if await self._platform.is_session_locked():
            self._state_machine._state = SessionState.LOCKED
        else:
            self._state_machine._state = SessionState.UNLOCKED

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._scanner.run())
            tg.create_task(self._process_loop())
            tg.create_task(self._absence_check_loop())

    async def _process_loop(self) -> None:
        """Read RSSI from queue and drive state machine."""
        while True:
            try:
                reading = await asyncio.wait_for(
                    self._rssi_queue.get(), timeout=self._config.scan_interval * 2
                )
            except TimeoutError:
                continue

            proximity = self._processor.update(reading.rssi, reading.timestamp)
            distance = self._processor.estimated_distance

            logger.debug(
                "RSSI: %d dBm | smoothed: %.1f dBm | distance: %.2fm | proximity: %s",
                reading.rssi,
                self._processor.smoothed_rssi or 0,
                distance or 0,
                proximity.value,
            )

            await self._handle_proximity(proximity)

    async def _absence_check_loop(self) -> None:
        """Periodically check if device has been absent too long."""
        while True:
            await asyncio.sleep(self._config.scan_interval * 3)
            proximity = self._processor.check_absence()
            if proximity == ProximityState.ABSENT:
                await self._handle_proximity(proximity)

    async def _handle_proximity(self, proximity: ProximityState) -> None:
        """Convert proximity state to event and drive state machine."""
        # Track if watch has been seen during this unlocked session
        if proximity == ProximityState.NEAR:
            if not self._device_seen:
                logger.info("Device detected — proximity lock/unlock active")
            self._device_seen = True

        # Don't lock if watch was never seen this session
        if not self._device_seen and proximity in (ProximityState.FAR, ProximityState.ABSENT):
            return

        event = proximity_to_event(proximity)
        old_state = self._state_machine.state
        new_state = self._state_machine.process(event)

        if old_state == new_state:
            return

        match new_state:
            case SessionState.UNLOCKED:
                self._cancel_grace()
                if await self._platform.is_session_locked():
                    await self._platform.unlock_session()
                    dist = self._processor.estimated_distance
                    logger.info("Session unlocked (distance: %.2fm)", dist or 0)

            case SessionState.LOCKING:
                self._start_grace()

            case SessionState.LOCKED:
                self._device_seen = False  # Reset for next session
                if not await self._platform.is_session_locked():
                    await self._platform.lock_session()
                    logger.info("Session locked")

    def _start_grace(self) -> None:
        """Start the grace period timer."""
        self._cancel_grace()
        self._grace_task = asyncio.get_event_loop().create_task(self._grace_timer())
        logger.info("Grace period started (%.0fs)", self._config.grace_period)

    def _cancel_grace(self) -> None:
        """Cancel the grace period if running."""
        if self._grace_task and not self._grace_task.done():
            self._grace_task.cancel()
            self._grace_task = None
            logger.debug("Grace period cancelled")

    async def _grace_timer(self) -> None:
        """Wait for grace period then fire GRACE_EXPIRED."""
        try:
            await asyncio.sleep(self._config.grace_period)
            self._state_machine.process(Event.GRACE_EXPIRED)
            if not await self._platform.is_session_locked():
                await self._platform.lock_session()
                logger.info("Session locked (grace period expired)")
        except asyncio.CancelledError:
            pass


async def run_daemon(config: Config) -> None:
    """Entry point for running the daemon."""
    daemon = Daemon(config)
    await daemon.run()
