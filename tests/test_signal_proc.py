"""Tests for RSSI signal processing."""

import math

from unlock_pc.signal_proc import ProximityState, RssiProcessor, rssi_to_distance


class TestRssiToDistance:
    def test_at_tx_power_returns_1m(self):
        """At tx_power RSSI, distance should be ~1 meter."""
        assert rssi_to_distance(-59, tx_power=-59) == 1.0

    def test_weaker_signal_is_further(self):
        d_close = rssi_to_distance(-50, tx_power=-59)
        d_far = rssi_to_distance(-80, tx_power=-59)
        assert d_far > d_close

    def test_zero_rssi_returns_zero(self):
        assert rssi_to_distance(0) == 0.0

    def test_known_value(self):
        # At -69 dBm with tx_power=-59 and n=2.0:
        # distance = 10^(((-59)-(-69)) / (10*2)) = 10^(10/20) = 10^0.5 ≈ 3.16m
        dist = rssi_to_distance(-69, tx_power=-59, path_loss_exponent=2.0)
        assert abs(dist - math.sqrt(10)) < 0.01


class TestRssiProcessor:
    def _make_processor(self, **kwargs):
        defaults = dict(
            alpha=0.5,
            tx_power=-59,
            path_loss_exponent=2.5,
            unlock_max_distance=2.0,
            lock_min_distance=4.0,
            absence_timeout=15.0,
            max_rssi_jump=20.0,
            stability_count=3,
        )
        defaults.update(kwargs)
        return RssiProcessor(**defaults)

    def test_initial_state_is_absent(self):
        proc = self._make_processor()
        assert proc.state == ProximityState.ABSENT

    def test_strong_signal_transitions_to_near(self):
        proc = self._make_processor()
        # -50 dBm is very close (~0.5m with default calibration)
        for _ in range(5):
            proc.update(-50, timestamp=1.0)
        assert proc.state == ProximityState.NEAR

    def test_weak_signal_transitions_to_far(self):
        proc = self._make_processor()
        # First get to NEAR
        for i in range(5):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # Then move far away (-85 dBm ≈ 10+m)
        for i in range(20):
            proc.update(-85, timestamp=float(10 + i))
        assert proc.state == ProximityState.FAR

    def test_hysteresis_prevents_flapping(self):
        proc = self._make_processor()
        # Get to NEAR
        for i in range(5):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # Signal at boundary (not far enough to trigger FAR)
        # -65 dBm ≈ 2.5m, which is between unlock(2m) and lock(4m)
        for i in range(10):
            proc.update(-65, timestamp=float(10 + i))
        # Should still be NEAR due to hysteresis
        assert proc.state == ProximityState.NEAR

    def test_absence_detection(self):
        proc = self._make_processor(absence_timeout=5.0)
        # Need 3 stable readings to transition to NEAR
        for i in range(3):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # Check absence after timeout
        result = proc.check_absence(timestamp=20.0)
        assert result == ProximityState.ABSENT

    def test_ema_smoothing(self):
        proc = self._make_processor(alpha=0.5)
        proc.update(-60, timestamp=0.0)
        assert proc.smoothed_rssi == -60.0

        proc.update(-70, timestamp=1.0)
        # EMA: 0.5 * -70 + 0.5 * -60 = -65
        assert proc.smoothed_rssi == -65.0

        proc.update(-70, timestamp=2.0)
        # EMA: 0.5 * -70 + 0.5 * -65 = -67.5
        assert proc.smoothed_rssi == -67.5

    def test_estimated_distance_updates(self):
        proc = self._make_processor()
        assert proc.estimated_distance is None

        proc.update(-59, timestamp=0.0)  # tx_power = 1m
        assert proc.estimated_distance is not None
        assert abs(proc.estimated_distance - 1.0) < 0.1

    def test_spike_rejection_clamps_large_jump(self):
        """A single RSSI spike > max_jump is clamped, preventing false transition."""
        proc = self._make_processor(max_rssi_jump=20.0, stability_count=1)
        # Establish baseline at -50 (very close)
        proc.update(-50, timestamp=0.0)
        assert proc.smoothed_rssi == -50.0

        # Spike to -95 (would be 40+ meters). Delta = -45, clamped to -50-20 = -70
        proc.update(-95, timestamp=1.0)
        # EMA: 0.5 * -70 + 0.5 * -50 = -60 (not -72.5 without clamping)
        assert proc.smoothed_rssi == -60.0

    def test_spike_rejection_allows_normal_change(self):
        """Normal RSSI changes within max_jump pass through unclamped."""
        proc = self._make_processor(max_rssi_jump=20.0, stability_count=1)
        proc.update(-50, timestamp=0.0)
        # -65 is a 15 dBm change, within the 20 dBm limit
        proc.update(-65, timestamp=1.0)
        # EMA: 0.5 * -65 + 0.5 * -50 = -57.5
        assert proc.smoothed_rssi == -57.5

    def test_stability_counter_prevents_single_reading_transition(self):
        """A single reading past threshold doesn't change state."""
        proc = self._make_processor(stability_count=3)
        # Get to NEAR (3 readings)
        for i in range(3):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # One very far reading — not enough to transition
        proc.update(-85, timestamp=10.0)  # clamped to -70, smoothed ≈ -60
        proc.update(-85, timestamp=11.0)  # clamped to -80, smoothed ≈ -70
        # These readings push distance past 4m but only 1-2 FAR readings
        # State should still be NEAR (need 3 consecutive FAR)
        # After 2 readings: smoothed ≈ -70, distance ≈ 2.8m (still < 4m)
        assert proc.state == ProximityState.NEAR

    def test_stability_counter_transitions_after_sustained_change(self):
        """State transitions after enough sustained readings past threshold."""
        proc = self._make_processor(stability_count=3)
        # Get to NEAR
        for i in range(3):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # Sustained far-away signal (15 readings at -85)
        for i in range(15):
            proc.update(-85, timestamp=float(10 + i))
        assert proc.state == ProximityState.FAR

    def test_stability_counter_resets_on_return(self):
        """If signal returns before stability count reached, counter resets."""
        proc = self._make_processor(stability_count=5, max_rssi_jump=50.0)
        # Get to NEAR
        for i in range(5):
            proc.update(-50, timestamp=float(i))
        assert proc.state == ProximityState.NEAR

        # 2 far readings (not enough for stability=5)
        proc.update(-90, timestamp=10.0)
        proc.update(-90, timestamp=11.0)
        # Signal returns to close
        for i in range(5):
            proc.update(-50, timestamp=float(15 + i))
        # Should still be NEAR — the brief far period didn't accumulate enough
        assert proc.state == ProximityState.NEAR
