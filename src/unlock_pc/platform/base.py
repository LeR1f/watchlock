"""Abstract platform adapter interface."""

from __future__ import annotations

from typing import Protocol


class PlatformAdapter(Protocol):
    async def lock_session(self) -> None:
        """Lock the current user session."""
        ...

    async def unlock_session(self) -> None:
        """Unlock the current user session."""
        ...

    async def is_session_locked(self) -> bool:
        """Check if the current session is locked."""
        ...
