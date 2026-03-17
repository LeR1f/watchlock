"""Configuration loading and validation."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "watchlock" / "config.yaml"

DEFAULTS = {
    "device": {"address": "", "name": ""},
    "distance": {"unlock_max": 2.0, "lock_min": 4.0},
    "rssi": {"tx_power": -59, "path_loss_exponent": 2.5, "smoothing_alpha": 0.3, "max_jump": 20},
    "timing": {
        "scan_interval": 1.0,
        "grace_period": 10.0,
        "absence_timeout": 25.0,
        "stability_readings": 3,
    },
    "daemon": {"log_level": "INFO", "log_file": None},
}


@dataclasses.dataclass
class Config:
    # Device
    device_address: str
    device_name: str
    # Distance thresholds (meters)
    unlock_max_distance: float
    lock_min_distance: float
    # RSSI calibration
    tx_power: int
    path_loss_exponent: float
    smoothing_alpha: float
    # Timing
    scan_interval: float
    grace_period: float
    # Daemon
    log_level: str
    log_file: str | None
    # Stability
    max_rssi_jump: float = 20.0
    stability_readings: int = 3
    absence_timeout: float = 25.0

    def validate(self) -> None:
        if not self.device_address:
            raise ValueError("device.address is required. Run 'watchlock pair' first.")
        if self.unlock_max_distance >= self.lock_min_distance:
            raise ValueError(
                f"distance.unlock_max ({self.unlock_max_distance}m) must be less than "
                f"distance.lock_min ({self.lock_min_distance}m) for hysteresis"
            )
        if not 0 < self.smoothing_alpha <= 1:
            raise ValueError(f"rssi.smoothing_alpha must be in (0, 1], got {self.smoothing_alpha}")
        if self.grace_period < 0:
            raise ValueError(f"timing.grace_period must be >= 0, got {self.grace_period}")
        if self.scan_interval <= 0:
            raise ValueError(f"timing.scan_interval must be > 0, got {self.scan_interval}")


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, recursively for nested dicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file, merged with defaults."""
    config_path = path or DEFAULT_CONFIG_PATH

    if config_path.exists():
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        logger.info("Loaded config from %s", config_path)
    else:
        user_config = {}
        logger.warning("No config file at %s, using defaults", config_path)

    merged = _deep_merge(DEFAULTS, user_config)

    return Config(
        device_address=merged["device"]["address"],
        device_name=merged["device"]["name"],
        unlock_max_distance=float(merged["distance"]["unlock_max"]),
        lock_min_distance=float(merged["distance"]["lock_min"]),
        tx_power=int(merged["rssi"]["tx_power"]),
        path_loss_exponent=float(merged["rssi"]["path_loss_exponent"]),
        smoothing_alpha=float(merged["rssi"]["smoothing_alpha"]),
        scan_interval=float(merged["timing"]["scan_interval"]),
        grace_period=float(merged["timing"]["grace_period"]),
        log_level=merged["daemon"]["log_level"],
        log_file=merged["daemon"]["log_file"],
        max_rssi_jump=float(merged["rssi"]["max_jump"]),
        stability_readings=int(merged["timing"]["stability_readings"]),
        absence_timeout=float(merged["timing"]["absence_timeout"]),
    )


def save_device(address: str, name: str, path: Path | None = None) -> None:
    """Save device address and name to config file."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    data.setdefault("device", {})
    data["device"]["address"] = address
    data["device"]["name"] = name

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

    logger.info("Saved device %s (%s) to %s", name, address, config_path)


# Map of CLI-friendly names to YAML paths
SETTINGS = {
    "unlock-distance": ("distance", "unlock_max"),
    "lock-distance": ("distance", "lock_min"),
    "grace-period": ("timing", "grace_period"),
    "absence-timeout": ("timing", "absence_timeout"),
    "stability-readings": ("timing", "stability_readings"),
    "scan-interval": ("timing", "scan_interval"),
    "tx-power": ("rssi", "tx_power"),
    "smoothing-alpha": ("rssi", "smoothing_alpha"),
    "max-jump": ("rssi", "max_jump"),
    "path-loss": ("rssi", "path_loss_exponent"),
    "log-level": ("daemon", "log_level"),
}


def set_setting(key: str, value: str, path: Path | None = None) -> None:
    """Update a single setting in the config file."""
    config_path = path or DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    section, field = SETTINGS[key]
    data.setdefault(section, {})

    # Auto-cast: int for stability-readings/tx-power, str for log-level, float for rest
    if key in ("stability-readings",):
        data[section][field] = int(value)
    elif key in ("tx-power",):
        data[section][field] = int(value)
    elif key in ("log-level",):
        data[section][field] = value.upper()
    else:
        data[section][field] = float(value)

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

    logger.info("Set %s = %s", key, value)
