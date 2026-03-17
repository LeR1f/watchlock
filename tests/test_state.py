"""Tests for the state machine."""

from unlock_pc.state import Event, SessionState, StateMachine


class TestStateMachine:
    def test_initial_state_is_locked(self):
        sm = StateMachine()
        assert sm.state == SessionState.LOCKED

    def test_device_near_unlocks(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        assert sm.state == SessionState.UNLOCKED

    def test_device_far_starts_locking(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_FAR)
        assert sm.state == SessionState.LOCKING

    def test_device_absent_starts_locking(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_ABSENT)
        assert sm.state == SessionState.LOCKING

    def test_grace_expired_locks(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_FAR)
        sm.process(Event.GRACE_EXPIRED)
        assert sm.state == SessionState.LOCKED

    def test_device_returns_during_grace_unlocks(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_FAR)
        assert sm.state == SessionState.LOCKING
        sm.process(Event.DEVICE_NEAR)
        assert sm.state == SessionState.UNLOCKED

    def test_repeated_near_events_no_change(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_NEAR)
        assert sm.state == SessionState.UNLOCKED

    def test_far_while_locked_no_change(self):
        sm = StateMachine()
        sm.process(Event.DEVICE_FAR)
        assert sm.state == SessionState.LOCKED

    def test_grace_expired_while_locked_no_change(self):
        sm = StateMachine()
        sm.process(Event.GRACE_EXPIRED)
        assert sm.state == SessionState.LOCKED

    def test_full_cycle(self):
        sm = StateMachine()
        assert sm.state == SessionState.LOCKED

        sm.process(Event.DEVICE_NEAR)
        assert sm.state == SessionState.UNLOCKED

        sm.process(Event.DEVICE_FAR)
        assert sm.state == SessionState.LOCKING

        sm.process(Event.GRACE_EXPIRED)
        assert sm.state == SessionState.LOCKED

        sm.process(Event.DEVICE_NEAR)
        assert sm.state == SessionState.UNLOCKED

    def test_callback_fires_on_transition(self):
        sm = StateMachine()
        transitions = []
        sm.on_change(lambda old, new, event: transitions.append((old, new, event)))

        sm.process(Event.DEVICE_NEAR)
        sm.process(Event.DEVICE_NEAR)  # No change, no callback
        sm.process(Event.DEVICE_FAR)

        assert len(transitions) == 2
        assert transitions[0] == (SessionState.LOCKED, SessionState.UNLOCKED, Event.DEVICE_NEAR)
        assert transitions[1] == (SessionState.UNLOCKED, SessionState.LOCKING, Event.DEVICE_FAR)
