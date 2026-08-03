#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""Goer — mark the reader top (like the GUI calibrator), then rise by N mm.

Standalone demo. Does not change GUI / test code.

Flow (same idea as CALIBRATE READER → MARK READER TOP):
  1. Connect, move to the 0° staging pose, turn suction on.
  2. Jog in UFactory Studio until the card just touches the reader top.
  3. Press ENTER to MARK — saves that pose as “reader top”.
  4. Type a number (mm) — arm returns over the reader and rises that far
     above the marked top. Q quits.

Run from Automation/::

    python Goer.py
"""

from __future__ import annotations

import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
_GUI_DIR = os.path.join(SCRIPT_DIR, "gui")
if _GUI_DIR not in sys.path:
    sys.path.insert(0, _GUI_DIR)

import config
from xarm.wrapper import XArmAPI

try:
    from constants import READER_STAGING_0_ANGLE as _STAGING
except Exception:  # pragma: no cover
    _STAGING = config.READER_DESCENT_STAGING_INLINE

JOINT_SPEED = float(getattr(config, "MOTION_JOINT_SPEED", 50.0))
JOINT_ACC = float(getattr(config, "MOTION_JOINT_ACC", 800.0))
TCP_SPEED = 80.0
TCP_ACC = 500.0
# After MARK, lift a little so the card is clear before height commands.
POST_MARK_LIFT_MM = 40.0


def _staging_angle():
    return [float(x) for x in list(_STAGING)[:6]]


def _connect(ip):
    print("Connecting to {} ...".format(ip))
    arm = XArmAPI(ip, baud_checkset=False)
    time.sleep(0.4)
    if not getattr(arm, "connected", True):
        raise RuntimeError("Arm not connected — check IP/cable.")
    try:
        arm.clean_warn()
        arm.clean_error()
    except Exception:
        pass
    arm.motion_enable(True)
    arm.set_mode(0)
    arm.set_state(0)
    time.sleep(0.2)
    return arm


def _get_pos(arm):
    ret = arm.get_position()
    if ret[0] != 0:
        return None
    return list(ret[1])


def _suction(arm, on):
    try:
        arm.set_suction_cup(bool(on), wait=False, delay_sec=0, hardware_version=1)
    except Exception as e:
        print("!! suction: {}".format(e))


def _move_staging(arm):
    pose = _staging_angle()
    print(">> Moving to staging / read angle: {}".format(
        ", ".join("{:.1f}".format(a) for a in pose)))
    code = arm.set_servo_angle(
        angle=pose, speed=JOINT_SPEED, mvacc=JOINT_ACC, wait=True, radius=0.0,
    )
    if code != 0:
        print("!! set_servo_angle failed: {}".format(code))
        return False
    return True


def _mark_reader(arm):
    """Capture current TCP as reader top (card touching). Same idea as GUI MARK."""
    pos = _get_pos(arm)
    if pos is None:
        print("!! Could not read position.")
        return None
    tcp_above_table = pos[2] - config.TABLE_Z_MM
    reader_h = round(config.card_face_above_table_from_tcp(tcp_above_table), 1)
    mark = {
        "x": pos[0], "y": pos[1], "z": pos[2],
        "roll": pos[3], "pitch": pos[4], "yaw": pos[5],
        "reader_h_mm": reader_h,
        "tcp_above_table_mm": round(tcp_above_table, 2),
    }
    print()
    print("  MARKED reader top")
    print("    TCP XYZ = {:.1f}, {:.1f}, {:.1f}".format(mark["x"], mark["y"], mark["z"]))
    print("    TCP {:.1f} mm above table".format(mark["tcp_above_table_mm"]))
    print("    Est. reader height (card face) = {:.1f} mm".format(mark["reader_h_mm"]))
    # Lift clear so the next command can come down/up safely.
    print(">> Lifting {:.0f} mm clear of the reader...".format(POST_MARK_LIFT_MM))
    arm.set_position(
        z=POST_MARK_LIFT_MM, roll=0, pitch=0, yaw=0,
        relative=True, speed=TCP_SPEED, mvacc=TCP_ACC, wait=True,
    )
    return mark


def _go_above_mark(arm, mark, above_mm):
    """Return over the marked XY/orientation, Z = marked top + above_mm."""
    target_z = mark["z"] + above_mm
    print(
        ">> Over reader, {:.1f} mm above marked top "
        "(target Z={:.2f})".format(above_mm, target_z)
    )
    code = arm.set_position(
        x=mark["x"], y=mark["y"], z=target_z,
        roll=mark["roll"], pitch=mark["pitch"], yaw=mark["yaw"],
        speed=TCP_SPEED, mvacc=TCP_ACC, wait=True,
    )
    if code != 0:
        print("!! set_position failed: {}".format(code))
        return False
    pos = _get_pos(arm)
    if pos is not None:
        print("   Now at Z={:.2f}  ({:.1f} mm above mark)".format(
            pos[2], pos[2] - mark["z"]))
    return True


def main():
    ip = os.environ.get("ROBOT_IP", config.ROBOT_IP)

    print("=" * 52)
    print("  Goer — mark reader, then rise by N mm")
    print("  TABLE_Z = {:.2f} mm".format(config.TABLE_Z_MM))
    print("=" * 52)

    arm = _connect(ip)
    mark = None
    try:
        if not _move_staging(arm):
            return 1
        _suction(arm, True)
        print()
        print("Suction ON — place a card on the cup.")
        print("In UFactory Studio, jog until the card just touches the reader top.")
        print("(Keep tool facing down / same orientation as staging.)")
        input("\nPress ENTER to MARK reader top  (or Ctrl+C to abort)... ")
        mark = _mark_reader(arm)
        if mark is None:
            return 1

        print()
        print("Type mm above the marked top (e.g. 25.4).  Q = quit.  M = re-mark.")
        while True:
            raw = input("\nmm above reader> ").strip()
            if not raw:
                continue
            low = raw.lower()
            if low in ("q", "quit", "exit"):
                break
            if low in ("m", "mark", "remark"):
                print("Jog to the reader top again in Studio...")
                input("ENTER when touching the top... ")
                mark = _mark_reader(arm)
                continue
            try:
                mm = float(raw)
            except ValueError:
                print("  Number, M (re-mark), or Q.")
                continue
            if mm < 0:
                print("  Use a non-negative height.")
                continue
            _go_above_mark(arm, mark, mm)
    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        try:
            _suction(arm, False)
        except Exception:
            pass
        try:
            arm.disconnect()
        except Exception:
            pass
        print("Disconnected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
