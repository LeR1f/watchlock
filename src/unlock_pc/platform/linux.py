"""Linux (GNOME/systemd) platform adapter."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


class LinuxAdapter:
    """Lock/unlock via loginctl (works with GNOME, KDE, and other systemd-based DEs)."""

    def __init__(self) -> None:
        self._session_id = os.environ.get("XDG_SESSION_ID", "")

    async def _run(self, *args: str) -> tuple[int, str]:
        """Run a command and return (returncode, stdout)."""
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("Command %s failed: %s", args, stderr.decode().strip())
        return proc.returncode, stdout.decode().strip()

    async def lock_session(self) -> None:
        """Lock the session via loginctl."""
        logger.info("Locking session")
        await self._run("loginctl", "lock-session")

    async def unlock_session(self) -> None:
        """Unlock the session via loginctl and wake the display."""
        logger.info("Unlocking session")
        await self._run("loginctl", "unlock-session")
        # Wake display (works on both X11 and Wayland in most cases)
        await self._run("xdg-screensaver", "reset")

    async def is_session_locked(self) -> bool:
        """Check if the session is locked via loginctl."""
        session_id = self._session_id or await self._get_session_id()
        if not session_id:
            return False
        rc, output = await self._run(
            "loginctl", "show-session", session_id,
            "--property=LockedHint", "--value",
        )
        return output == "yes"

    async def _get_session_id(self) -> str:
        """Get the current session ID."""
        rc, output = await self._run(
            "loginctl", "show-user", os.environ.get("USER", ""),
            "--property=Sessions", "--value",
        )
        if output:
            # Take the first session ID
            self._session_id = output.split()[0]
        return self._session_id
