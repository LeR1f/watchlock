"""BLE scanner using bleak for continuous RSSI monitoring."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)

# Fallback RSSI when device is connected but real RSSI can't be read from D-Bus.
# -50 dBm roughly corresponds to ~1-2m distance.
_CONNECTED_FALLBACK_RSSI = -50


@dataclass
class RssiReading:
    address: str
    name: str | None
    rssi: int
    timestamp: float
    via_connection: bool = field(default=False, repr=False)


async def _get_paired_devices() -> list[tuple[str, str]]:
    """Get paired devices from bluetoothctl."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", "devices",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        devices = []
        for line in stdout.decode().strip().splitlines():
            parts = line.split(maxsplit=2)
            if len(parts) >= 3 and parts[0] == "Device":
                devices.append((parts[1], parts[2]))
        return devices
    except Exception:
        return []


async def _read_bluez_rssi(address: str) -> int | None:
    """Read RSSI from BlueZ D-Bus for a device."""
    addr_path = address.upper().replace(":", "_")
    device_path = f"/org/bluez/hci0/dev_{addr_path}"
    try:
        proc = await asyncio.create_subprocess_exec(
            "busctl", "get-property", "org.bluez", device_path,
            "org.bluez.Device1", "RSSI",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            # Output format: "n -55" (variant type n = int16)
            parts = stdout.decode().strip().split()
            if len(parts) == 2:
                return int(parts[1])
    except Exception:
        pass
    return None


async def _try_connected_rssi(address: str, timeout: float = 5.0) -> int | None:
    """Connect to a device via bluetoothctl and try to read its RSSI.

    Uses bluetoothctl connect which works for both classic BT and BLE devices.
    Returns real RSSI from D-Bus if available, a fallback value if connected
    but RSSI unreadable, or None if connection fails (device not nearby).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "bluetoothctl", "connect", address,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            logger.debug("Connection to %s timed out", address)
            return None

        if b"Connection successful" in stdout:
            await asyncio.sleep(0.5)
            rssi = await _read_bluez_rssi(address)
            return rssi if rssi is not None else _CONNECTED_FALLBACK_RSSI

    except Exception as e:
        logger.debug("Cannot connect to %s: %s", address, e)
    return None


class BleScanner:
    """Continuously scans for a target BLE device and reports RSSI readings.

    Uses BLE advertisements as the primary source. Falls back to direct GATT
    connections for paired devices that stop advertising.
    """

    _ADV_FALLBACK_DELAY = 10.0  # seconds without advertisement before trying connection

    def __init__(self, target_address: str, rssi_queue: asyncio.Queue[RssiReading]) -> None:
        self._target = target_address.upper()
        self._queue = rssi_queue
        self._scanner: BleakScanner | None = None
        self._running = False
        self._last_adv_time: float = 0.0

    def _on_detection(self, device: BLEDevice, advertisement: AdvertisementData) -> None:
        """Callback when a BLE device is detected via advertisement."""
        if device.address.upper() == self._target:
            now = asyncio.get_event_loop().time()
            self._last_adv_time = now
            reading = RssiReading(
                address=device.address,
                name=device.name,
                rssi=advertisement.rssi,
                timestamp=now,
            )
            try:
                self._queue.put_nowait(reading)
            except asyncio.QueueFull:
                pass

    async def _advertisement_scan(self) -> None:
        """Scan for BLE advertisements."""
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

    async def _connection_fallback(self) -> None:
        """Fallback: connect to paired device when no advertisements are received."""
        await asyncio.sleep(self._ADV_FALLBACK_DELAY)

        while self._running:
            now = asyncio.get_event_loop().time()
            if now - self._last_adv_time >= self._ADV_FALLBACK_DELAY:
                logger.debug("No advertisements from %s, trying direct connection", self._target)
                rssi = await _try_connected_rssi(self._target)
                if rssi is not None:
                    reading = RssiReading(
                        address=self._target,
                        name=None,
                        rssi=rssi,
                        timestamp=asyncio.get_event_loop().time(),
                        via_connection=True,
                    )
                    try:
                        self._queue.put_nowait(reading)
                    except asyncio.QueueFull:
                        pass

            await asyncio.sleep(5.0)

    async def run(self) -> None:
        """Start continuous BLE scanning with connection fallback."""
        self._running = True
        logger.info("Starting BLE scan for %s", self._target)

        adv_task = asyncio.create_task(self._advertisement_scan())
        conn_task = asyncio.create_task(self._connection_fallback())

        try:
            await asyncio.gather(adv_task, conn_task)
        except asyncio.CancelledError:
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
    """Discover BLE devices in range, including paired devices that don't advertise."""
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

    # Try paired devices not found via advertisements (in parallel)
    paired = await _get_paired_devices()
    missing = [(addr, name) for addr, name in paired
               if addr.upper() not in {d.address.upper() for d in devices}]

    if missing:
        results = await asyncio.gather(
            *[_try_connected_rssi(addr, timeout=5.0) for addr, _ in missing]
        )
        for (address, name), rssi in zip(missing, results):
            if rssi is not None:
                seen.add(address)
                devices.append(
                    RssiReading(
                        address=address, name=name, rssi=rssi,
                        timestamp=0.0, via_connection=True,
                    )
                )

    return sorted(devices, key=lambda d: d.rssi, reverse=True)
