"""Shared pytest fixtures + hardware fakes for the read-height test suite.

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Make the whole test suite runnable with NO robot, reader, or barcode
    scanner attached, on any OS. The production code imports Windows/hardware
    modules at import time (``msvcrt``, ``xarm``), so this conftest injects
    lightweight fakes into ``sys.modules`` before those modules are imported,
    and puts the ``Automation/`` and ``Automation/gui/`` directories on the
    import path so the code imports exactly as it does at runtime.

    The centerpiece is ``FakeArm`` — a stand-in for ``xarm.wrapper.XArmAPI``
    that returns success codes and RECORDS every motion/suction call. Tests use
    it to characterize behavior (the sequence and arguments of arm commands, the
    result-row math) without moving a real Lite 6.

Role in the system:
    Test-only. Never imported by production code.
"""

import os
import sys
import types

# ---------------------------------------------------------------------------
# Import paths — mirror how gui.py / cardreadheight.py set themselves up.
# ---------------------------------------------------------------------------
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(TESTS_DIR)
for p in (AUTOMATION_ROOT, os.path.join(AUTOMATION_ROOT, "gui"),
          os.path.join(AUTOMATION_ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Fake hardware/OS modules so the code imports headlessly and deterministically.
# Injected unconditionally so a test host with the real SDK still never drives
# a physical arm.
# ---------------------------------------------------------------------------
def _install_fake_msvcrt():
    m = types.ModuleType("msvcrt")
    m.kbhit = lambda: False           # never "a key was pressed"
    m.getwch = lambda: ""
    sys.modules["msvcrt"] = m


def _install_fake_xarm():
    xarm = types.ModuleType("xarm")
    version = types.ModuleType("xarm.version")
    version.__version__ = "fake-test"
    wrapper = types.ModuleType("xarm.wrapper")

    class XArmAPI:                    # noqa: D401 - stand-in only
        """Placeholder so ``from xarm.wrapper import XArmAPI`` resolves."""
        def __init__(self, *a, **k):
            raise RuntimeError(
                "Real XArmAPI must not be constructed in tests — use FakeArm.")

    wrapper.XArmAPI = XArmAPI
    xarm.wrapper = wrapper
    xarm.version = version
    sys.modules["xarm"] = xarm
    sys.modules["xarm.wrapper"] = wrapper
    sys.modules["xarm.version"] = version


_install_fake_msvcrt()
_install_fake_xarm()

import pytest


# ---------------------------------------------------------------------------
# FakeArm — records SDK calls; returns success (0) so control flow proceeds.
# ---------------------------------------------------------------------------
class FakeArm:
    """Minimal stand-in for XArmAPI that logs calls instead of moving anything.

    Every motion / suction call is appended to ``self.calls`` as
    ``(method_name, kwargs)`` so tests can assert the exact command sequence a
    refactor must preserve. Position/joint getters return internal state that
    relative moves update, so descent/ascent helpers behave plausibly.
    """

    def __init__(self, joints=None, position=None):
        self.connected = True
        self.state = 0
        self.error_code = 0
        self.warn_code = 0
        self._joints = list(joints or [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        self._pos = list(position or [200.0, 0.0, 150.0, 180.0, 0.0, 0.0])
        self.suction = False
        self.calls = []
        # RobotMain.smart_pick reaches through ``arm.arm.check_air_pump_state``.
        self.arm = types.SimpleNamespace(
            check_air_pump_state=lambda *a, **k: True)

    # -- bookkeeping --
    def _rec(self, name, **kw):
        self.calls.append((name, kw))

    def calls_named(self, name):
        return [kw for (n, kw) in self.calls if n == name]

    # -- init / faults --
    def clean_warn(self):
        self._rec("clean_warn"); return 0

    def clean_error(self):
        self._rec("clean_error"); return 0

    def motion_enable(self, enable):
        self._rec("motion_enable", enable=enable); return 0

    def set_mode(self, mode):
        self._rec("set_mode", mode=mode); return 0

    def set_state(self, state):
        self._rec("set_state", state=state); return 0

    def register_error_warn_changed_callback(self, cb):
        self._rec("register_error_warn_changed_callback")

    def register_state_changed_callback(self, cb):
        self._rec("register_state_changed_callback")

    def release_error_warn_changed_callback(self, cb):
        self._rec("release_error_warn_changed_callback")

    def release_state_changed_callback(self, cb):
        self._rec("release_state_changed_callback")

    def get_state(self):
        return (0, self.state)

    def get_err_warn_code(self):
        return (0, [self.error_code, self.warn_code])

    # -- motion --
    def set_servo_angle(self, angle=None, **kw):
        self._rec("set_servo_angle", angle=list(angle) if angle else None, **kw)
        if angle:
            self._joints = [float(a) for a in list(angle)[:6]]
        return 0

    def set_position(self, x=None, y=None, z=None, roll=None, pitch=None,
                     yaw=None, relative=False, **kw):
        self._rec("set_position", x=x, y=y, z=z, roll=roll, pitch=pitch,
                  yaw=yaw, relative=relative, **kw)
        if relative:
            self._pos[0] += x or 0.0
            self._pos[1] += y or 0.0
            self._pos[2] += z or 0.0
        else:
            if x is not None:
                self._pos[0] = x
            if y is not None:
                self._pos[1] = y
            if z is not None:
                self._pos[2] = z
        return 0

    def get_position(self):
        return (0, list(self._pos))

    def get_servo_angle(self):
        return (0, list(self._joints))

    def set_suction_cup(self, on, **kw):
        self._rec("set_suction_cup", on=on, **kw)
        self.suction = bool(on)
        return 0

    def get_forward_kinematics(self, angle, **kw):
        j6 = angle[5] if len(angle) > 5 else 0.0
        return (0, [300.0, 0.0, 200.0, 180.0, 0.0, j6])

    def get_inverse_kinematics(self, pose, **kw):
        return (0, [0.0, 0.0, 0.0, 0.0, 0.0, pose[5] if len(pose) > 5 else 0.0])

    def emergency_stop(self):
        self._rec("emergency_stop")

    def disconnect(self):
        self._rec("disconnect")


@pytest.fixture
def fake_arm():
    return FakeArm()


@pytest.fixture
def gui_robot(fake_arm, monkeypatch):
    """A ready GuiRobot wired to a FakeArm (no real motion, no 1s init sleep)."""
    import robot.move as move
    monkeypatch.setattr(move.time, "sleep", lambda *_a, **_k: None)
    from gui_robot import GuiRobot
    robot = GuiRobot(fake_arm)
    robot.init_gui()
    return robot
