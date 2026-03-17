"""BLE scanner using bleak for continuous RSSI monitoring."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)


@dataclass
class RssiReading:
    address: str
    name: str | None
    rssi: int
    timestamp: float


class BleScanner:
    """Continuously scans for a target BLE device and reports RSSI readings."""

    def __init__(self, target_address: str, rssi_queue: asyncio.Queue[RssiReading]) -> None:
        self._target = target_address.upper()
        self._queue = rssi_queue
        self._scanner: BleakScanner | None = None
        self._running = False

    def _on_detection(self, device: BLEDevice, advertisement: AdvertisementData) -> None:
        """Callback when a BLE device is detected."""
        if device.address.upper() == self._target:
            reading = RssiReading(
                address=device.address,
                name=device.name,
                rssi=advertisement.rssi,
                timestamp=asyncio.get_event_loop().time(),
            )
            try:
                self._queue.put_nowait(reading)
            except asyncio.QueueFull:
                pass  # Drop reading if queue is full

    async def run(self) -> None:
        """Start continuous BLE scanning. Runs until stop() is called."""
        self._running = True
        logger.info("Starting BLE scan for %s", self._target)

        while self._running:
            try:
                self._scanner = BleakScanner(detection_callback=self._on_detection)
                await self._scanner.start()

                while self._running:
                    await asyncio.sleep(1.0)

            except Exception:
                logger.exception("BLE scanner error, restarting in 5s")
                await asyncio.sleep(5.0)
            finally:
                if self._scanner:
                    try:
                        await self._scanner.stop()
                    except Exception:
                        pass

    async def stop(self) -> None:
        """Stop the scanner."""
        self._running = False
        if self._scanner:
            try:
                await self._scanner.stop()
            except Exception:
                pass
        logger.info("BLE scanner stopped")


async def discover_devices(timeout: float = 10.0) -> list[RssiReading]:
    """Discover BLE devices in range. Returns a list of readings."""
    devices: list[RssiReading] = []
    seen: set[str] = set()

    def on_detection(device: BLEDevice, advertisement: AdvertisementData) -> None:
        if device.address not in seen:
            seen.add(device.address)
            devices.append(
                RssiReading(
                    address=device.address,
                    name=device.name,
                    rssi=advertisement.rssi,
                    timestamp=0.0,
                )
            )

    scanner = BleakScanner(detection_callback=on_detection)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    return sorted(devices, key=lambda d: d.rssi, reverse=True)
