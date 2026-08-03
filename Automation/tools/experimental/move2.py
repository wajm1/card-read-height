#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""Experimental reverse read-height characteriser (quarantined under tools/).

Role
    Optional/dev-only: starts inside a guaranteed read zone, walks upward until
    the read is lost, then bisects the boundary. Writes results to CSV.
    Not imported by the GUI or production CLI.

Strategy: start inside the guaranteed read zone (53.975 mm above the table),
walk upward 1 mm at a time until the read is lost, then bisect back into the
boundary with 5 passes (~0.03 mm accuracy).

Inputs / side effects
    Lite 6 motion via ``RobotMain``; credential reads via ``BarcodeListener``;
    reader info via ``reader.cli``. Hardcoded staging pose / motion constants.

Run from Automation/::

    python tools/experimental/move2.py
"""

import os
import sys
import csv
import time
import traceback
from datetime import datetime

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

import config
from xarm.wrapper import XArmAPI
from robot.move import RobotMain
from reader.cli import get_reader_info
from barcode.scanner import BarcodeListener

# ── motion constants ──────────────────────────────────────────────────────────
TABLE_Z_MM          = config.SMART_PICK_TABLE_Z_MM   # absolute Z of table surface
START_ABOVE_TABLE   = 53.975   # mm above table to begin (inside read zone)
MAX_WALK_MM         = 80.0     # safety: abort if we walk this far without losing read
COARSE_STEP_MM      = 1.0      # upward step size during walk phase
BISECT_PASSES       = 5        # bisection refinement passes  (~1/32 mm resolution)
SETTLE_SEC          = 0.15     # pause after each move before checking read
TCP_SPEED           = 20       # mm/s — slow, controlled
TCP_ACC             = 200

# ── reader staging pose (joint angles, degrees) ───────────────────────────────
# Position the arm directly above the reader before any descent.
READER_STAGING_ANGLE = [0.8, 27.4, 39.6, 5.4, 6.8, 0.9]
RESULTS_DIR = config.PATHS.get("results", os.path.join(AUTOMATION_ROOT, "results"))


def pprint(*args):
    try:
        frame = traceback.extract_stack(limit=2)[0]
        print("[{}][{}] {}".format(
            time.strftime("%Y-%m-%d %H:%M:%S"), frame[1],
            " ".join(str(a) for a in args)))
    except Exception:
        print(*args)


# =============================================================================
class ReadHeightCharacteriser(RobotMain):
    """
    Subclasses the unmodified RobotMain so all safety callbacks, error checks,
    and arm state management are inherited unchanged.
    """

    def __init__(self, arm, reader_id="unknown"):
        super().__init__(arm)
        self.reader_id = reader_id
        self._ceiling_z_abs   = None   # absolute Z of read ceiling (robot frame)
        self._ceiling_above_table = None   # mm above table — what goes in the CSV
        self._coarse_last_good = None
        self._coarse_loss      = None

    # ── internal helpers ──────────────────────────────────────────────────────

    def _current_z(self):
        """Return current TCP Z in robot-frame mm, or None on failure."""
        code, pos = self._arm.get_position()
        if not self._check_code(code, "get_position"):
            return None
        return pos[2]

    def _move_to_abs_z(self, target_z_abs):
        """Move in Z only (relative) to reach an absolute robot-frame Z."""
        current = self._current_z()
        if current is None:
            return False
        delta = target_z_abs - current
        code = self._arm.set_position(
            z=delta, radius=0,
            speed=TCP_SPEED, mvacc=TCP_ACC,
            relative=True, wait=True)
        return self._check_code(code, "move_abs_z to {:.3f}".format(target_z_abs))

    def _check_read(self, window_sec=0.4):
        """
        Listen for a card read event for up to window_sec seconds.
        Returns True if any read is detected, False if the window expires.
        Uses BarcodeListener — the same mechanism as the rest of the codebase.
        """
        detected = {"v": False}

        def on_read(_barcode):
            detected["v"] = True

        listener = BarcodeListener(on_read)
        listener.start()
        try:
            deadline = time.monotonic() + window_sec
            while time.monotonic() < deadline:
                if detected["v"]:
                    return True
                time.sleep(0.02)
            return False
        finally:
            listener.stop()

    def _above_table(self, abs_z):
        """Convert absolute robot-frame Z to height above the table."""
        return abs_z - TABLE_Z_MM

    # ── phase 1: coarse upward walk ───────────────────────────────────────────

    def _coarse_walk(self, start_abs_z):
        """
        Walk upward 1 mm at a time from start_abs_z until the read is lost.
        Returns (last_good_abs_z, loss_abs_z) or (None, None) on error/timeout.
        """
        pprint("Phase 1 — coarse walk up ({}mm steps)".format(COARSE_STEP_MM))
        z = start_abs_z
        last_good = None

        walked = 0.0
        while walked <= MAX_WALK_MM:
            if not self.is_alive:
                return None, None

            time.sleep(SETTLE_SEC)
            got_read = self._check_read()
            above = self._above_table(z)
            pprint("  z_abs={:.3f}  above_table={:.3f}mm  read={}".format(
                z, above, got_read))

            if got_read:
                last_good = z
            else:
                if last_good is None:
                    pprint("  ERROR: no read at start position — "
                           "check reader mode and card placement.")
                    return None, None
                loss_z = z
                pprint("  Read lost at {:.3f}mm above table (abs {:.3f})".format(
                    self._above_table(loss_z), loss_z))
                pprint("  Last-good   at {:.3f}mm above table (abs {:.3f})".format(
                    self._above_table(last_good), last_good))
                return last_good, loss_z

            # step up
            z += COARSE_STEP_MM
            walked += COARSE_STEP_MM
            if not self._move_to_abs_z(z):
                return None, None

        pprint("  ERROR: walked {:.0f}mm without losing read — "
               "check MAX_WALK_MM or reader cable.".format(MAX_WALK_MM))
        return None, None

    # ── phase 2: bisection ────────────────────────────────────────────────────

    def _bisect(self, lo_abs, hi_abs):
        """
        Binary-search the read boundary between lo_abs (reads) and hi_abs
        (no read). Returns the tightest last-good abs Z after BISECT_PASSES.
        """
        pprint("Phase 2 — bisection ({} passes, target ±{:.3f}mm)".format(
            BISECT_PASSES, COARSE_STEP_MM / (2 ** BISECT_PASSES)))

        for i in range(BISECT_PASSES):
            if not self.is_alive:
                return lo_abs   # return best known so far
            mid = (lo_abs + hi_abs) / 2.0
            if not self._move_to_abs_z(mid):
                return lo_abs
            time.sleep(SETTLE_SEC)
            got_read = self._check_read()
            pprint("  pass {:d}: mid={:.4f} ({:.4f}mm above table)  read={}  "
                   "bracket=[{:.4f},{:.4f}]".format(
                       i + 1, mid, self._above_table(mid), got_read, lo_abs, hi_abs))
            if got_read:
                lo_abs = mid   # inside zone — raise the known-good floor
            else:
                hi_abs = mid   # outside zone — lower the ceiling

        pprint("  Ceiling pinned to {:.4f}mm above table".format(
            self._above_table(lo_abs)))
        return lo_abs   # lo_abs is the highest Z that still produces a read

    # ── results ───────────────────────────────────────────────────────────────

    def _save_csv(self, ceiling_above_table, coarse_last_good, coarse_loss, reader_info):
        os.makedirs(RESULTS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fname = os.path.join(RESULTS_DIR,
                             "{}_{}_{}_ceiling.csv".format(ts, self.reader_id, "reverse"))
        fields = [
            "Timestamp", "Reader ID", "Reader Part-Number", "Reader Firmware",
            "Start Above Table (mm)", "Coarse Step (mm)", "Bisect Passes",
            "Coarse Last-Good (mm)", "Coarse Loss (mm)",
            "Ceiling Above Table (mm)", "Ceiling Abs Z (mm)",
        ]
        row = {
            "Timestamp": ts,
            "Reader ID": self.reader_id,
            "Reader Part-Number": reader_info.get("Part-Number", ""),
            "Reader Firmware": reader_info.get("USB-Firmware", ""),
            "Start Above Table (mm)": START_ABOVE_TABLE,
            "Coarse Step (mm)": COARSE_STEP_MM,
            "Bisect Passes": BISECT_PASSES,
            "Coarse Last-Good (mm)": round(self._above_table(coarse_last_good), 4)
                                     if coarse_last_good else "",
            "Coarse Loss (mm)": round(self._above_table(coarse_loss), 4)
                                if coarse_loss else "",
            "Ceiling Above Table (mm)": round(ceiling_above_table, 4),
            "Ceiling Abs Z (mm)": round(self._ceiling_z_abs, 4)
                                  if self._ceiling_z_abs else "",
        }
        with open(fname, "w", newline="", encoding="utf-8") as f:
            f.write("# rf IDEAS — Reverse Read-Height Characterisation\n")
            f.write("# Reader: {}  ({})\n".format(
                self.reader_id, reader_info.get("Part-Number", "")))
            f.write("# Date: {}\n".format(ts))
            f.write("# Algorithm: coarse walk {}mm/step + {} bisection passes\n".format(
                COARSE_STEP_MM, BISECT_PASSES))
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerow(row)
        pprint("CSV saved -> {}".format(fname))
        return fname

    def _print_summary(self, ceiling_above_table):
        width = 52
        bar = "=" * width
        print("\n" + bar)
        print("  READ CEILING RESULT")
        print(bar)
        print("  Reader        : {}".format(self.reader_id))
        print("  Start height  : {:.3f} mm above table".format(START_ABOVE_TABLE))
        print("  Coarse bracket: {:.3f} → {:.3f} mm".format(
            self._above_table(self._coarse_last_good),
            self._above_table(self._coarse_loss)))
        print("  ─" * (width // 2))
        print("  READ CEILING  : {:.4f} mm above table".format(ceiling_above_table))
        print("  Abs robot Z   : {:.4f} mm".format(self._ceiling_z_abs))
        print("  Resolution    : ±{:.4f} mm".format(
            COARSE_STEP_MM / (2 ** BISECT_PASSES)))
        print(bar + "\n")

    # ── main run ──────────────────────────────────────────────────────────────

    def run(self):
        try:
            # ── get reader info before touching the arm ───────────────────────
            pprint("Fetching reader info...")
            try:
                reader_info = get_reader_info() or {}
            except Exception:
                reader_info = {}
            pprint("Reader: {} FW {}".format(
                reader_info.get("Part-Number", "?"),
                reader_info.get("USB-Firmware", "?")))

            # ── home ─────────────────────────────────────────────────────────
            pprint("Homing...")
            code = self._arm.set_servo_angle(
                angle=config.HOME_ANGLE, speed=120, mvacc=1000,
                wait=True, radius=0.0)
            if not self._check_code(code, "home"):
                return

            # ── move to staging pose (above reader) ───────────────────────────
            pprint("Moving to staging pose above reader...")
            self._angle_speed = 60
            self._angle_acc   = 500
            code = self._arm.set_servo_angle(
                angle=READER_STAGING_ANGLE,
                speed=self._angle_speed, mvacc=self._angle_acc,
                wait=True, radius=0.0)
            if not self._check_code(code, "staging pose"):
                return

            # ── descend to the guaranteed read height ─────────────────────────
            start_abs_z = TABLE_Z_MM + START_ABOVE_TABLE
            pprint("Descending to {:.3f}mm above table (abs Z={:.3f})...".format(
                START_ABOVE_TABLE, start_abs_z))
            if not self._move_to_abs_z(start_abs_z):
                return
            time.sleep(0.3)

            # verify we actually have a read at the start position
            if not self._check_read():
                pprint("ERROR: no read at start height ({:.3f}mm above table). "
                       "Check card, reader mode, and START_ABOVE_TABLE.".format(
                           START_ABOVE_TABLE))
                return

            pprint("Read confirmed at start height. Beginning reverse search...")

            # ── phase 1: coarse walk ──────────────────────────────────────────
            last_good, loss_z = self._coarse_walk(start_abs_z)
            if last_good is None:
                return
            self._coarse_last_good = last_good
            self._coarse_loss      = loss_z

            # ── phase 2: bisection ────────────────────────────────────────────
            ceiling_abs = self._bisect(last_good, loss_z)
            self._ceiling_z_abs = ceiling_abs
            ceiling_above_table = self._above_table(ceiling_abs)
            self._ceiling_above_table = ceiling_above_table

            # ── results ───────────────────────────────────────────────────────
            self._print_summary(ceiling_above_table)
            self._save_csv(ceiling_above_table, last_good, loss_z, reader_info)

        except Exception as e:
            pprint("MainException: {}".format(e))
            traceback.print_exc()
        finally:
            # ── retract to home ───────────────────────────────────────────────
            pprint("Retracting to home...")
            try:
                self._arm.set_servo_angle(
                    angle=config.HOME_ANGLE, speed=80, mvacc=800,
                    wait=True, radius=0.0)
            except Exception as e:
                pprint("Retract error: {}".format(e))

            self.alive = False
            try:
                self._arm.release_error_warn_changed_callback(
                    self._error_warn_changed_callback)
                self._arm.release_state_changed_callback(
                    self._state_changed_callback)
            except Exception:
                pass
            self._arm.disconnect()
            pprint("Done.")


# =============================================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Reverse read-height characteriser — finds the upper "
                    "read ceiling for the card/reader under test.")
    parser.add_argument("--ip", default=config.ROBOT_IP,
                        help="Robot IP (default: {})".format(config.ROBOT_IP))
    parser.add_argument("--reader", default="unknown",
                        help="Reader ID label for the CSV (e.g. HIP2_SP)")
    args = parser.parse_args()

    pprint("Connecting to {}...".format(args.ip))
    arm = XArmAPI(args.ip, baud_checkset=False)
    time.sleep(0.5)

    robot = ReadHeightCharacteriser(arm, reader_id=args.reader)
    robot.run()