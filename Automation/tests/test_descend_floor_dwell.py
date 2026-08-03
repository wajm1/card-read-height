"""Tests for the reader-floor hold in _descend_until_read (low-reader support).

Author:  Wajahat Mahmood
Created: 2026-08-03
Purpose:
    Some readers only read when the card is essentially touching. The descent
    now HOLDS at its lowest point (the calibrated reader top) and keeps listening
    for READER_DESCENT_FLOOR_DWELL_S before giving up. These tests lock that in:
    the hold runs when nothing has read, a read that only arrives at the floor is
    captured, and a reader that reads during the descent is unaffected. Uses a
    controllable fake listener (no real keyboard hook) and the FakeArm robot.
"""

import time

import config
import robot.move as move


class _Listener:
    """Stand-in for CardReadListener; reads_when() decides each poll's result."""

    def __init__(self, reads_when=None, **_kw):
        self._reads_when = reads_when or (lambda: False)

    def start(self):
        pass

    def stop(self):
        pass

    def reset(self):
        pass

    def read_detected(self):
        return bool(self._reads_when())

    def wait_for_read(self, _t):
        return self.read_detected()


def _start_60mm_above_table(fake_arm):
    fake_arm._pos = [200.0, 0.0, config.TABLE_Z_MM + 60.0, 180.0, 0.0, 0.0]


def test_floor_dwell_constant_is_at_least_half_second():
    assert config.READER_DESCENT_FLOOR_DWELL_S >= 0.5


def test_holds_at_floor_when_nothing_reads(gui_robot, fake_arm, monkeypatch):
    monkeypatch.setattr(move, "CardReadListener", lambda **kw: _Listener())  # never reads
    _start_60mm_above_table(fake_arm)
    t0 = time.monotonic()
    res = gui_robot._descend_until_read(
        max_drop=6.0, step=2.0, speed=50.0, start_lift_mm=0,
        dwell_s=0.01, settle_s=0.0, floor_dwell_s=0.2)
    elapsed = time.monotonic() - t0
    assert res.read_found is False
    assert res.dropped_mm >= 6.0            # reached the floor
    assert elapsed >= 0.19                  # the floor hold actually ran


def test_read_that_only_arrives_at_floor_is_caught(gui_robot, fake_arm, monkeypatch):
    # Reader stays silent until the card is at the floor, then needs a few polls
    # to fire — only the floor hold catches it.
    floor_z = config.TABLE_Z_MM + 60.0 - 6.0
    state = {"polls_at_floor": 0}

    def reads_when():
        if fake_arm._pos[2] <= floor_z + 0.01:
            state["polls_at_floor"] += 1
            return state["polls_at_floor"] >= 5
        return False

    monkeypatch.setattr(move, "CardReadListener",
                        lambda **kw: _Listener(reads_when=reads_when))
    _start_60mm_above_table(fake_arm)
    res = gui_robot._descend_until_read(
        max_drop=6.0, step=2.0, speed=50.0, start_lift_mm=0,
        dwell_s=0.01, settle_s=0.0, floor_dwell_s=0.5)
    assert res.read_found is True
    # Captured at the reader floor (~54 mm above table for this setup).
    assert res.height_above_table_mm is not None
    assert abs(res.height_above_table_mm - 54.0) < 2.0


def test_read_during_descent_is_unaffected(gui_robot, fake_arm, monkeypatch):
    # A reader that reads immediately never reaches the floor-hold path.
    monkeypatch.setattr(move, "CardReadListener",
                        lambda **kw: _Listener(reads_when=lambda: True))
    _start_60mm_above_table(fake_arm)
    res = gui_robot._descend_until_read(
        max_drop=60.0, step=2.0, speed=50.0, start_lift_mm=0,
        dwell_s=0.01, settle_s=0.0, floor_dwell_s=0.5)
    assert res.read_found is True
    assert res.dropped_mm <= 4.0            # stopped on the first step or two
