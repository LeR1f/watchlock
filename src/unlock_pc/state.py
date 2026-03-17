"""State machine for lock/unlock lifecycle."""

from __future__ import annotations

import enum
import logging
from typing import Callable

from unlock_pc.signal_proc import ProximityState

logger = logging.getLogger(__name__)


class SessionState(enum.Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    LOCKING = "locking"  # Grace period before locking


class Event(enum.Enum):
    DEVICE_NEAR = "device_near"
    DEVICE_FAR = "device_far"
    DEVICE_ABSENT = "device_absent"
    GRACE_EXPIRED = "grace_expired"


def proximity_to_event(proximity: ProximityState) -> Event:
    """Convert a ProximityState to a state machine Event."""
    return {
        ProximityState.NEAR: Event.DEVICE_NEAR,
        ProximityState.FAR: Event.DEVICE_FAR,
        ProximityState.ABSENT: Event.DEVICE_ABSENT,
    }[proximity]


class StateMachine:
    """Manages session lock/unlock state transitions.

    Transitions:
        LOCKED   + DEVICE_NEAR    → UNLOCKED
        UNLOCKED + DEVICE_FAR     → LOCKING
        UNLOCKED + DEVICE_ABSENT  → LOCKING
        LOCKING  + DEVICE_NEAR    → UNLOCKED
        LOCKING  + GRACE_EXPIRED  → LOCKED
    """

    def __init__(self) -> None:
        self._state = SessionState.LOCKED
        self._listeners: list[StateChangeCallback] = []

    @property
    def state(self) -> SessionState:
        return self._state

    def on_change(self, callback: StateChangeCallback) -> None:
        """Register a callback for state changes."""
        self._listeners.append(callback)

    def process(self, event: Event) -> SessionState:
        """Process an event and return the new state."""
        old_state = self._state

        match (self._state, event):
            case (SessionState.LOCKED, Event.DEVICE_NEAR):
                self._state = SessionState.UNLOCKED

            case (SessionState.UNLOCKED, Event.DEVICE_FAR | Event.DEVICE_ABSENT):
                self._state = SessionState.LOCKING

            case (SessionState.LOCKING, Event.DEVICE_NEAR):
                self._state = SessionState.UNLOCKED

            case (SessionState.LOCKING, Event.GRACE_EXPIRED):
                self._state = SessionState.LOCKED

            case _:
                pass  # No transition

        if self._state != old_state:
            logger.info("State: %s → %s (event: %s)", old_state.value, self._state.value, event.value)
            for listener in self._listeners:
                listener(old_state, self._state, event)

        return self._state


# Type alias for state change callbacks
StateChangeCallback = Callable[[SessionState, SessionState, Event], None]
