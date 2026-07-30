#!/usr/bin/env python3
"""Core Lite 6 motion library for credential read-height testing.

Role
    ``RobotMain`` wraps the xArm SDK: home, smart-pick, barcode scan + HWG
    configure, descend-until-read, clean stop. ``CardReadListener`` detects
    credential keyboard-wedge reads. Used by the GUI (``GuiRobot`` subclass)
    and the CLI runner (``cardreadheight.py``).

Inputs
    Connected ``XArmAPI`` instance; settings from ``config``; barcode wedge
    and RRMTool CLI via ``barcode.scanner`` / ``reader.cli``.

Outputs / hardware side effects
    Moves joints/TCP, operates suction cup, loads HWG to the reader, prints
    status. Does not write the GUI/CLI results CSV (callers do).

Windows-oriented (``msvcrt`` Q-to-stop listener). Prefer not editing motion
timings/poses without operator approval.
"""

import os
import sys
import time
import traceback
import threading
import msvcrt
from typing import NamedTuple

from xarm import version
from xarm.wrapper import XArmAPI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config
from barcode.scanner import BarcodeListener, lookup_card, WEDGE_BURST_GAP_S, SCAN_MAX_KEY_GAP_S, _typing_in_tk_entry
from reader.cli import configure_reader_for_card


def _is_barcode_noise(data: str) -> bool:
    """Ignore A### / B### barcode bursts mistaken for credential reads."""
    d = data.strip().upper()
    return len(d) == 4 and d[0] in "AB" and d[1:].isdigit()


class DescentResult(NamedTuple):
    dropped_mm: float
    read_found: bool
    height_above_table_mm: float | None = None


class CardReadListener:
    """Detects a credential read from the reader's USB keyboard-wedge output."""

    def __init__(self, on_read=None, *, suppress_wedge=True, tk_root=None):
        self._on_read = on_read
        self.suppress_wedge = suppress_wedge
        self._tk_root = tk_root
        self._event = threading.Event()
        self._data = ""
        self._captured = ""
        self._hook = None
        self._unhook = None
        self._last_time = 0.0
        self._block_burst = False
        self.active = False

    def start(self):
        try:
            import keyboard
        except Exception as e:
            print(f">> (read-detect disabled: keyboard module unavailable: {e})")
            return
        self.active = True
        self._event.clear()
        self._data = ""
        self._captured = ""
        self._last_time = 0.0
        self._block_burst = False
        if self.suppress_wedge:
            self._unhook = keyboard.hook(self._on_key, suppress=True)
        else:
            self._hook = keyboard.hook(self._on_key)

    def stop(self):
        self.active = False
        try:
            if self._unhook is not None:
                self._unhook()
            elif self._hook is not None:
                import keyboard
                keyboard.unhook(self._hook)
        except Exception:
            pass
        finally:
            self._hook = None
            self._unhook = None
            self._block_burst = False

    def _allow_key(self) -> bool:
        if not self.suppress_wedge:
            return True
        return not self._block_burst

    def _on_key(self, event):
        if not self.active:
            return True

        if _typing_in_tk_entry(self._tk_root):
            return True

        if event.event_type != "down":
            return self._allow_key()

        now = time.monotonic()
        gap = now - self._last_time if self._last_time else float("inf")
        if self._data and gap > SCAN_MAX_KEY_GAP_S:
            self._data = ""
            self._block_burst = False

        if event.name == "enter":
            text = self._data.strip()
            allow = self._allow_key()
            self._data = ""
            self._block_burst = False
            self._last_time = now
            if text and not _is_barcode_noise(text):
                self._captured = text
                self._event.set()
                if self._on_read:
                    self._on_read(text)
            return allow

        if len(event.name) == 1:
            starting = not self._data
            if not starting and gap < WEDGE_BURST_GAP_S:
                self._block_burst = True
            self._last_time = now
            self._data += event.name
            return self._allow_key()

        return self._allow_key()

    def read_detected(self):
        return self._event.is_set()

    def wait_for_read(self, timeout_s: float) -> bool:
        return self._event.wait(timeout=timeout_s)

    def is_set(self) -> bool:
        return self._event.is_set()

    def reset(self):
        self._event.clear()
        self._data = ""
        self._captured = ""

    @property
    def data(self) -> str:
        return self._captured or self._data.strip()


