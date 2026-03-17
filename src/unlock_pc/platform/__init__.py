"""Platform-specific lock/unlock adapters."""

from __future__ import annotations

from unlock_pc.platform.base import PlatformAdapter


def get_platform_adapter() -> PlatformAdapter:
    """Return the Linux platform adapter."""
    from unlock_pc.platform.linux import LinuxAdapter

    return LinuxAdapter()
