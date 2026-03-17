"""Tests for configuration loading and validation."""

import textwrap
from pathlib import Path

import pytest

from unlock_pc.config import Config, load_config


class TestConfigValidation:
    def _make_config(self, **overrides):
        defaults = dict(
            device_address="AA:BB:CC:DD:EE:FF",
            device_name="Test Watch",
            unlock_max_distance=2.0,
            lock_min_distance=4.0,
            tx_power=-59,
            path_loss_exponent=2.5,
            smoothing_alpha=0.3,
            scan_interval=1.0,
            grace_period=10.0,
            log_level="INFO",
            log_file=None,
        )
        defaults.update(overrides)
        return Config(**defaults)

    def test_valid_config(self):
        config = self._make_config()
        config.validate()  # Should not raise

    def test_empty_address_raises(self):
        config = self._make_config(device_address="")
        with pytest.raises(ValueError, match="device.address is required"):
            config.validate()

    def test_unlock_ge_lock_raises(self):
        config = self._make_config(unlock_max_distance=5.0, lock_min_distance=3.0)
        with pytest.raises(ValueError, match="must be less than"):
            config.validate()

    def test_equal_distances_raises(self):
        config = self._make_config(unlock_max_distance=3.0, lock_min_distance=3.0)
        with pytest.raises(ValueError, match="must be less than"):
            config.validate()

    def test_invalid_alpha_raises(self):
        config = self._make_config(smoothing_alpha=0.0)
        with pytest.raises(ValueError, match="smoothing_alpha"):
            config.validate()

        config = self._make_config(smoothing_alpha=1.5)
        with pytest.raises(ValueError, match="smoothing_alpha"):
            config.validate()

    def test_negative_grace_raises(self):
        config = self._make_config(grace_period=-1.0)
        with pytest.raises(ValueError, match="grace_period"):
            config.validate()

    def test_zero_scan_interval_raises(self):
        config = self._make_config(scan_interval=0.0)
        with pytest.raises(ValueError, match="scan_interval"):
            config.validate()


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(textwrap.dedent("""\
            device:
              address: "11:22:33:44:55:66"
              name: "My Watch"
            distance:
              unlock_max: 1.5
              lock_min: 3.0
        """))
        config = load_config(config_file)
        assert config.device_address == "11:22:33:44:55:66"
        assert config.device_name == "My Watch"
        assert config.unlock_max_distance == 1.5
        assert config.lock_min_distance == 3.0

    def test_defaults_when_no_file(self, tmp_path: Path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.device_address == ""
        assert config.unlock_max_distance == 2.0
        assert config.lock_min_distance == 4.0
        assert config.smoothing_alpha == 0.3

    def test_partial_override(self, tmp_path: Path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(textwrap.dedent("""\
            device:
              address: "AA:BB:CC:DD:EE:FF"
            distance:
              unlock_max: 1.0
        """))
        config = load_config(config_file)
        assert config.device_address == "AA:BB:CC:DD:EE:FF"
        assert config.unlock_max_distance == 1.0
        # Defaults preserved
        assert config.lock_min_distance == 4.0
        assert config.device_name == ""

    def test_stability_defaults(self, tmp_path: Path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.max_rssi_jump == 20.0
        assert config.stability_readings == 3
        assert config.absence_timeout == 25.0