class RobotMain:
    """Lite 6 motion core: pick, barcode+config, descend-until-read, clean stop.

    Args:
        robot: Connected ``XArmAPI`` instance.

    Hardware side effects: joint/TCP motion, suction cup, reader configure via
    ``reader.cli`` when scanning barcodes.
    """

    def __init__(self, robot):
        self.alive = True
        self._arm = robot
        self._ignore_exit_state = False
        self._tcp_speed = config.MOTION_TCP_SPEED
        self._tcp_acc = config.MOTION_TCP_ACC
        self._angle_speed = config.MOTION_JOINT_SPEED
        self._angle_acc = config.MOTION_JOINT_ACC
        self._stop_event = threading.Event()
        self._last_pick_z = None
        self._current_card = None
        self._robot_init()
        self._input_thread = threading.Thread(target=self._listen_for_stop, daemon=True)
        self._input_thread.start()

    def _robot_init(self):
        self._arm.clean_warn()
        self._arm.clean_error()
        self._arm.motion_enable(True)
        self._arm.set_mode(0)
        self._arm.set_state(0)
        time.sleep(1)
        self._arm.register_error_warn_changed_callback(self._error_warn_changed_callback)
        self._arm.register_state_changed_callback(self._state_changed_callback)

    def _error_warn_changed_callback(self, data):
        if data and data["error_code"] != 0:
            self.alive = False
            self.pprint(f"Error {data['error_code']}, stopping.")
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)

    def _state_changed_callback(self, data):
        if not self._ignore_exit_state and data and data["state"] == 4:
            self.alive = False
            self.pprint("State=4, stopping.")
            self._arm.release_state_changed_callback(self._state_changed_callback)

    def _listen_for_stop(self):
        print(">> Press Q at any time for a clean stop...")
        while not self._stop_event.is_set():
            if msvcrt.kbhit():
                if msvcrt.getwch().lower() == "q":
                    print(">> Q pressed — finishing current move then stopping cleanly...")
                    self._stop_event.set()
                    self.alive = False
                    break
            time.sleep(0.1)

    def _check_code(self, code, label):
        if not self.is_alive or code != 0:
            self.alive = False
            ret1 = self._arm.get_state()
            ret2 = self._arm.get_err_warn_code()
            self.pprint(
                f"{label} failed | code={code} connected={self._arm.connected} "
                f"state={self._arm.state} error={self._arm.error_code} | ret1={ret1} ret2={ret2}"
            )
        return self.is_alive

    def clean_stop(self):
        """Release suction, stop motion cleanly, and disconnect from the arm."""
        print(">> Clean stop initiated...")
        self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
        time.sleep(0.3)
        self._arm.set_servo_angle(
            angle=config.HOME_ANGLE,
            speed=config.MOTION_PARK_JOINT_SPEED,
            mvacc=config.MOTION_PARK_JOINT_ACC,
            wait=True, radius=0.0,
        )
        time.sleep(0.5)
        self._arm.motion_enable(False)
        print(">> Arm safely stopped at home.")

    @staticmethod
    def pprint(*args, **kwargs):
        try:
            stack_tuple = traceback.extract_stack(limit=2)[0]
            print(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}]"
                f"[{stack_tuple[1]}] {' '.join(map(str, args))}"
            )
        except Exception:
            print(*args, **kwargs)

    @property
    def is_alive(self):
        if self._stop_event.is_set():
            return False
        if self.alive and self._arm.connected and self._arm.error_code == 0:
            if self._ignore_exit_state:
                return True
            if self._arm.state == 5:
                for _ in range(5):
                    if self._arm.state != 5:
                        break
                    time.sleep(0.1)
            return self._arm.state < 4
        return False

    def _scan_barcode_and_config(self, timeout=15):
        result = {}
        event = threading.Event()

        def on_barcode(barcode):
            if result.get("card"):
                return
            card = lookup_card(barcode)
            if card:
                result["card"] = card
                event.set()
                print(f">> Barcode {barcode} -> {card.get('name', '?')}")
            else:
                print(f">> Unknown barcode: {barcode}")

        listener = BarcodeListener(
            on_barcode,
            tk_root=getattr(self, "tk_root", None),
            force_capture=True,
        )
        listener.start()
        print(f">> Waiting for barcode (up to {timeout}s)...")
        event.wait(timeout=timeout)
        listener.stop()

        card = result.get("card")
        if not card:
            print(">> No valid barcode read.")
            return None

        print(f">> Configuring reader for {card.get('name', '?')}...")
        ok = configure_reader_for_card(card, log_fn=print)
        print(">> Reader configured." if ok else ">> Reader configuration FAILED.")
        self._current_card = card
        return card

    def _max_drop_to_floor(self, *, include_start_lift=True):
        """Max downward travel before hitting the reader floor limit."""
        ret = self._arm.get_position()
        if ret[0] != 0:
            return config.READER_DESCENT_MAX_DROP_MM
        z_start = ret[1][2]
        if include_start_lift:
            z_start += config.READER_DESCENT_START_LIFT_MM
        floor_z = config.TABLE_Z_MM + config.READER_DESCENT_MIN_HEIGHT_MM
        allowed = z_start - floor_z
        return max(0.0, min(allowed, config.READER_DESCENT_MAX_DROP_MM))

    def _floor_above_table_mm(self):
        return config.READER_DESCENT_MIN_HEIGHT_MM

    def _height_above_table_from_arm(self):
        ret = self._arm.get_position()
        if ret[0] != 0:
            return None
        return ret[1][2] - config.TABLE_Z_MM

    def _raise_after_descent(self, dropped, label="raise from reader", *, include_start_lift=True):
        lift = config.READER_DESCENT_START_LIFT_MM if include_start_lift else 0.0
        retract = dropped + lift
        if retract <= 0:
            return True
        code = self._arm.set_position(
            z=retract, radius=0,
            speed=self._tcp_speed, mvacc=self._tcp_acc,
            relative=True, wait=True,
        )
        return self._check_code(code, label)

    def _descend_until_read(
        self,
        max_drop=None,
        step=None,
        speed=None,
        start_lift_mm=None,
        dwell_s=None,
        settle_s=None,
    ):
        if max_drop is None:
            max_drop = self._max_drop_to_floor()
        step = config.READER_DESCENT_STEP_MM if step is None else step
        speed = config.READER_DESCENT_SPEED_MM_S if speed is None else speed
        if start_lift_mm is None:
            start_lift_mm = config.READER_DESCENT_START_LIFT_MM
        dwell_s = config.READER_DESCENT_DWELL_S if dwell_s is None else dwell_s
        settle_s = config.READER_DESCENT_SETTLE_S if settle_s is None else settle_s
        if start_lift_mm > 0:
            print(f">> Lifting {start_lift_mm:.0f}mm before reader descent...")
            code = self._arm.set_position(
                z=start_lift_mm, radius=0,
                speed=self._tcp_speed, mvacc=self._tcp_acc,
                relative=True, wait=True,
            )
            if not self._check_code(code, "pre-descent lift"):
                return DescentResult(0.0, False, None)

        listener = CardReadListener(tk_root=getattr(self, "tk_root", None))
        listener.start()
        listener.reset()
        dropped = 0.0
        read_found = False
        height_at_read = None

        def _listen_at_step(dropped_mm):
            if settle_s > 0:
                time.sleep(settle_s)
            deadline = time.monotonic() + dwell_s
            while time.monotonic() < deadline and self.is_alive:
                if listener.read_detected():
                    print(f">> Card READ at {dropped_mm:.1f}mm descent — stopping.")
                    return True
                time.sleep(0.02)
            if listener.read_detected():
                print(f">> Card READ at {dropped_mm:.1f}mm descent — stopping.")
                return True
            return False

        try:
            floor_mm = self._floor_above_table_mm()
            print(
                f">> Descending toward reader ({speed:.0f} mm/s, stop on read, max {max_drop:.0f}mm descent, "
                f"floor {floor_mm:.1f}mm above table, {dwell_s:.2f}s listen per step)..."
            )
            while True:
                if not self.is_alive:
                    break
                if dropped >= max_drop:
                    above = self._height_above_table_from_arm()
                    if above is not None:
                        print(
                            f">> Reached floor limit ({self._floor_above_table_mm():.1f}mm above table) "
                            f"at {above:.1f}mm above table after {dropped:.0f}mm descent — no read."
                        )
                    else:
                        print(f">> Reached {max_drop:.0f}mm descent limit with no read.")
                    break
                code = self._arm.set_position(
                    z=-step, radius=0, speed=speed, mvacc=self._tcp_acc,
                    relative=True, wait=True,
                )
                if not self._check_code(code, "descend toward reader"):
                    break
                dropped += step
                if _listen_at_step(dropped):
                    read_found = True
                    height_at_read = self._height_above_table_from_arm()
                    break
        finally:
            listener.stop()
        return DescentResult(dropped, read_found, height_at_read)

    def smart_pick(self):
        """Search-descend at the pick pose until suction grabs a card; return True/False."""
        step_size = config.PICK_SEARCH_STEP_MM
        max_descent = config.PICK_SEARCH_MAX_MM
        suction_wait = 0.2
        table_z = config.TABLE_Z_MM

        print(f">> Smart pick — descending in {step_size}mm steps (max {max_descent}mm)...")
        total_descent = 0.0

        while total_descent < max_descent:
            if not self.is_alive:
                return None

            code = self._arm.set_position(
                z=-step_size, radius=-1,
                speed=config.MOTION_PICK_DESCENT_SPEED,
                mvacc=config.MOTION_PICK_DESCENT_ACC,
                relative=True, wait=True,
            )
            if not self._check_code(code, "smart descend step"):
                return None

            total_descent += step_size
            ret = self._arm.get_position()
            current_z = ret[1][2] if ret[0] == 0 else None
            if current_z is not None:
                print(
                    f">>   Suction cup to table: {current_z - table_z:.1f}mm | "
                    f"Total descent: {total_descent:.1f}mm"
                )

            if self._arm.arm.check_air_pump_state(1, timeout=suction_wait, hardware_version=1):
                if current_z is not None:
                    self._last_pick_z = current_z
                    print(
                        f">> Card grabbed! Z={current_z:.2f}mm | "
                        f"{current_z - table_z:.1f}mm from table | after {total_descent:.1f}mm descent"
                    )
                return current_z

        print(f">> WARNING: No card detected within {max_descent}mm — backing off!")
        self._arm.set_position(
            z=max_descent, radius=-1,
            speed=self._tcp_speed, mvacc=self._tcp_acc,
            relative=True, wait=True,
        )
        return None

    def run(self):
        try:
            code = self._arm.set_servo_angle(
                angle=config.HOME_ANGLE,
                speed=config.MOTION_HOME_SPEED,
                mvacc=config.MOTION_HOME_ACC,
                wait=True, radius=0.0,
            )
            if not self._check_code(code, "home position"):
                return
            print(">> Home reached. Starting card cycles...")

            for i in range(config.CARD_STACK_COUNT):
                if not self.is_alive:
                    break

                print(">> ─────────────────────────────────")
                print(f">> Cycle {i + 1} of {config.CARD_STACK_COUNT}")
                t1 = time.monotonic()

                self._angle_speed = config.MOTION_FAST_JOINT_SPEED
                self._angle_acc = config.MOTION_FAST_JOINT_ACC
                code = self._arm.set_servo_angle(
                    angle=config.PICK_ANGLE,
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0,
                )
                if not self._check_code(code, "move to pick"):
                    return

                code = self._arm.set_suction_cup(True, wait=False, delay_sec=0, hardware_version=1)
                if not self._check_code(code, "suction on"):
                    return

                pick_z = self.smart_pick()
                if pick_z is None:
                    print(f">> Pick failed on cycle {i + 1} — stopping run.")
                    break

                time.sleep(config.POST_MOTION_PAUSE_S)

                code = self._arm.set_position(
                    z=config.POST_PICK_LIFT_MM, radius=0,
                    speed=config.MOTION_TCP_SPEED, mvacc=config.MOTION_TCP_ACC,
                    relative=True, wait=True,
                )
                if not self._check_code(code, "lift card"):
                    return
                time.sleep(config.POST_MOTION_PAUSE_S)

                code = self._arm.set_state(0)
                if not self._check_code(code, "set_state"):
                    return

                self._angle_speed = config.MOTION_TRANSIT_JOINT_SPEED
                self._angle_acc = config.MOTION_TRANSIT_JOINT_ACC
                code = self._arm.set_servo_angle(
                    angle=config.BARCODE_SCAN_ANGLE,
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0,
                )
                if not self._check_code(code, "move to barcode scan"):
                    return

                self._scan_barcode_and_config()

                self._angle_speed = config.MOTION_TRANSIT_JOINT_SPEED
                self._angle_acc = config.MOTION_TRANSIT_JOINT_ACC
                for label in ("place 1", "place 2"):
                    code = self._arm.set_servo_angle(
                        angle=config.READER_DESCENT_STAGING_ANGLE,
                        speed=self._angle_speed, mvacc=self._angle_acc,
                        wait=True, radius=0.0,
                    )
                    if not self._check_code(code, f"move to {label}"):
                        return

                    result = self._descend_until_read()
                    if not self._raise_after_descent(result.dropped_mm, f"raise from {label}"):
                        return

                code = self._arm.set_servo_angle(
                    angle=config.RELEASE_ANGLE,
                    speed=config.RELEASE_SPEED,
                    mvacc=config.RELEASE_ACC,
                    wait=True, radius=0.0,
                )
                if not self._check_code(code, "move to final position"):
                    return
                if config.RELEASE_DWELL_S > 0:
                    time.sleep(config.RELEASE_DWELL_S)

                code = self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
                if not self._check_code(code, "suction off"):
                    return

                print(f">> Cycle {i + 1} complete in {time.monotonic() - t1:.2f}s")

        except Exception as e:
            self.pprint(f"MainException: {e}")
        finally:
            if self._stop_event.is_set():
                self.clean_stop()
            else:
                self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
                self._arm.set_servo_angle(
                    angle=config.HOME_ANGLE,
            speed=config.MOTION_PARK_JOINT_SPEED,
            mvacc=config.MOTION_PARK_JOINT_ACC,
            wait=True, radius=0.0,
                )
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)
            self._arm.disconnect()
            print(">> Arm disconnected. Done.")


if __name__ == "__main__":
    RobotMain.pprint(f"xArm-Python-SDK Version: {version.__version__}")
    arm = XArmAPI(config.ROBOT_IP, baud_checkset=False)
    time.sleep(0.5)
    RobotMain(arm).run()
