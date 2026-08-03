#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""CLI card read-height test runner (parallel orchestrator to GuiRobot).

Role
    ``CardReadHeightTest`` drives pick → barcode → HWG → descend-until-read
    for a stack of cards and writes timestamped CSVs under ``results/``.
    ``--gui`` delegates to ``gui.gui.main`` (does not use this class).

Inputs
    CLI args (``--ip``, ``--cycles``, ``--scans``, ``--dry-run``, …);
    ``config`` / ``TestSettings``; Lite 6 + barcode + RRMTool when not dry-run.

Outputs / hardware side effects
    Arm motion and suction (unless ``--dry-run``); reader HWG loads; CSV in
    workspace ``results/``.

Flow per card:
  1. Pick card from stack
  2. Start barcode listen immediately, lift and move to scanner while listening
  3. Look up files/AllCards.csv → load matching HWG from files/hwg/
  4. Move to reader (side A or B from barcode), descend slowly until credential is read
  5. Record read height to results/ (FAIL if no read by 10mm floor)
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import threading
import time
import traceback
from datetime import datetime

from xarm import version
from xarm.wrapper import XArmAPI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config
from barcode.scanner import BarcodeListener, lookup_card
from reader.cli import (
    check_reader, configure_reader_for_card, get_reader_info,
)
from robot.move import RobotMain, CardReadListener
from robot.test_settings import TestSettings

PLACE_ANGLES = {"A": config.PLACE_ANGLE_SIDE_A, "B": config.PLACE_ANGLE_SIDE_B}
TABLE_Z = config.TABLE_Z_MM
SCAN_TIMEOUT_S = 30
BARCODE_WIGGLE_J6_DEG = 3.0
BARCODE_WIGGLE_STEP_S = 0.2
RESULT_FIELDS = [
    "Timestamp",
    "Reader Model",
    "Card Name",
    "Barcode",
    "Read Height (mm)",
    "Status",
]

SUMMARY_FIELDS = [
    "Timestamp",
    "Reader Model",
    "Card Name",
    "Barcode",
    "Scans",
    "Avg Read Height (mm)",
    "Min (mm)",
    "Max (mm)",
    "Std Dev (mm)",
    "All Readings (mm)",
    "Status",
]

# Fast confirmation pass — proves the reader reads this card before the
# slow, slider-controlled height measurement(s). Not slider-adjustable.
FAST_DESCENT_SPEED = 60.0   # mm/s
FAST_DESCENT_ACC = 1000.0   # mm/s^2
FAST_STEP_MM = 5.0
FAST_DWELL_S = 0.15


