"""RSSI signal processing: EMA smoothing, distance estimation, hysteresis."""

from __future__ import annotations

import enum
import logging
import math
import time

logger = logging.getLogger(__name__)


class ProximityState(enum.Enum):
    NEAR = "near"
    FAR = "far"
    ABSENT = "absent"


def rssi_to_distance(rssi: int, tx_power: int = -59, path_loss_exponent: float = 2.5) -> float:
    """Convert RSSI to estimated distance in meters using log-distance path loss model.

    distance = 10 ^ ((tx_power - rssi) / (10 * n))

    Args:
        rssi: Received signal strength in dBm (negative).
        tx_power: RSSI measured at 1 meter (calibration value).
        path_loss_exponent: Environment factor (2=open space, 2.5=office, 3=walls).

    Returns:
        Estimated distance in meters.
    """
    if rssi >= 0:
        return 0.0
    return math.pow(10, (tx_power - rssi) / (10 * path_loss_exponent))


class RssiProcessor:
    """Processes raw RSSI readings into smoothed distance and proximity state."""

    def __init__(
        self,
        *,
        alpha: float,
        tx_power: int,
        path_loss_exponent: float,
        unlock_max_distance: float,
        lock_min_distance: float,
        absence_timeout: float = 25.0,
        max_rssi_jump: float = 20.0,
        stability_count: int = 3,
    ) -> None:
        self._alpha = alpha
        self._tx_power = tx_power
        self._path_loss_exponent = path_loss_exponent
        self._unlock_distance = unlock_max_distance
        self._lock_distance = lock_min_distance
        self._absence_timeout = absence_timeout
        self._max_rssi_jump = max_rssi_jump
        self._required_stability = stability_count

        self._smoothed_rssi: float | None = None
        self._last_seen: float = 0.0
        self._current_state = ProximityState.ABSENT
        self._pending_state: ProximityState | None = None
        self._stability_counter: int = 0

    @property
    def smoothed_rssi(self) -> float | None:
        return self._smoothed_rssi

    @property
    def estimated_distance(self) -> float | None:
        if self._smoothed_rssi is None:
            return None
        return rssi_to_distance(
            int(self._smoothed_rssi), self._tx_power, self._path_loss_exponent
        )

    @property
    def state(self) -> ProximityState:
        return self._current_state

    def update(self, rssi: int, timestamp: float | None = None) -> ProximityState:
        """Feed a new RSSI reading and return the current proximity state."""
        now = timestamp if timestamp is not None else time.monotonic()
        self._last_seen = now

        # Outlier rejection: clamp extreme RSSI jumps to prevent spike-driven transitions
        clamped_rssi = rssi
        if self._smoothed_rssi is not None:
            delta = rssi - self._smoothed_rssi
            if abs(delta) > self._max_rssi_jump:
                clamped_rssi = int(
                    self._smoothed_rssi
                    + (self._max_rssi_jump if delta > 0 else -self._max_rssi_jump)
                )
                logger.debug("RSSI spike clamped: %d → %d dBm", rssi, clamped_rssi)

        # EMA smoothing
        if self._smoothed_rssi is None:
            self._smoothed_rssi = float(clamped_rssi)
        else:
            self._smoothed_rssi = (
                self._alpha * clamped_rssi + (1 - self._alpha) * self._smoothed_rssi
            )

        distance = rssi_to_distance(
            int(self._smoothed_rssi), self._tx_power, self._path_loss_exponent
        )

        # Hysteresis: different thresholds for near→far and far→near transitions
        raw_state = self._current_state
        if self._current_state in (ProximityState.FAR, ProximityState.ABSENT):
            if distance <= self._unlock_distance:
                raw_state = ProximityState.NEAR
        elif self._current_state == ProximityState.NEAR:
            if distance >= self._lock_distance:
                raw_state = ProximityState.FAR

        # Stability: require N consecutive readings in new state before transitioning
        if raw_state != self._current_state:
            if raw_state == self._pending_state:
                self._stability_counter += 1
            else:
                self._pending_state = raw_state
                self._stability_counter = 1
            if self._stability_counter >= self._required_stability:
                logger.debug(
                    "Proximity stable: %s → %s (%d readings)",
                    self._current_state.value,
                    raw_state.value,
                    self._required_stability,
                )
                self._current_state = raw_state
                self._pending_state = None
                self._stability_counter = 0
        else:
            self._pending_state = None
            self._stability_counter = 0

        return self._current_state

    def check_absence(self, timestamp: float | None = None) -> ProximityState:
        """Check if the device has been absent for too long."""
        now = timestamp if timestamp is not None else time.monotonic()
        if self._last_seen == 0.0 or (now - self._last_seen) > self._absence_timeout:
            self._current_state = ProximityState.ABSENT
            self._pending_state = None
            self._stability_counter = 0
        return self._current_state