class RunStatus:
    """Shared status for GUI polling."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.phase = "Idle"
        self.card_name = "—"
        self.barcode = "—"
        self.side = "—"
        self.reader_checked = False
        self.reader_configured = False
        self.current_height_mm: float | None = None
        self.read_height_mm: float | None = None
        self.current_pass = "\u2014"
        self.avg_height_mm: float | None = None


class CardReadHeightTest(RobotMain):
    """Extends RobotMain with barcode lookup, reader config, and read-height testing."""

    def __init__(
        self, robot, *, cycles: int = 1, scans: int = 1,
        settings: TestSettings | None = None,
        status: RunStatus | None = None,
        log_fn=None,
    ):
        super().__init__(robot)
        self.cycles = cycles
        self.scans = max(1, int(scans))
        self.settings = settings or TestSettings()
        self.status = status or RunStatus()
        self._log_fn = log_fn
        self.reader_info = {}
        self.results_path = None
        self.summary_path = None
        self._barcode_result: dict | None = None
        self._barcode_event = threading.Event()
        self._barcode_listen_deadline = 0.0
        self._barcode_listener = BarcodeListener(self._on_barcode_scanned)
        self._read_stop = threading.Event()
        self._read_listener: CardReadListener | None = None

    def request_stop(self):
        self._stop_event.set()
        self.alive = False
        self._halt_motion()

    def _set_phase(self, phase: str):
        self.status.phase = phase
        self.pprint(phase)

    def _halt_motion(self):
        try:
            self._arm.set_state(4)
            time.sleep(0.05)
            self._arm.set_state(0)
        except Exception:
            pass

    def pprint(self, *args, **kwargs):
        super().pprint(*args, **kwargs)
        if self._log_fn:
            self._log_fn(" ".join(map(str, args)))

    def _on_barcode_scanned(self, barcode: str):
        if self._barcode_result is not None:
            return

        card = lookup_card(barcode)
        if card:
            self._barcode_result = card
            self._barcode_event.set()
            self._barcode_listener.stop()
            self.pprint(f"Barcode accepted: {barcode} -> {card['name']}")
        else:
            self.pprint(f"Unknown barcode (ignored): {barcode}")

    def _configure_reader(self, card_info: dict) -> bool:
        """Load HWG for card — same path as reader/reader_test.py."""
        name = card_info["name"]
        self.pprint(f"Configuring reader for {name}...")
        self.pprint(f"  Barcode:  {card_info.get('barcode', '?')}")
        self.pprint(f"  Side:     {card_info.get('side', '?')}")
        self.pprint(f"  Part #:   {card_info.get('part_number', '?')}")
        self.pprint(f"  HWG:      {card_info.get('hwg', '?')}")

        hwg = card_info.get("hwg", "")
        if not hwg or not os.path.isfile(hwg):
            self.pprint(f"HWG file missing: {hwg}")
            return False

        if not configure_reader_for_card(card_info, log_fn=self.pprint, verify=True):
            self.status.reader_checked = True
            self.status.reader_configured = False
            return False

        self.status.reader_checked = True
        self.status.reader_configured = True
        return True

    def _start_barcode_listen(self):
        """Begin listening as soon as the card is on suction — before lift/transit."""
        self._barcode_result = None
        self._barcode_event.clear()
        self._barcode_listen_deadline = time.monotonic() + SCAN_TIMEOUT_S
        self._barcode_listener.start()
        self.pprint("Listening for barcode (during lift and transit to scanner)...")

    def _wiggle_at_scanner(self):
        """Small wrist oscillation in front of the fixed barcode scanner."""
        if self._barcode_event.is_set():
            return

        base = list(config.BARCODE_SCAN_ANGLE)
        offsets = [BARCODE_WIGGLE_J6_DEG, -BARCODE_WIGGLE_J6_DEG, 0.0]
        self.pprint("Wiggling card in front of barcode scanner...")

        while self.is_alive and not self._barcode_event.is_set():
            if time.monotonic() >= self._barcode_listen_deadline:
                break

            for offset in offsets:
                if not self.is_alive or self._barcode_event.is_set():
                    break
                if time.monotonic() >= self._barcode_listen_deadline:
                    break

                angle = base.copy()
                angle[5] += offset
                if not self._move_to_servo(
                    angle, "barcode wiggle", speed=30, acc=200,
                ):
                    return

                pause_end = min(
                    time.monotonic() + BARCODE_WIGGLE_STEP_S,
                    self._barcode_listen_deadline,
                )
                while time.monotonic() < pause_end and not self._barcode_event.is_set():
                    time.sleep(0.05)

        if self.is_alive and not self._barcode_event.is_set():
            self._move_to_servo(
                config.BARCODE_SCAN_ANGLE, "barcode scanner center", speed=30, acc=200,
            )

    def _finish_barcode_scan(self) -> dict | None:
        """Wiggle at scanner if needed, then wait out the scan window."""
        if not self._barcode_event.is_set():
            self._wiggle_at_scanner()

        if not self._barcode_event.is_set():
            remaining = self._barcode_listen_deadline - time.monotonic()
            if remaining > 0:
                self.pprint(f"At scanner — waiting up to {remaining:.0f}s more for barcode...")
                self._barcode_event.wait(timeout=remaining)

        self._barcode_listener.stop()

        if not self._barcode_result:
            self.pprint("Barcode scan timed out or card not found in AllCards.csv")
            return None

        self.pprint(f"Card identified: {self._barcode_result['name']}")
        return self._barcode_result

    def _move_to_servo(self, angle, label, *, speed=None, acc=None, wait=True):
        speed = speed if speed is not None else self._angle_speed
        acc = acc if acc is not None else self._angle_acc
        code = self._arm.set_servo_angle(
            angle=angle, speed=speed, mvacc=acc, wait=wait, radius=0.0,
        )
        return self._check_code(code, label)

    def _move_z_relative(self, dz, label, *, speed=None, acc=None, wait=True):
        speed = speed if speed is not None else self._tcp_speed
        acc = acc if acc is not None else self._tcp_acc
        code = self._arm.set_position(
            z=dz, radius=0, speed=speed, mvacc=acc, relative=True, wait=wait,
        )
        return self._check_code(code, label)

    def _height_above_table(self) -> float | None:
        ret = self._arm.get_position()
        if ret[0] != 0:
            return None
        return ret[1][2] - TABLE_Z

    def _move_to_height_above_table(
        self, height_mm: float, *, wait: bool = False,
        speed: float | None = None, acc: float | None = None,
    ) -> bool:
        s = self.settings
        speed = speed if speed is not None else s.descent_speed
        acc = acc if acc is not None else s.descent_acc
        ret = self._arm.get_position()
        if ret[0] != 0:
            return False
        pos = ret[1]
        target_z = TABLE_Z + height_mm
        code = self._arm.set_position(
            x=pos[0], y=pos[1], z=target_z,
            roll=pos[3], pitch=pos[4], yaw=pos[5],
            speed=speed, mvacc=acc,
            wait=wait,
        )
        if code != 0:
            return self._check_code(code, f"move to {height_mm:.1f}mm above table")

        if wait:
            return True

        while self.is_alive:
            if self._read_stop.is_set():
                self._halt_motion()
                return True
            moving = self._arm.get_is_moving()
            # SDK may return a tuple (code, is_moving) or a plain bool
            if isinstance(moving, tuple):
                is_moving = moving[1] if moving[0] == 0 else True
            else:
                is_moving = bool(moving)
            if not is_moving:
                break
            time.sleep(0.02)
        return True

    def _on_credential_read(self, data: str):
        self._read_stop.set()
        self._halt_motion()
        h = self._height_above_table()
        if h is not None:
            self.status.current_height_mm = h
            self.status.read_height_mm = h
        self.pprint(f"  READ detected — stopping arm ({data!r})")

    def _measure_read_height(
        self, *, speed: float | None = None, acc: float | None = None,
        step: float | None = None, dwell: float | None = None,
        settle: float | None = None, start: float | None = None,
        floor: float | None = None,
    ) -> float | None:
        """Descend with listener active; stop arm immediately on credential read.

        With no overrides this uses the live (slider) descent speed. The fast
        confirmation pass calls it with explicit fast speed/step/dwell.
        """
        s = self.settings
        speed = speed if speed is not None else s.descent_speed
        acc = acc if acc is not None else s.descent_acc
        step = step if step is not None else s.step_mm
        dwell = dwell if dwell is not None else s.dwell_s
        settle = settle if settle is not None else s.settle_s
        start = start if start is not None else s.start_height_mm
        floor = floor if floor is not None else s.min_height_mm

        self._read_stop.clear()
        self.status.read_height_mm = None

        def on_read(data: str):
            self._on_credential_read(data)

        self._read_listener = CardReadListener(on_read=on_read)
        self._read_listener.start()

        try:
            if not self._move_to_height_above_table(start, wait=False, speed=speed, acc=acc):
                return None

            height = start
            self.pprint(
                f"Descent: start {start:.1f}mm, step {step:.1f}mm, "
                f"floor {floor:.1f}mm, speed {speed:.0f}mm/s",
            )

            while height >= floor and self.is_alive:
                if self._read_stop.is_set():
                    h = self._height_above_table()
                    if h is not None:
                        self.pprint(f"  READ at {h:.2f}mm above table")
                        return h
                    return height

                h = self._height_above_table()
                if h is not None:
                    self.status.current_height_mm = h

                if settle > 0:
                    time.sleep(settle)

                dwell_end = time.monotonic() + dwell
                while time.monotonic() < dwell_end and self.is_alive:
                    if self._read_stop.is_set():
                        h = self._height_above_table()
                        if h is not None:
                            self.pprint(f"  READ at {h:.2f}mm above table")
                            return h
                        return height
                    time.sleep(0.02)

                height -= step
                if height < floor:
                    break
                if not self._move_to_height_above_table(height, wait=False, speed=speed, acc=acc):
                    if self._read_stop.is_set():
                        return self._height_above_table()
                    return None

            return None
        finally:
            if self._read_listener:
                self._read_listener.stop()
                self._read_listener = None

    def _append_result(self, row: dict):
        config.ensure_paths_exist()
        if not self.results_path:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            model = self.reader_info.get("Part-Number", "reader")
            self.results_path = config.get_results_path(f"{ts}_{model}_read_heights.csv")

        write_header = not os.path.exists(self.results_path)
        with open(self.results_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        self.pprint(f"Result saved -> {self.results_path}")

    def _run_read_height_at_place(self, side: str, scans: int) -> list:
        s = self.settings

        # ── Fast confirmation pass: prove the reader reads this card ──
        self._set_phase(f"Confirming reader (fast) side {side}")
        confirm = self._measure_read_height(
            speed=FAST_DESCENT_SPEED, acc=FAST_DESCENT_ACC,
            step=FAST_STEP_MM, dwell=FAST_DWELL_S, settle=0.0,
        )
        if confirm is None:
            self.pprint(f"Reader did NOT confirm a read (side {side}) — skipping measurement.")
            self._move_z_relative(
                70, f"raise from reader side {side}",
                speed=s.approach_speed, acc=s.approach_acc,
            )
            return []
        self.pprint(f"Fast confirm OK (~{confirm:.1f}mm). Running {scans} measured scan(s)...")

        # ── Slow, slider-controlled measured passes for averaging ──
        heights: list = []
        for r in range(scans):
            if not self.is_alive:
                break
            self.status.current_pass = f"{r + 1}/{scans}"
            self._set_phase(f"Measuring side {side} — scan {r + 1}/{scans}")
            h = self._measure_read_height()
            if h is not None:
                heights.append(h)
                self.pprint(f"  Scan {r + 1}: {h:.2f}mm")
            else:
                self.pprint(f"  Scan {r + 1}: no read by floor")

        self._move_z_relative(
            70, f"raise from reader side {side}",
            speed=s.approach_speed, acc=s.approach_acc,
        )
        return heights

    def _export_summary(self, card_info: dict, side: str, heights: list,
                        reader_model: str, status: str):
        """Append one averaged row per card to a results/ summary CSV."""
        config.ensure_paths_exist()
        if not self.summary_path:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            model = reader_model or "reader"
            self.summary_path = config.get_results_path(
                f"{ts}_{model}_read_height_summary.csv"
            )

        if heights:
            avg = sum(heights) / len(heights)
            lo = min(heights)
            hi = max(heights)
            sd = statistics.pstdev(heights) if len(heights) > 1 else 0.0
        else:
            avg = lo = hi = sd = None

        row = {
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Reader Model": reader_model,
            "Card Name": card_info.get("name", ""),
            "Barcode": card_info.get("barcode", ""),
            "Scans": len(heights),
            "Avg Read Height (mm)": f"{avg:.2f}" if avg is not None else "",
            "Min (mm)": f"{lo:.2f}" if lo is not None else "",
            "Max (mm)": f"{hi:.2f}" if hi is not None else "",
            "Std Dev (mm)": f"{sd:.3f}" if sd is not None else "",
            "All Readings (mm)": "; ".join(f"{h:.2f}" for h in heights),
            "Status": status,
        }

        write_header = not os.path.exists(self.summary_path)
        with open(self.summary_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        self.pprint(f"Summary saved -> {self.summary_path}")

    def run(self):
        try:
            config.ensure_paths_exist()

            ok, reader_msg = check_reader()
            self.pprint(f"Reader check: {'PASS' if ok else 'FAIL'} — {reader_msg}")
            if not ok:
                return

            self.reader_info = get_reader_info()
            reader_model = self.reader_info.get("Part-Number", "unknown")
            self.pprint(f"Reader: {reader_model}")

            if not self._move_to_servo(config.HOME_ANGLE, "home position", speed=180, acc=1100):
                return
            self.pprint(f"Starting {self.cycles} card cycle(s)...")

            for i in range(self.cycles):
                if not self.is_alive:
                    break

                self.pprint("─" * 40)
                self.pprint(f"Cycle {i + 1} of {self.cycles}")
                t1 = time.monotonic()

                # ── Pick Position ─────────────────────────────────────────
                self._angle_speed = 180
                self._angle_acc = 1100
                if not self._move_to_servo(config.PICK_ANGLE, "pick position"):
                    break

                code = self._arm.set_suction_cup(
                    True, wait=False, delay_sec=0, hardware_version=1,
                )
                if not self._check_code(code, "suction on"):
                    break

                pick_z = self.smart_pick()
                if pick_z is None:
                    self.pprint(f"Pick failed on cycle {i + 1}")
                    break

                # ── Barcode listen starts immediately after grab ────────
                self._start_barcode_listen()

                time.sleep(0.3)

                # ── Lift (scanner may read during motion) ───────────────
                self._angle_speed = 180
                self._angle_acc = 1100
                if not self._move_z_relative(50, "lift card", speed=self._tcp_speed):
                    self._barcode_listener.stop()
                    break
                time.sleep(0.3)

                if not self._check_code(self._arm.set_state(0), "set_state"):
                    self._barcode_listener.stop()
                    break

                # ── Transit to barcode scanner (still listening) ────────
                self._angle_speed = 180
                self._angle_acc = 1100
                if not self._move_to_servo(config.BARCODE_SCAN_ANGLE, "barcode scanner position"):
                    self._barcode_listener.stop()
                    break

                card_info = self._finish_barcode_scan()
                if not card_info:
                    break

                self.status.card_name = card_info["name"]
                self.status.barcode = card_info.get("barcode", "—")
                self.status.side = card_info.get("side", "A")

                self._set_phase("Configuring reader")
                if not self._configure_reader(card_info):
                    break

                # ── Reader (one side per barcode: A or B) ─────────────
                side = (card_info.get("side") or "A").upper()
                if side not in PLACE_ANGLES:
                    side = "A"
                self.pprint(f"Read-height test on side {side}")

                self._angle_speed = 180
                self._angle_acc = 1100
                if not self._move_to_servo(
                    PLACE_ANGLES[side], f"reader side {side}", wait=True,
                ):
                    break

                heights = self._run_read_height_at_place(side, self.scans)

                # ── Release ───────────────────────────────────────────
                if not self._move_to_servo(config.RELEASE_ANGLE, "release position", wait=False):
                    break
                code = self._arm.set_suction_cup(
                    False, wait=False, delay_sec=0, hardware_version=1,
                )
                if not self._check_code(code, "suction off"):
                    break

                # ── Averaged summary export ───────────────────────────
                if heights:
                    avg = sum(heights) / len(heights)
                    self.status.avg_height_mm = avg
                    status = "PASS"
                    self.pprint(
                        f"{card_info['name']} side {side}: avg {avg:.2f}mm "
                        f"(min {min(heights):.2f}, max {max(heights):.2f}, n={len(heights)})"
                    )
                else:
                    status = "FAIL"
                self._export_summary(card_info, side, heights, reader_model, status)

                interval = time.monotonic() - t1
                self.pprint(f"Cycle {i + 1} complete in {interval:.2f}s")

        except Exception as e:
            self.pprint(f"MainException: {e}")
            traceback.print_exc()

        finally:
            self._barcode_listener.stop()
            if self._read_listener:
                self._read_listener.stop()
            self.status.phase = "Done"
            if self._stop_event.is_set():
                self.clean_stop()
            else:
                self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
                self._arm.set_servo_angle(
                    angle=config.HOME_ANGLE, speed=60, mvacc=500, wait=True, radius=0.0,
                )
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)
            self._arm.disconnect()
            self.pprint("Arm disconnected. Done.")


def run_dry_run(*, configure_reader: bool = False) -> int:
    """Validate CSV lookup and optionally load HWG to reader (no robot)."""
    config.ensure_paths_exist()

    ok, reader_msg = check_reader()
    print(f"Reader check: {'PASS' if ok else 'FAIL'} — {reader_msg}")
    if configure_reader and not ok:
        return 1

    card = lookup_card("A001")
    if not card:
        print("ERROR: Could not look up A001 in AllCards.csv")
        return 1
    print(f"Lookup OK: {card['name']} -> {card['hwg']}")
    print(f"  Side:   {card.get('side', '?')}")
    print(f"  Part #: {card.get('part_number', '?')}")

    if configure_reader:
        print("\nLoading HWG to reader...")
        if not configure_reader_for_card(card):
            print("FAIL — reader configuration failed")
            return 1
        print("PASS — reader configured")

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = config.get_results_path(f"{ts}_dry-run_read_heights.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerow({
            "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Reader Model": get_reader_info().get("Part-Number", "dry-run"),
            "Card Name": card["name"],
            "Barcode": "A001",
            "Read Height (mm)": f"{config.DEFAULT_READ_SPEC_MM:.2f}",
            "Status": "DRY-RUN",
        })
    print(f"Dry-run results written -> {path}")
    print(f"read_height_mm={config.DEFAULT_READ_SPEC_MM:.2f}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Low-band card read height test")
    parser.add_argument("--ip", default=config.ROBOT_IP, help="xArm IP address")
    parser.add_argument("--cycles", type=int, default=config.CARD_STACK_COUNT, help="Number of cards")
    parser.add_argument("--scans", type=int, default=1, help="Slow measured scans per card (for averaging)")
    parser.add_argument("--dry-run", action="store_true", help="Validate CSV/results without robot")
    parser.add_argument(
        "--reader-config", action="store_true",
        help="With --dry-run, also load A001 HWG to reader",
    )
    parser.add_argument(
        "--gui", action="store_true",
        help="Open live control GUI",
    )
    args = parser.parse_args()

    if args.gui:
        from gui.gui import main as gui_main
        gui_main()
        return

    if args.dry_run:
        sys.exit(run_dry_run(configure_reader=args.reader_config))

    RobotMain.pprint(f"xArm-Python-SDK Version: {version.__version__}")
    arm = XArmAPI(args.ip, baud_checkset=False)
    time.sleep(0.5)
    test = CardReadHeightTest(arm, cycles=args.cycles, scans=args.scans)
    test.run()


if __name__ == "__main__":
    main()