"""GuiRobot — barcode wave + multi-angle read-height / tap-and-go / deadzone orchestration.

Role
    GUI subclass of ``robot.move.RobotMain``. Adds barcode-scanner wiggle,
    per-angle staging, zone-in measurement, flip, Tap-and-Go timing, Deadzone
    ascent, Combined runs, and abort/telemetry hooks used by ``app.App``.

Inputs
    ``XArmAPI`` arm handle (via ``RobotMain``); run config set on the instance
    by the GUI (``cfg_cycles``, ``cfg_angles``, ``cfg_flip``, presets, etc.).

Outputs / hardware side effects
    Moves the Lite 6, operates suction, configures the WAVE ID reader via
    RRMTool CLI, listens for barcode / credential wedge reads, appends result
    rows for the GUI to CSV-export.

Cut-and-paste extraction from gui.py (Phase 3). Motion / timing / poses /
CSV behavior must stay identical to the pre-split monolith.
"""

import os
import sys
import time
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

import config
from robot.move import RobotMain
try:
    from robot.move import CardReadListener
except Exception:      # pragma: no cover
    CardReadListener = None
from barcode.scanner import BarcodeListener, lookup_card
from reader.cli import configure_reader_for_card

from constants import (
    TABLE_Z,
    READ_ANGLES, LITE6_JOINT_LIMITS, JOINT_LIMIT_MARGIN_DEG,
    nearest_j6_in_range, joint_limit_issues,
    FINAL_TAP_STEP_MM, DESCENT_PRESETS, DEFAULT_PRESET,
    FIXED_ZONE_TAPS, FIXED_REMEASURES,
    REFINE_CLEARANCE_MM,
    FAST_TAP_SPEED_MM_S, FAST_TAP_STEP_MM, FAST_TAP_DWELL_S,
    DROP_ANGLE, DROP_CLEARANCE_MM, DROP_HOVER_ANGLE,
    READER_STAGING_0_ANGLE, PICK_ANGLE,
    READER_PARALLEL_ROLL_DEG, READER_PARALLEL_PITCH_DEG,
    FLIP_SET_DOWN_PATH, FLIP_RETRACT_LIFT_MM, FLIP_REGRAB_POSE, FLIP_GRAB_STROKE_MM,
    FLIP_JOINT_SPEED, FLIP_JOINT_ACC, FLIP_TCP_SPEED, FLIP_TCP_ACC,
    FLIP_GRAB_TCP_SPEED, FLIP_GRAB_TCP_ACC, FLIP_RELEASE_DWELL_S, FLIP_SETTLE_S,
    TAPGO_DESCENT_SPEED_MM_S, TAPGO_DESCENT_ACC, TAPGO_APPROACH_ABOVE_READER_MM,
    TAPGO_RESET_DWELL_S, TAPGO_READ_TIMEOUT_S, TAPGO_STOP_ABOVE_FLOOR_MM,
    DEADZONE_GAP_CONFIRM_STEPS, DEADZONE_EOF_STEPS,
    DEADZONE_MAX_ABOVE_READER_MM, DEADZONE_MAX_TRAVEL_S,
    DEADZONE_DWELL_S, DEADZONE_SETTLE_S, DEADZONE_FLOOR_READ_TIMEOUT_S,
    WIGGLE_DEG, WIGGLE_LIFT_DEG, WIGGLE_SPEED, WIGGLE_ACC, WIGGLE_PAUSE_S,
    SAFETY_MARGIN_MM,
)


# ===========================================================================
# ROBOT: subclass of the unchanged RobotMain
# ===========================================================================
class GuiRobot(RobotMain):
    """Barcode-scanner wave + configurable 4-angle run + read-height capture.

    All real motion uses the inherited (working) methods. Only the barcode
    wave, the per-angle staging pose, and the run/record orchestration are
    added here.
    """

    # 0°/90°/180°/270° about the card normal == wrist (J6) offsets. On this
    # rig, +J6 rotates the card +physical°, so each read angle uses a POSITIVE
    # J6 offset equal to the angle itself.
    # Read angle → wrist (J6) rotation applied to the jogged 0° staging pose
    # (READER_STAGING_0_ANGLE). On this rig +J6 = +physical°, so each angle
    # just adds its own value at the wrist. Net J6 values land at
    # −270.8 / −180.8 / −90.8 / −0.8 for 0/90/180/270 — a smooth monotonic
    # sweep, all inside the ±360° wrist range. 90° reproduces the validated
    # orthogonal wrist (−180.8 ... i.e. −90.8 relative), 270° = raw staging.
    _ANGLE_J6_OFFSET = {0: 0.0, 90: 90.0, 180: 180.0, 270: 270.0}

    def diagnose_fault(self, context=""):
        """When something fails, read the arm's actual error/state/joints and
        say WHICH joint (if any) is at/past a limit — the usual cause of C23.
        Read-only; safe to call in any state."""
        try:
            err = self._arm.error_code
            warn = self._arm.warn_code
            state = self._arm.state
            print(">> DIAGNOSIS{}: error={} warn={} state={}".format(
                " ({})".format(context) if context else "", err, warn, state))
            ret = self._arm.get_servo_angle()
            if ret[0] == 0 and ret[1]:
                joints = list(ret[1])[:6]
                print(">>   joints: [{}]".format(
                    ", ".join("{:.1f}".format(a) for a in joints)))
                issues = joint_limit_issues(joints)
                if issues:
                    for msg in issues:
                        print(">>   *** {}".format(msg))
                    print(">>   FIX: in UFACTORY Studio use Manual Mode to drag the "
                          "joint(s) above back toward mid-range, then Clear Error + Enable.")
                elif err == 23:
                    print(">>   C23 reported but all joints read in-range now — the "
                          "limit was hit mid-move. Note which motion was running.")
        except Exception as e:
            print(">> DIAGNOSIS failed: {}".format(e))

    def _check_code(self, code, label):
        """Same pass/fail as the base check, plus an automatic fault autopsy on
        failure so C23-style errors name the offending joint in the log."""
        ok = super()._check_code(code, label)
        if not ok:
            self.diagnose_fault(label)
        return ok

    def init_gui(self):
        """Initialize GUI-tunable run config defaults (cycles, angles, presets)."""
        self.cfg_cycles = 1
        self.cfg_run_id = 1                        # set per run by the GUI
        self.cfg_scans = FIXED_REMEASURES         # always 1 — hard-coded
        self.cfg_taps = FIXED_ZONE_TAPS           # always 3 — hard-coded
        self.cfg_angles = list(READ_ANGLES)       # which angles to measure
        self.cfg_flip = False                      # test both sides (flip after A)
        self.cfg_staging_0 = list(READER_STAGING_0_ANGLE)  # 0° staging pose (calibratable)
        self.cfg_preset = DEFAULT_PRESET          # "Slow" / "Medium" / "Fast"
        # Preset-driven descent parameters (final tap = recorded; middle tap
        # bridges from the always-fast coarse tap 0 down to the recorded tap).
        default = DESCENT_PRESETS[DEFAULT_PRESET]
        self.cfg_descent_speed = default["final_speed_mm_s"]   # final tap speed
        self.cfg_final_step_mm = default["final_step_mm"]      # final tap step
        self.cfg_mid_speed_mm_s = default["mid_speed_mm_s"]    # middle tap speed
        self.cfg_mid_step_mm = default["mid_step_mm"]          # middle tap step
        self.cfg_descent_step = config.READER_DESCENT_STEP_MM  # (kept for compat)
        self.cfg_retries = 3
        self.cfg_reader_height = None          # mm, table-to-top of selected reader
        # Descent floor (mm above table) captured by MARK READER TOP. When set,
        # the arm will not descend below this height (the reader top). None =
        # fall back to config.READER_DESCENT_MIN_HEIGHT_MM.
        self.cfg_reader_floor_above_table = None
        self.cfg_safety_margin = SAFETY_MARGIN_MM
        self._on_progress = None
        self._on_result = None
        self._last_barcode = None
        self.results = []
        self.suction_on = False            # mirrored for live 3D card mesh
        self._tcp_speed = config.MOTION_TCP_SPEED
        self._tcp_acc = config.MOTION_TCP_ACC
        self._angle_speed = config.MOTION_JOINT_SPEED
        self._angle_acc = config.MOTION_JOINT_ACC

    def _set_suction(self, on, wait=False, delay_sec=0):
        """Set vacuum and mirror ``suction_on`` for the browser workcell view.

        Same SDK call as ``set_suction_cup(..., hardware_version=1)`` — timing
        and wait semantics are unchanged; only a boolean flag is recorded.
        """
        self.suction_on = bool(on)
        return self._arm.set_suction_cup(
            bool(on), wait=wait, delay_sec=delay_sec, hardware_version=1,
        )

    def apply_preset(self, preset_name):
        """Point the descent parameters at a Slow/Medium/Fast preset."""
        if preset_name not in DESCENT_PRESETS:
            preset_name = DEFAULT_PRESET
        p = DESCENT_PRESETS[preset_name]
        self.cfg_preset = preset_name
        self.cfg_descent_speed = p["final_speed_mm_s"]
        self.cfg_final_step_mm = p["final_step_mm"]
        self.cfg_mid_speed_mm_s = p["mid_speed_mm_s"]
        self.cfg_mid_step_mm = p["mid_step_mm"]

    # ---- per-angle staging pose ----
    def _staging_pose_for_angle(self, angle_deg):
        """The jogged 0° staging pose with only the wrist (J6) rotated for the
        requested read angle.

        Every angle keeps the same J1–J5 (so the card stays centred on the
        reader) and differs only at the wrist. Result is wrapped into the arm's
        ±360° range if needed (physically identical modulo 360°).
        """
        base = list(getattr(self, "cfg_staging_0", None) or READER_STAGING_0_ANGLE)
        j6 = base[5] + self._ANGLE_J6_OFFSET.get(angle_deg, 0.0)
        wrapped = j6
        while wrapped > 360.0:
            wrapped -= 360.0
        while wrapped < -360.0:
            wrapped += 360.0
        if abs(wrapped - j6) > 0.001:
            print(">>   Note: J6 for {}° wrapped {:.1f}->{:.1f} to stay in range".format(
                angle_deg, j6, wrapped))
        base[5] = wrapped
        return base

    # ---- descent floor (overrides RobotMain to honor a calibrated reader top) ----
    def _reader_floor_above_table(self):
        """Lowest allowed TCP height above the table (mm).

        When MARK READER TOP has been used this session, that captured reader
        top is the floor — the arm never descends past it. Otherwise falls back
        to the configured default so behaviour is unchanged for uncalibrated
        runs.
        """
        f = getattr(self, "cfg_reader_floor_above_table", None)
        if f is not None:
            return f
        return config.READER_DESCENT_MIN_HEIGHT_MM

    def _floor_above_table_mm(self):
        return self._reader_floor_above_table()

    def _max_drop_to_floor(self, *, include_start_lift=True):
        """Max downward travel before hitting the (possibly calibrated) floor."""
        ret = self._arm.get_position()
        if ret[0] != 0:
            return config.READER_DESCENT_MAX_DROP_MM
        z_start = ret[1][2]
        if include_start_lift:
            z_start += config.READER_DESCENT_START_LIFT_MM
        floor_z = config.TABLE_Z_MM + self._reader_floor_above_table()
        allowed = z_start - floor_z
        return max(0.0, min(allowed, config.READER_DESCENT_MAX_DROP_MM))

    # ---- wiggle override (barcode scan) ----
    def _scan_barcode_and_config(self, timeout=30, *, continuous=False):
        """Wave (wrist turn + up/down) in front of the scanner while waiting
        for a barcode, then configure the reader for the matched card.

        ``continuous=True`` loads a short-lockout HWG patch so the reader keeps
        emitting credential wedge events while the card stays in the field
        (used by the Deadzone ascent test).
        """
        ret = self._arm.get_servo_angle()
        base = list(ret[1]) if ret[0] == 0 else list(config.BARCODE_SCAN_ANGLE)

        result = {}
        event = threading.Event()

        def on_barcode(barcode):
            if result.get('card'):
                return
            card = lookup_card(barcode)
            if card:
                result['card'] = card
                result['barcode'] = barcode
                event.set()
                print('>> Barcode {} -> {} (side {})'.format(
                    barcode, card.get('name', '?'), card.get('side', '?')))
            else:
                print('>> Unknown barcode: {}'.format(barcode))

        listener = BarcodeListener(
            on_barcode,
            tk_root=getattr(self, "tk_root", None),
            force_capture=True,
        )
        listener.start()
        print('>> Waving (turn + up/down) in front of barcode scanner...')

        # Lengthen slightly — always-on-top GUI + wave motion needs headroom.
        # force_capture=True so Comment/Cards focus cannot discard wedge keys.
        # (Previously every scan was ignored while any Entry had focus.)
        deadline = time.monotonic() + max(timeout, 30)
        moves = [
            ( WIGGLE_DEG,  WIGGLE_LIFT_DEG),   # turn one way, lift up
            (-WIGGLE_DEG, -WIGGLE_LIFT_DEG),   # turn other way, dip down
            ( 0.0,         0.0),               # back to center
        ]
        try:
            while self.is_alive and not event.is_set() and time.monotonic() < deadline:
                for turn, lift in moves:
                    if event.is_set() or not self.is_alive:
                        break
                    ang = list(base)
                    ang[1] += lift    # J2 (shoulder) → up/down wave
                    ang[5] += turn    # J6 (wrist)    → turn
                    self._arm.set_servo_angle(
                        angle=ang, speed=WIGGLE_SPEED, mvacc=WIGGLE_ACC,
                        wait=True, radius=0.0)
                    pause_end = time.monotonic() + WIGGLE_PAUSE_S
                    while time.monotonic() < pause_end and not event.is_set():
                        time.sleep(0.02)
        finally:
            listener.stop()
            # return to the scan pose so the next move starts from a known spot
            try:
                self._arm.set_servo_angle(
                    angle=base, speed=WIGGLE_SPEED, mvacc=WIGGLE_ACC,
                    wait=True, radius=0.0)
            except Exception:
                pass

        card = result.get('card')
        self._last_barcode = result.get('barcode')
        if not card:
            print('>> No valid barcode read.')
            return None

        mode = " (continuous)" if continuous else ""
        print('>> Configuring reader for {}{}...'.format(card.get('name', '?'), mode))
        ok = configure_reader_for_card(card, log_fn=print, continuous=continuous)
        print('>> Reader configured.' if ok else '>> Reader configuration FAILED.')
        self._current_card = card
        return card

    @staticmethod
    def _resolve_card_side(card):
        """Card face from barcode: A = front, B = back (AllCards.csv Side column)."""
        side = (card.get("side") or "A").strip().upper()
        if side not in ("A", "B"):
            print(">> Warning: unknown card face {!r} — defaulting to A".format(side))
            side = "A"
        return side

    # ---- read-height measurement helpers ----
    def _height_above_table(self):
        ret = self._arm.get_position()
        if ret[0] != 0:
            return None
        return ret[1][2] - TABLE_Z

    def _fresh_card_data(self):
        """Reload card row from AllCards.csv (name / HWG / side)."""
        barcode = (self._current_card or {}).get("barcode") or self._last_barcode
        if barcode:
            card = lookup_card(barcode)
            if card:
                self._current_card = card
                return card
        return self._current_card or {}

    def _assumed_reader_height(self):
        """Reader top (mm above table) to plan approaches against.

        MARK READER TOP / nominal library value when known. Otherwise fall back
        to the descent floor so a run still executes instead of skipping every
        card — the floor already protects the reader.
        """
        reader_h = self.cfg_reader_height
        if reader_h is not None:
            return reader_h
        floor = self._reader_floor_above_table()
        if floor is None:
            return None
        if not getattr(self, "_warned_assumed_reader_h", False):
            print(">>   Reader height not calibrated — assuming reader top = "
                  "{:.1f}mm above table (descent floor). Run MARK READER TOP "
                  "for accurate heights.".format(floor))
            self._warned_assumed_reader_h = True
        return floor

    def _approach_start_above_reader(self):
        """Height above reader to start the fast locate (mm above reader top).

        Fixed approach — AllCards no longer stores per-card read-height baselines.
        """
        start = float(config.READER_FALLBACK_SEARCH_ABOVE_READER_MM)
        return (
            start,
            None,
            "fixed {:.1f}mm above reader".format(start),
        )

    def _move_joint(self, angle, label, *, speed=None, acc=None, radius=None, wait=True):
        """Joint move with optional corner blending for smooth transit.

        Before commanding, J6 is normalized to the nearest legal revolution
        relative to the wrist's current angle. A ±360° shift is physically
        identical, so orientation is unchanged, but the commanded number stays
        inside the ±360° limit — this stops the C23 wrist fault on the way to
        the drop bin.
        """
        angle = list(angle)
        if len(angle) >= 6:
            lo6, hi6 = LITE6_JOINT_LIMITS[5]
            m = JOINT_LIMIT_MARGIN_DEG
            # Only intervene when the commanded J6 is actually outside the legal
            # range. In-range poses (e.g. the designed staging sweep) are left
            # exactly as-is; illegal ones are pulled to an identical legal turn.
            if not (lo6 + m <= angle[5] <= hi6 - m):
                ret = self._arm.get_servo_angle()
                ref = (list(ret[1])[5]
                       if isinstance(ret, (list, tuple)) and ret[0] == 0 and ret[1]
                       else angle[5])
                safe_j6 = nearest_j6_in_range(angle[5], ref)
                print(">>   J6 {:.1f}° out of range for '{}' — using identical "
                      "legal turn {:.1f}°".format(angle[5], label, safe_j6))
                angle[5] = safe_j6
        blend = config.MOTION_JOINT_RADIUS if radius is None else radius
        code = self._arm.set_servo_angle(
            angle=angle,
            speed=speed if speed is not None else config.MOTION_JOINT_SPEED,
            mvacc=acc if acc is not None else config.MOTION_JOINT_ACC,
            wait=wait,
            radius=blend,
        )
        return self._check_code(code, label)

    def _move_to_height_above_table(
        self, height_mm, label="position above table", *,
        speed=None, acc=None, radius=None,
    ):
        ret = self._arm.get_position()
        if ret[0] != 0:
            return False
        pos = ret[1]
        target_z = TABLE_Z + height_mm
        blend = config.MOTION_TCP_RADIUS if radius is None else radius
        code = self._arm.set_position(
            x=pos[0], y=pos[1], z=target_z,
            roll=pos[3], pitch=pos[4], yaw=pos[5],
            radius=blend,
            speed=speed if speed is not None else self._tcp_speed,
            mvacc=acc if acc is not None else self._tcp_acc,
            wait=True,
        )
        return self._check_code(code, label)

    def _move_to_approach_for_orientation(self, orientation):
        """Move TCP above reader using the fixed approach clearance (absolute Z)."""
        reader_h = self._assumed_reader_height()
        if reader_h is None:
            print(">>   ERROR: reader top unknown and no descent floor — "
                  "calibrate the reader (MARK READER TOP)")
            return False

        start_above_reader, peak_ref, src = self._approach_start_above_reader()
        # Position TCP so the card face (not flange) is at start_above_reader.
        target_above_table = config.tcp_above_table_for_card_face(
            reader_h + start_above_reader,
        )
        current = self._height_above_table()
        if current is not None:
            print(
                ">>   Approach {} — {} = {:.2f}mm above reader "
                "({:.2f}mm above table, currently {:.2f}mm)".format(
                    orientation, src, start_above_reader, target_above_table, current,
                )
            )
            if abs(current - target_above_table) <= 0.5:
                print(">>   Approach {} — already at target height".format(orientation))
                return True
            if current > target_above_table:
                return self._move_to_height_above_table(
                    target_above_table,
                    "approach {} (slow descent)".format(orientation.lower()),
                    speed=self.cfg_descent_speed,
                    acc=config.READ_HEIGHT_DESCENT_ACC,
                )
        return self._move_to_height_above_table(
            target_above_table, "approach {}".format(orientation.lower()),
        )

    def _clear_reader_after_side(self):
        """Return to a safe height above the reader after one orientation."""
        reader_h = self.cfg_reader_height
        if reader_h is None:
            return True
        target = reader_h + config.READER_CLEAR_AFTER_SIDE_ABOVE_READER_MM
        current = self._height_above_table()
        if current is not None and current >= target - 0.5:
            print(
                ">>   Clear after side OK — {:.1f}mm above table "
                "({:.0f}mm above reader)".format(current, current - reader_h)
            )
            return True
        return self._move_to_height_above_table(target, "clear reader after side")

    def _ensure_clearance_above_reader(self, minimum_above_reader_mm=None):
        """Rise to at least N mm above the reader top (before leaving the read area)."""
        if minimum_above_reader_mm is None:
            minimum_above_reader_mm = config.READER_PRE_RELEASE_CLEARANCE_ABOVE_READER_MM
        reader_h = self.cfg_reader_height
        if reader_h is None:
            print(">>   Pre-release clearance — lifting {:.0f}mm (reader height unknown)".format(
                minimum_above_reader_mm))
            code = self._arm.set_position(
                z=minimum_above_reader_mm, radius=config.MOTION_TCP_RADIUS,
                speed=config.MOTION_EXIT_TCP_SPEED, mvacc=config.MOTION_EXIT_TCP_ACC,
                relative=True, wait=True,
            )
            return self._check_code(code, "pre-release clearance")

        target_above_table = reader_h + minimum_above_reader_mm
        current = self._height_above_table()
        if current is not None and current >= target_above_table - 0.5:
            print(
                ">>   Pre-release clearance OK — {:.1f}mm above table "
                "({:.0f}mm above reader)".format(
                    current, current - reader_h,
                )
            )
            return True
        print(
            ">>   Pre-release — rising to {:.1f}mm above table "
            "({:.0f}mm above reader)".format(target_above_table, minimum_above_reader_mm)
        )
        return self._move_to_height_above_table(
            target_above_table, "pre-release clearance",
            speed=config.MOTION_EXIT_TCP_SPEED, acc=config.MOTION_EXIT_TCP_ACC,
        )

    def _exit_reader_and_release(self):
        """Mandatory clearance above reader, then smooth fast drop + release."""
        if not self._ensure_clearance_above_reader():
            return False
        return self._release_card()

    def _read_height_above_reader(self, tcp_height_above_table):
        """Card clearance above reader top (mm), corrected for suction cup offset."""
        if tcp_height_above_table is None:
            return None
        card_above_table = config.card_face_above_table_from_tcp(tcp_height_above_table)
        reader_h = self._assumed_reader_height()
        if reader_h is None:
            return card_above_table
        return card_above_table - reader_h

    def _move_to_staging(self, pose, label):
        if not self._move_joint(
            pose, label, radius=config.MOTION_JOINT_RADIUS,
        ):
            return False
        # Taught staging joints can leave the flange tilted (e.g. J5 ≠ tool-down).
        # Force card parallel to the reader before approach / descent. A refused
        # levelling move (IK / joint limit) must not abandon the measurement —
        # the taught pose is still usable, just less parallel.
        if not self._level_tool_parallel_to_reader():
            print(">>   Continuing with the taught staging orientation.")
        return True

    def _level_tool_parallel_to_reader(self):
        """Set roll/pitch so the card face is parallel to a flat table reader.

        UFactory tool-down is roll=±180°, pitch=0°. Yaw (in-plane card angle)
        is preserved. No-op if already within 0.5°.
        """
        ret = self._arm.get_position()
        if ret[0] != 0 or not ret[1]:
            print(">>   Level parallel — get_position failed ({})".format(ret[0]))
            return False
        x, y, z, roll, pitch, yaw = ret[1][:6]
        want_roll = float(READER_PARALLEL_ROLL_DEG)
        # ±180° are the same attitude; pick the nearer sign to avoid a long spin.
        if abs((-want_roll) - roll) < abs(want_roll - roll):
            want_roll = -want_roll
        want_pitch = float(READER_PARALLEL_PITCH_DEG)
        if abs(roll - want_roll) < 0.5 and abs(pitch - want_pitch) < 0.5:
            print(">>   Tool already parallel to reader "
                  "(R={:.1f}° P={:.1f}° Y={:.1f}°)".format(roll, pitch, yaw))
            return True
        print(
            ">>   Leveling card parallel to reader: "
            "R {:.1f}→{:.1f}°, P {:.1f}→{:.1f}° (yaw {:.1f}° kept)".format(
                roll, want_roll, pitch, want_pitch, yaw,
            )
        )
        code = self._arm.set_position(
            x=x, y=y, z=z,
            roll=want_roll, pitch=want_pitch, yaw=yaw,
            radius=0.0,
            speed=min(float(self._tcp_speed), 80.0),
            mvacc=self._tcp_acc,
            wait=True,
        )
        return self._check_code(code, "level tool parallel to reader")

    def _lift_for_refine(self):
        """Rise above the last read point before the next zone-in tap."""
        lift = REFINE_CLEARANCE_MM
        code = self._arm.set_position(
            z=lift, radius=0,
            speed=min(self.cfg_descent_speed * 4, 40.0),
            mvacc=config.READ_HEIGHT_DESCENT_ACC,
            relative=True, wait=True,
        )
        return self._check_code(code, "lift for refine scan")

    @staticmethod
    def _zone_tap_count(taps):
        """Descents per measure: 1 tap => fast zone + one slow; N>=2 => N taps."""
        return 2 if taps <= 1 else taps

    def _zone_tap_params(self, tap_index, tap_total):
        """Speed/step/dwell for one zone-in tap.

        With FIXED_ZONE_TAPS = 3 there are three descents per angle:
          • tap 0 (fast):      always aggressive — coarse locate, not recorded
          • tap 1 (middle):    preset-scaled — bridges to the final tap
          • tap 2 (recorded):  preset-scaled — slowest, height IS recorded

        If a caller ever passes tap_total != 3, extra middle taps just repeat
        the middle-tap parameters, so behaviour degrades gracefully.
        """
        record = tap_index == tap_total - 1
        if tap_index == 0:
            return {
                "speed": FAST_TAP_SPEED_MM_S,
                "step": FAST_TAP_STEP_MM,
                "dwell_s": FAST_TAP_DWELL_S,
                "settle_s": 0.0,
                "record": False,
            }
        if record:
            return {
                "speed": self.cfg_descent_speed,   # preset final speed
                "step": self.cfg_final_step_mm,    # preset final step
                "dwell_s": config.READER_DESCENT_DWELL_S,
                "settle_s": config.READER_DESCENT_SETTLE_S,
                "record": True,
            }
        # Middle tap — preset-scaled, dwell/settle between fast and slow.
        return {
            "speed": self.cfg_mid_speed_mm_s,
            "step": self.cfg_mid_step_mm,
            "dwell_s": (FAST_TAP_DWELL_S + config.READER_DESCENT_DWELL_S) / 2.0,
            "settle_s": config.READER_DESCENT_SETTLE_S / 2.0,
            "record": False,
        }

    def _zone_in_measure_read(self, taps, *, from_approach=False, skip_fast_zone=False):
        """Progressive zone-in descents; only the final tap height is recorded."""
        tap_total = self._zone_tap_count(taps)
        recorded = None

        for tap_i in range(tap_total):
            if tap_i > 0:
                if not self._lift_for_refine():
                    return None

            params = self._zone_tap_params(tap_i, tap_total)
            if skip_fast_zone and tap_i == 0:
                sub = 1 if tap_total > 2 else tap_total - 1
                params = {**self._zone_tap_params(sub, tap_total), "record": False}
            if tap_i == 0 and from_approach and not skip_fast_zone:
                max_drop = self._max_drop_to_floor(include_start_lift=False)
            else:
                max_drop = REFINE_CLEARANCE_MM + config.READER_REFINE_MAX_DROP_MM

            if max_drop <= 0.0:
                print(">>   Zone tap {}: skip — no descent room".format(tap_i + 1))
                return None

            label = "record" if params["record"] else "zone"
            print(
                ">>   Zone tap {}/{} ({}) — {:.1f} mm/s, {:.1f}mm steps, "
                "{:.2f}s listen".format(
                    tap_i + 1, tap_total, label,
                    params["speed"], params["step"], params["dwell_s"],
                )
            )
            result = self._descend_until_read(
                max_drop=max_drop,
                step=params["step"],
                speed=params["speed"],
                start_lift_mm=0,
                dwell_s=params["dwell_s"],
                settle_s=params["settle_s"],
            )
            if not result.read_found:
                print(">>   Zone tap {}: no read".format(tap_i + 1))
                return None

            h = result.height_above_table_mm
            if h is None:
                h = self._height_above_table()
            if h is not None and not params["record"]:
                print(
                    ">>   Zone tap {}: read at {:.2f}mm above table "
                    "(not recorded)".format(tap_i + 1, h)
                )
            if params["record"] and h is not None:
                recorded = h

        return recorded

    def _final_tap_read(self):
        """One slow recorded descent from refine clearance (after zone-in is done)."""
        params = {
            "speed": self.cfg_descent_speed,
            "step": FINAL_TAP_STEP_MM,   # slowest tap: arm's finest practical step
            "dwell_s": config.READER_DESCENT_DWELL_S,
            "settle_s": config.READER_DESCENT_SETTLE_S,
        }
        max_drop = REFINE_CLEARANCE_MM + config.READER_REFINE_MAX_DROP_MM
        print(
            ">>   Slow remeasure — {:.1f} mm/s, {:.1f}mm steps, {:.2f}s listen".format(
                params["speed"], params["step"], params["dwell_s"],
            )
        )
        result = self._descend_until_read(
            max_drop=max_drop,
            step=params["step"],
            speed=params["speed"],
            start_lift_mm=0,
            dwell_s=params["dwell_s"],
            settle_s=params["settle_s"],
        )
        if not result.read_found:
            return None
        h = result.height_above_table_mm
        if h is None:
            h = self._height_above_table()
        return h

    def _fast_locate_read(self):
        """Fast descent from staging until first read — height is NOT recorded."""
        cap = self._max_drop_to_floor(include_start_lift=False)
        if cap <= 0.0:
            print('>>   Skip descent: already at/below floor.')
            return False
        print('>>   Fast locate — descending from staging, floor {:.1f}mm above table (height not recorded)'.format(
            config.READER_DESCENT_MIN_HEIGHT_MM))
        result = self._descend_until_read(
            max_drop=cap,
            step=FAST_TAP_STEP_MM,
            speed=FAST_TAP_SPEED_MM_S,
            start_lift_mm=0,
            dwell_s=FAST_TAP_DWELL_S,
            settle_s=0.0,
        )
        if result.read_found:
            h = result.height_above_table_mm
            if h is None:
                h = self._height_above_table()
            if h is not None:
                print('>>   Fast read at {:.2f}mm above table — reference only, not recorded'.format(h))
            else:
                print('>>   Fast read detected — reference only, not recorded')
        return result.read_found

    def _slow_measure_read(self, *, prepare_next=True):
        """Slow descent from refine clearance; this height IS recorded."""
        max_drop = REFINE_CLEARANCE_MM + config.READER_REFINE_MAX_DROP_MM
        print('>>   Slow measure — {:.0f}mm descent from {:.0f}mm above reference at {:.1f} mm/s'.format(
            max_drop, REFINE_CLEARANCE_MM, self.cfg_descent_speed))
        result = self._descend_until_read(
            max_drop=max_drop,
            step=self.cfg_descent_step,
            speed=self.cfg_descent_speed,
            start_lift_mm=0,
            dwell_s=config.READER_DESCENT_DWELL_S,
            settle_s=config.READER_DESCENT_SETTLE_S,
        )
        height = result.height_above_table_mm if result.read_found else None
        if height is None and result.read_found:
            height = self._height_above_table()
        if result.read_found and height is not None:
            if prepare_next:
                self._lift_for_refine()
            return height
        return None

    def _measure_orientation(self, orientation, pose, scans, *, clear_after=False, skip_fast_zone=False):
        """Measure read height at one reader angle (0/90/180/270).

        Moves to the (angle-specific) staging pose, approaches from above,
        finds the read height with progressive zone-in taps (each slower than
        the last, final tap slowest and recorded), then does `scans - 1` slow
        remeasures. Returns the list of recorded heights (mm above reader).
        """
        heights = []
        taps = self.cfg_taps

        if self.cfg_reader_height is None:
            print('>> Warning: reader height not calibrated — heights are '
                  'relative to the assumed reader top. Use MARK READER TOP.')

        if not self._move_to_staging(pose, '{} orientation'.format(orientation)):
            return heights

        if not self._move_to_approach_for_orientation(orientation):
            return heights

        print(
            ">>   {} — zone-in {} tap(s) once{}, then {} slow remeasure(s) "
            "(final {:.1f} mm/s)".format(
                orientation,
                taps,
                " (refine start)" if skip_fast_zone else "",
                max(0, scans - 1),
                self.cfg_descent_speed,
            )
        )

        self._progress(
            self._cur_cycle, self.cfg_cycles,
            "{} — zone-in".format(orientation),
        )
        h_table = self._zone_in_measure_read(
            taps, from_approach=True, skip_fast_zone=skip_fast_zone,
        )

        if h_table is None:
            print('>>   {} zone-in: no read — clearing and retrying'.format(orientation))
            if not self._clear_reader_after_side():
                return heights
            if not self._move_to_staging(pose, '{} orientation (retry)'.format(orientation)):
                return heights
            if not self._move_to_approach_for_orientation(orientation):
                return heights
            h_table = self._zone_in_measure_read(taps, from_approach=True)

        if h_table is not None:
            read_h = self._read_height_above_reader(h_table)
            if read_h is not None:
                heights.append(round(read_h, 2))
                print('>>   {} measure 1: {:.2f}mm above reader (card {:.2f}mm above table)'.format(
                    orientation, read_h,
                    config.card_face_above_table_from_tcp(h_table),
                ))

        for s in range(1, scans):
            if not self.is_alive:
                break
            if not heights:
                break
            self._progress(
                self._cur_cycle, self.cfg_cycles,
                "{} — remeasure {}/{}".format(orientation, s + 1, scans),
            )
            if not self._lift_for_refine():
                break
            h_table = self._final_tap_read()
            read_h = self._read_height_above_reader(h_table)
            if read_h is not None:
                heights.append(round(read_h, 2))
                print('>>   {} measure {}: {:.2f}mm above reader (card {:.2f}mm above table)'.format(
                    orientation, s + 1, read_h,
                    config.card_face_above_table_from_tcp(h_table),
                ))
            else:
                print('>>   {} measure {}: no read'.format(orientation, s + 1))

        if clear_after:
            self._clear_reader_after_side()
        return heights

    def _hover_above_pose(self, angle, clearance_mm, label):
        """Position the TCP `clearance_mm` above the TCP position of a joint pose,
        WITHOUT ever letting the controller re-solve the wrist.

        This is the fix for the C23-at-drop fault. The old version made a
        Cartesian set_position to the raised point; because a Cartesian move
        lets IK pick any wrist revolution, from a deeply-wound read pose (e.g.
        J6 = -270.8°) it could resolve the wrist to the identical-but-illegal
        -630.8° (= -270.8° - 360°) and trip the limit.

        Now: compute the raised TCP via FK, solve it back to joints via IK, then
        PIN J6 to the input pose's wrist (`angle[5]`) — the +Z lift doesn't
        rotate the wrist, so its correct value is unchanged — and execute a pure
        JOINT move. The wrist is never re-solved, so it cannot cross the limit.
        Falls back to a plain relative lift if FK/IK is unavailable.
        """
        angle = list(angle)
        fk = None
        try:
            fk = self._arm.get_forward_kinematics(
                angle, input_is_radian=False, return_is_radian=False)
        except Exception as e:
            print(">>   FK call failed ({}) — will lift relative instead".format(e))

        if isinstance(fk, (list, tuple)) and fk[0] == 0 and fk[1] and len(fk[1]) >= 6:
            x, y, z, roll, pitch, yaw = fk[1][:6]
            ik = None
            try:
                ik = self._arm.get_inverse_kinematics(
                    [x, y, z + clearance_mm, roll, pitch, yaw],
                    input_is_radian=False, return_is_radian=False)
            except Exception as e:
                print(">>   IK call failed ({}) — will lift relative instead".format(e))
            if isinstance(ik, (list, tuple)) and ik[0] == 0 and ik[1] and len(ik[1]) >= 6:
                hover = list(ik[1])[:6]
                hover[5] = angle[5]   # pin wrist to the read-time value (no re-solve)
                print(">>   Hover above drop (joint move), wrist pinned at J6 = "
                      "{:.1f}°".format(hover[5]))
                return self._move_joint(
                    hover, label,
                    speed=config.RELEASE_SPEED, acc=config.RELEASE_ACC,
                )
            # IK unavailable: fall through to a safe relative lift (no re-solve).

        print(">>   FK/IK unavailable — lifting {:.0f}mm relative before drop".format(clearance_mm))
        code = self._arm.set_position(
            z=clearance_mm, relative=True,
            speed=self._tcp_speed, mvacc=self._tcp_acc, wait=True,
        )
        return self._check_code(code, label + " (relative lift)")

    def _release_card(self):
        """Hover ≥DROP_CLEARANCE_MM above the drop point, descend to the drop
        pose, brief pause, then release suction.

        The drop pose is the fixed, hand-jogged DROP_ANGLE (all six joints,
        including the wrist). Because that pose was jogged to a safe wrist
        (J6 = -179.8°) well inside the range, the move from any read angle to
        the drop stays clear of the ±360° limit. Both the hover and the descent
        are pure JOINT moves — no Cartesian re-solve of the wrist — so J6 is
        commanded exactly and never crosses its limit. The hover-first step
        guarantees the arm clears everything on the way over before it comes
        down to drop."""
        drop_pose = list(DROP_ANGLE)

        # 1) Hover above the drop point (pure joint move, wrist fixed at the
        #    drop pose's J6 so the traverse cannot wind past the limit).
        if DROP_HOVER_ANGLE is not None:
            hover_pose = list(DROP_HOVER_ANGLE)
            hover_pose[5] = drop_pose[5]   # keep the drop wrist here too
            print(">>   Release — hover (joint pose), descend to drop, release")
            if not self._move_joint(
                hover_pose, "drop hover",
                speed=config.RELEASE_SPEED, acc=config.RELEASE_ACC,
            ):
                return False
        else:
            print(">>   Release — hover {:.0f}mm above drop (joint), descend, release".format(
                DROP_CLEARANCE_MM))
            if not self._hover_above_pose(drop_pose, DROP_CLEARANCE_MM, "hover above drop"):
                return False

        # 2) Descend to the drop pose (joint move).
        if not self._move_joint(
            drop_pose, "drop pose",
            speed=config.RELEASE_SPEED, acc=config.RELEASE_ACC,
        ):
            return False

        # 3) Settle, then release.
        if config.RELEASE_DWELL_S > 0:
            time.sleep(config.RELEASE_DWELL_S)
        code = self._set_suction(False, wait=True, delay_sec=0)
        return self._check_code(code, "release card")

    def _flip_card(self):
        """Place the just-tested card in the flip fixture, release it, and
        re-pick it flipped so the other side faces the reader.

        Faithful translation of the Studio flip program, run with wait=True and
        code-checks on every step. All joint moves + pure-vertical relative Z.
        Assumes the card is already clear of the reader (caller lifts first).
        Returns True on success."""
        print(">> FLIP — placing card in fixture and re-picking the other side")
        # 1) carry the card down into the flip fixture
        for n, pose in enumerate(FLIP_SET_DOWN_PATH, 1):
            if not self.is_alive:
                return False
            code = self._arm.set_servo_angle(
                angle=pose, speed=FLIP_JOINT_SPEED, mvacc=FLIP_JOINT_ACC,
                wait=True, radius=0.0)
            if not self._check_code(code, "flip set-down {}".format(n)):
                return False
        # 2) release the card into the fixture
        # 2) release the card into the fixture (wait=False: don't wait on the
        #    object-detection sensor — matches the working Studio sequence)
        code = self._set_suction(False, wait=False, delay_sec=0)
        if not self._check_code(code, "flip release"):
            return False
        if FLIP_RELEASE_DWELL_S > 0:
            time.sleep(FLIP_RELEASE_DWELL_S)
        # 3) retract straight up, clear of the fixture
        code = self._arm.set_position(
            z=FLIP_RETRACT_LIFT_MM, relative=True,
            speed=FLIP_TCP_SPEED, mvacc=FLIP_TCP_ACC, wait=True)
        if not self._check_code(code, "flip retract"):
            return False
        # 4) reposition to approach the flipped card
        code = self._arm.set_servo_angle(
            angle=FLIP_REGRAB_POSE, speed=FLIP_JOINT_SPEED, mvacc=FLIP_JOINT_ACC,
            wait=True, radius=0.0)
        if not self._check_code(code, "flip re-grab approach"):
            return False
        # 5) suction on, then descend onto the card to seal
        # 5) suction on, then descend onto the card to seal.
        #    wait=False is REQUIRED here: the card isn't under the cup yet, so
        #    waiting for object-detection would time out (code 41). The seal
        #    forms as it descends and during FLIP_SETTLE_S below.
        code = self._set_suction(True, wait=False, delay_sec=0)
        if not self._check_code(code, "flip suction on"):
            return False
        code = self._arm.set_position(
            z=-FLIP_GRAB_STROKE_MM, relative=True,
            speed=FLIP_GRAB_TCP_SPEED, mvacc=FLIP_GRAB_TCP_ACC, wait=True)
        if not self._check_code(code, "flip descend to grab"):
            return False
        # 6) settle for a good seal, then lift the flipped card out
        if FLIP_SETTLE_S > 0:
            time.sleep(FLIP_SETTLE_S)
        code = self._arm.set_position(
            z=FLIP_GRAB_STROKE_MM, relative=True,
            speed=FLIP_GRAB_TCP_SPEED, mvacc=FLIP_GRAB_TCP_ACC, wait=True)
        if not self._check_code(code, "flip lift with card"):
            return False
        print(">> FLIP — done, card flipped and re-picked")
        return True

    def _goto_scan_barcode(self, cycle, *, continuous=False):
        """Move to the barcode pose and scan + configure the reader.

        Returns (card_name, barcode) on success, or (None, None) on failure.
        Reusable per side, so a flip test re-scans the barcode before testing
        the back — the reader config must match the side currently facing out.

        ``continuous=True`` enables short-lockout continuous wedge output
        (Deadzone test).
        """
        self._progress(cycle, self.cfg_cycles, "Scanning barcode")
        if not self._move_joint(
            config.BARCODE_SCAN_ANGLE, 'barcode pose',
            radius=config.MOTION_JOINT_RADIUS,
        ):
            return None, None
        card = self._scan_barcode_and_config(continuous=continuous)
        if not card:
            return None, None
        return card.get('name'), self._last_barcode

    def _scan_and_measure(self, cycle, side_label=""):
        """Move to the barcode pose, scan + configure the reader, then measure
        every selected angle for the face currently facing out.

        `side_label` is log-only ("A"/"B" for flip pass order). Results use
        Card Code (A###/B###) — no Side column is written.
        Does NOT release the card — the caller decides whether to drop or flip.
        Returns (info_or_None, error_flag, angle_heights)."""
        self._progress(cycle, self.cfg_cycles, "Scanning barcode")
        if not self._move_joint(
            config.BARCODE_SCAN_ANGLE, 'barcode pose',
            radius=config.MOTION_JOINT_RADIUS,
        ):
            return None, "MOVE FAIL", {}

        card = self._scan_barcode_and_config()
        card_name = card.get('name') if card else None
        barcode = self._last_barcode
        if not card:
            print('>> No barcode — skipping measurement.')
            return None, "BARCODE FAIL", {}

        face = {"A": "front", "B": "back"}.get(side_label, "single side")
        print('>> Measuring {} ({}) — {} angle(s)'.format(
            face, side_label or "n/a",
            ", ".join("{}°".format(a) for a in self.cfg_angles)))

        angle_heights = {}
        for angle in self.cfg_angles:
            if not self.is_alive:
                break
            pose = self._staging_pose_for_angle(angle)
            heights = self._measure_orientation(
                "{}°".format(angle), pose, self.cfg_scans,
                clear_after=True, skip_fast_zone=False,
            )
            angle_heights[angle] = heights
        return (card_name, barcode, side_label), "", angle_heights

    def _progress(self, cycle, total, phase):
        if self._on_progress:
            self._on_progress(cycle, total, phase)

    # ---- telemetry (read-only live joint stream for the 3D view / ROS2) ----
    def start_telemetry(self, callback, hz=12.0):
        """Start a daemon thread that reports live joint angles via callback.

        ``callback(joints, suction_on)`` receives degrees and the mirrored
        suction flag. Reads the SDK's cached joint state (no extra motion
        commands). Safe no-op to call start/stop repeatedly.
        """
        self.stop_telemetry()
        self._telemetry_cb = callback
        self._telemetry_stop = threading.Event()
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop, args=(max(1.0, hz),), daemon=True)
        self._telemetry_thread.start()

    def stop_telemetry(self):
        ev = getattr(self, "_telemetry_stop", None)
        if ev is not None:
            ev.set()
        self._telemetry_thread = None

    def _telemetry_loop(self, hz):
        period = 1.0 / hz
        ev = self._telemetry_stop
        while not ev.is_set():
            try:
                ret = self._arm.get_servo_angle()
                if ret[0] == 0 and self._telemetry_cb:
                    self._telemetry_cb(
                        list(ret[1])[:6],
                        bool(getattr(self, "suction_on", False)),
                    )
            except Exception:
                pass
            ev.wait(period)

    # ---- abort (kill switch) ----
    def request_abort(self):
        """Operator Stop: set abort flag, emergency-stop the arm, then clear fault latch."""
        self._stop_event.set()
        self.alive = False
        try:
            self._arm.emergency_stop()
        except Exception:
            pass
        # emergency_stop can leave the controller latched in a fault state
        # (state=4) which makes every later command silently fail. Clear it so
        # the arm can park and the next run starts clean.
        try:
            time.sleep(0.2)
            self._arm.clean_error()
            self._arm.clean_warn()
            self._arm.set_state(0)
        except Exception:
            pass

    # ---- run(): pick → scan → measure 4 angles → release ----
    def run(self):
        """Read Height run: home → pick → scan/config → multi-angle zone-in → flip/drop.

        Hardware side effects: joint/TCP motion, suction, reader HWG load, CSV rows
        via ``self.on_result`` / print. Honors ``request_abort()``.
        """
        try:
            print('>> Homing (fast)...')
            if not self._move_joint(config.HOME_ANGLE, 'home'):
                return
            print('>> Home reached. Starting {} card(s).'.format(self.cfg_cycles))
            print(
                '>> Suction cup offset: +{:.1f}mm (card face above TCP — applied to readings)'.format(
                    config.SUCTION_CUP_CARD_OFFSET_MM,
                )
            )
            print('>> Read angles this run: {}'.format(
                ", ".join("{}°".format(a) for a in self.cfg_angles)))

            for i in range(self.cfg_cycles):
                if not self.is_alive:
                    break
                self._cur_cycle = i + 1
                self._progress(i + 1, self.cfg_cycles, "Picking card")
                print('>> ───────────────  Card {} of {}  ───────────────'.format(
                    i + 1, self.cfg_cycles))
                t1 = time.monotonic()
                error_flag = ""

                # ── Pick (with retries) ──
                pick_z = None
                pick_radius = (
                    config.MOTION_POST_RELEASE_JOINT_RADIUS
                    if i > 0 else config.MOTION_JOINT_RADIUS
                )
                for attempt in range(self.cfg_retries):
                    if not self.is_alive:
                        break
                    if not self._move_joint(
                        PICK_ANGLE, 'move to pick', radius=pick_radius,
                    ):
                        break
                    self._set_suction(True, wait=False, delay_sec=0)
                    pick_z = self.smart_pick()
                    if pick_z is not None:
                        break
                    print('>> Pick attempt {} failed.'.format(attempt + 1))
                    self._set_suction(False, wait=False, delay_sec=0)

                if pick_z is None:
                    error_flag = "PICK FAIL"
                    print('>> Skipping card {} (pick failed).'.format(i + 1))
                    if not self._move_joint(
                        config.HOME_ANGLE, 'home after pick fail',
                        radius=config.MOTION_JOINT_RADIUS,
                    ):
                        pass
                    self._emit_result(i + 1, None, {}, error_flag)
                    continue

                time.sleep(config.POST_MOTION_PAUSE_S)

                # ── Lift ──
                code = self._arm.set_position(
                    z=config.POST_PICK_LIFT_MM, radius=config.MOTION_TCP_RADIUS,
                    speed=config.MOTION_TCP_SPEED, mvacc=config.MOTION_TCP_ACC,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift'):
                    break
                time.sleep(config.POST_MOTION_PAUSE_S)
                self._arm.set_state(0)

                flip_enabled = bool(getattr(self, "cfg_flip", False))

                # ── Side A (side currently facing out) ──
                # Side is only meaningful in a flip test; blank otherwise.
                infoA, errA, heightsA = self._scan_and_measure(
                    i + 1, side_label=("A" if flip_enabled else ""))
                self._emit_result(i + 1, infoA, heightsA, errA)

                if infoA is None:
                    # Barcode/move failed — can't test or safely flip. Drop it.
                    self._progress(i + 1, self.cfg_cycles, "Releasing card")
                    self._release_card()
                    print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                    continue

                if flip_enabled:
                    # Instead of dropping: clear the reader, flip the card,
                    # then re-scan + test the other side, then drop.
                    self._progress(i + 1, self.cfg_cycles, "Clearing reader")
                    if not self._ensure_clearance_above_reader():
                        break
                    self._progress(i + 1, self.cfg_cycles, "Flipping card")
                    if not self._flip_card():
                        print('>> Flip failed — releasing card and moving on.')
                        self._release_card()
                        self._emit_result(i + 1, infoA, {}, "FLIP FAIL")
                        print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                        continue

                    # ── Side B ──
                    infoB, errB, heightsB = self._scan_and_measure(i + 1, side_label="B")
                    self._emit_result(i + 1, infoB, heightsB, errB)
                    self._progress(i + 1, self.cfg_cycles, "Clearing reader")
                    if infoB is None:
                        self._release_card()
                    else:
                        self._exit_reader_and_release()
                else:
                    self._progress(i + 1, self.cfg_cycles, "Clearing reader")
                    self._exit_reader_and_release()

                print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))

        except Exception as e:
            print('>> MainException: {}'.format(e))
        finally:
            try:
                if self._stop_event.is_set():
                    print('>> Abort — parking arm safely...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                    except Exception:
                        pass
                elif self._arm.error_code != 0 or (self._arm.state or 0) >= 4:
                    # The run ended because the arm faulted mid-motion. Explain
                    # it (naming any limit-violating joint), then try ONE
                    # recovery so we can at least drop suction and park.
                    self.diagnose_fault('end of run')
                    print('>> Attempting one recovery so the arm can park...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                        time.sleep(0.3)
                    except Exception:
                        pass
                if self._arm.error_code == 0 and (self._arm.state or 0) < 4:
                    self._set_suction(False, wait=True, delay_sec=0)
                    self._move_joint(
                        config.HOME_ANGLE, 'park home',
                        radius=config.MOTION_JOINT_RADIUS,
                    )
                else:
                    print('>> Arm still faulted (error {}, state {}) — skipping park. '
                          'NOTE: suction may still be holding a card. Clear the error in '
                          'UFACTORY Studio (see the joint report above), then re-enable.'.format(
                              self._arm.error_code, self._arm.state))
            except Exception as e:
                print('>> Park error: {}'.format(e))
            self.alive = False
            try:
                self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
                self._arm.release_state_changed_callback(self._state_changed_callback)
            except Exception:
                pass
            self._arm.disconnect()
            print('>> Arm disconnected. Done.')

    def _emit_result(self, idx, card, angle_heights, error_flag):
        """Record per-angle stats for one card.

        angle_heights: {angle_deg: [recorded heights mm above reader]}.
        """
        name = barcode = card_face = None
        if card:
            name, barcode = card[0], card[1]

        def stats(vals):
            if not vals:
                return ("", "", "", "")
            return (
                round(sum(vals) / len(vals), 2),
                round(min(vals), 2),
                round(max(vals), 2),
                len(vals),
            )

        # Side is not written — A/B is already in Card Code (A### / B###).
        row = {
            "kind": "read_height",
            "run": getattr(self, "cfg_run_id", 1),
            "card_num": idx,
            "card_title": name or "",
            "card_code": (barcode or "").upper(),
        }

        all_vals = []
        for angle in READ_ANGLES:
            vals = (angle_heights or {}).get(angle, []) or []
            avg, mn, mx, n = stats(vals)
            row["a{}_avg".format(angle)] = avg
            row["a{}_min".format(angle)] = mn
            row["a{}_max".format(angle)] = mx
            row["a{}_scans".format(angle)] = n
            all_vals += vals

        card_max = round(max(all_vals), 2) if all_vals else ""
        row["card_max"] = card_max

        # Partial / no-read annotations (only when there is no hard error).
        selected = list(getattr(self, "cfg_angles", READ_ANGLES))
        measured = [a for a in selected if (angle_heights or {}).get(a)]
        missing = [a for a in selected if not (angle_heights or {}).get(a)]
        partial = ""
        if not error_flag:
            if measured and missing:
                partial = "NO READ: " + ", ".join("{}°".format(a) for a in missing)
            elif not measured:
                partial = "NO READ (all angles)"

        row["error_skip"] = error_flag or partial
        self.results.append(row)
        if self._on_result:
            self._on_result(row)

    # =====================================================================
    # TAP-AND-GO TEST  (measures reader read-latency on a fast tap)
    # =====================================================================
    def _tapgo_reference_above_table(self):
        """TCP height above table for the reference point (card face at the
        calibrated reader top, plus an optional gap)."""
        reader_h = self._assumed_reader_height()
        if reader_h is None:
            return None
        return config.tcp_above_table_for_card_face(
            reader_h + TAPGO_STOP_ABOVE_FLOOR_MM)

    def _tapgo_approach_above_table(self):
        """TCP height above table for the tap start (card face high above reader
        to give runway to reach max speed)."""
        reader_h = self._assumed_reader_height()
        if reader_h is None:
            return None
        return config.tcp_above_table_for_card_face(
            reader_h + TAPGO_APPROACH_ABOVE_READER_MM)

    def _tapgo_measure_angle(self, angle, side_label=""):
        """Fast-tap this card at one angle `cfg_scans` times, timing each read.
        Returns (times_ms, error_flag); times_ms entries are float ms or None(miss)."""
        times = []
        if CardReadListener is None:
            print(">>   Tap-and-Go: read listener unavailable.")
            return times, "NO LISTENER"
        ref = self._tapgo_reference_above_table()
        approach = self._tapgo_approach_above_table()
        if ref is None or approach is None:
            print(">>   Tap-and-Go: reader height unknown — calibrate first.")
            return times, "NO CALIB"

        pose = self._staging_pose_for_angle(angle)
        if not self._move_to_staging(pose, 'tap-go staging {}°'.format(angle)):
            return times, "MOVE FAIL"

        read_ts = {"t": None}
        listener = CardReadListener(on_read=lambda _txt: read_ts.__setitem__("t", time.perf_counter()))
        listener.start()
        try:
            for tap in range(max(1, self.cfg_scans)):
                if not self.is_alive:
                    break
                self._progress(self._cur_cycle, self.cfg_cycles,
                               "{}° tap {}/{}{}".format(
                                   angle, tap + 1, self.cfg_scans,
                                   " (side {})".format(side_label) if side_label else ""))
                # rise to the (high) approach for runway to reach max speed
                if not self._move_to_height_above_table(
                        approach, "tap-go approach {}°".format(angle),
                        speed=config.MOTION_EXIT_TCP_SPEED, acc=config.MOTION_EXIT_TCP_ACC):
                    times.append(None)
                    break
                # between taps: hold high so the reader clears/resets before re-tap
                if tap > 0 and TAPGO_RESET_DWELL_S > 0:
                    time.sleep(TAPGO_RESET_DWELL_S)
                # fast plunge straight down to the reference point
                read_ts["t"] = None
                listener.reset()
                ok = self._move_to_height_above_table(
                    ref, "tap-go plunge {}°".format(angle),
                    speed=TAPGO_DESCENT_SPEED_MM_S, acc=TAPGO_DESCENT_ACC)
                t_arrive = time.perf_counter()
                if not ok:
                    times.append(None)
                    break
                got = listener.wait_for_read(TAPGO_READ_TIMEOUT_S)
                t_after = time.perf_counter()
                if got:
                    t_read = read_ts["t"] or t_after
                    ms = max(0.0, (t_read - t_arrive) * 1000.0)
                    times.append(round(ms, 1))
                    print(">>   {}° tap {}: read in {:.1f} ms".format(angle, tap + 1, ms))
                else:
                    times.append(None)
                    print(">>   {}° tap {}: NO READ within {:.1f}s".format(
                        angle, tap + 1, TAPGO_READ_TIMEOUT_S))
        finally:
            try:
                listener.stop()
            except Exception:
                pass
        # lift to a safe height before the wrist rotates to the next angle
        self._clear_reader_after_side()
        return times, ""

    def _emit_tapgo_result(self, idx, card, times, side_label, angle, error_flag):
        """Record one card/angle tap-and-go timing row (side_label is log-only)."""
        name = barcode = None
        if card:
            name, barcode = card[0], card[1]
        reads = [t for t in times if t is not None]
        misses = sum(1 for t in times if t is None)
        # Side omitted — barcode (A###/B###) identifies the face.
        row = {
            "kind": "tap_and_go",
            "run": getattr(self, "cfg_run_id", 1),
            "card_num": idx,
            "angle": "{}°".format(angle) if angle is not None else "",
            "card_title": name or "",
            "card_code": (barcode or "").upper(),
            "taps": len(times),
            "reads": len(reads),
            "misses": misses,
            "avg_ms": round(sum(reads) / len(reads), 1) if reads else "",
            "min_ms": round(min(reads), 1) if reads else "",
            "max_ms": round(max(reads), 1) if reads else "",
            "times_ms": ", ".join("{:.1f}".format(t) if t is not None else "miss" for t in times),
        }
        note = error_flag
        if not note and times and not reads:
            note = "NO READ (all taps)"
        row["error_skip"] = note or ""
        self.results.append(row)
        if self._on_result:
            self._on_result(row)

    def _tapgo_measure_side(self, idx, card_name, barcode, side_label):
        """Tap-and-Go every selected angle for one side; emit a row per angle."""
        for angle in self.cfg_angles:
            if not self.is_alive:
                break
            times, err = self._tapgo_measure_angle(angle, side_label)
            self._emit_tapgo_result(idx, (card_name, barcode), times, side_label, angle, err)

    def run_tap_and_go(self):
        """Tap-and-Go run: pick → scan/config → fast-tap timing → (flip) → drop."""
        try:
            print('>> Homing (fast)...')
            if not self._move_joint(config.HOME_ANGLE, 'home'):
                return
            print('>> Home reached. Tap-and-Go on {} card(s), {} tap(s) each.'.format(
                self.cfg_cycles, self.cfg_scans))

            for i in range(self.cfg_cycles):
                if not self.is_alive:
                    break
                self._cur_cycle = i + 1
                self._progress(i + 1, self.cfg_cycles, "Picking card")
                print('>> ─────────  Card {} of {} (Tap-and-Go)  ─────────'.format(
                    i + 1, self.cfg_cycles))
                t1 = time.monotonic()
                error_flag = ""

                # ── Pick (with retries) — identical to the read-height flow ──
                pick_z = None
                pick_radius = (config.MOTION_POST_RELEASE_JOINT_RADIUS
                               if i > 0 else config.MOTION_JOINT_RADIUS)
                for attempt in range(self.cfg_retries):
                    if not self.is_alive:
                        break
                    if not self._move_joint(PICK_ANGLE, 'move to pick', radius=pick_radius):
                        break
                    self._set_suction(True, wait=False, delay_sec=0)
                    pick_z = self.smart_pick()
                    if pick_z is not None:
                        break
                    print('>> Pick attempt {} failed.'.format(attempt + 1))
                    self._set_suction(False, wait=False, delay_sec=0)

                if pick_z is None:
                    print('>> Skipping card {} (pick failed).'.format(i + 1))
                    self._move_joint(config.HOME_ANGLE, 'home after pick fail',
                                     radius=config.MOTION_JOINT_RADIUS)
                    self._emit_tapgo_result(i + 1, None, [], "", None, "PICK FAIL")
                    continue

                time.sleep(config.POST_MOTION_PAUSE_S)
                code = self._arm.set_position(
                    z=config.POST_PICK_LIFT_MM, radius=config.MOTION_TCP_RADIUS,
                    speed=config.MOTION_TCP_SPEED, mvacc=config.MOTION_TCP_ACC,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift'):
                    break
                time.sleep(config.POST_MOTION_PAUSE_S)
                self._arm.set_state(0)

                # ── Barcode scan + reader config (same as read-height) ──
                self._progress(i + 1, self.cfg_cycles, "Scanning barcode")
                if not self._move_joint(config.BARCODE_SCAN_ANGLE, 'barcode pose',
                                        radius=config.MOTION_JOINT_RADIUS):
                    break
                card = self._scan_barcode_and_config()
                card_name = card.get('name') if card else None
                barcode = self._last_barcode

                if not card:
                    print('>> No barcode — skipping, releasing card.')
                    self._progress(i + 1, self.cfg_cycles, "Releasing card")
                    self._release_card()
                    self._emit_tapgo_result(i + 1, None, [], "", None, "BARCODE FAIL")
                    print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                    continue

                flip = bool(getattr(self, "cfg_flip", False))
                # ── Side A — tap every selected angle ──
                self._tapgo_measure_side(i + 1, card_name, barcode, "A" if flip else "")

                # ── Optional flip → Side B ──
                if flip and self.is_alive:
                    self._ensure_clearance_above_reader()
                    if self._flip_card():
                        # Re-scan the barcode for side B — the back may carry a
                        # different code, and the reader config must match the
                        # side now facing out.
                        nameB, barcodeB = self._goto_scan_barcode(i + 1)
                        if barcodeB is None:
                            print('>> Side B: no barcode after flip — recording BARCODE FAIL.')
                            self._emit_tapgo_result(
                                i + 1, (card_name, barcode), [], "B", None, "BARCODE FAIL")
                        else:
                            self._tapgo_measure_side(i + 1, nameB, barcodeB, "B")
                    else:
                        print('>> Flip failed — recording FLIP FAIL for side B.')
                        self._emit_tapgo_result(i + 1, (card_name, barcode), [], "B", None, "FLIP FAIL")

                # ── Drop and move on ──
                self._progress(i + 1, self.cfg_cycles, "Dropping card")
                self._exit_reader_and_release()
                print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))

        except Exception as e:
            print('>> MainException (tap-and-go): {}'.format(e))
        finally:
            try:
                if self._stop_event.is_set():
                    print('>> Abort — parking arm safely...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                    except Exception:
                        pass
                elif self._arm.error_code != 0 or (self._arm.state or 0) >= 4:
                    self.diagnose_fault('end of tap-and-go run')
                    print('>> Attempting one recovery so the arm can park...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                        time.sleep(0.3)
                    except Exception:
                        pass
                if self._arm.error_code == 0 and (self._arm.state or 0) < 4:
                    self._set_suction(False, wait=True, delay_sec=0)
                    self._move_joint(config.HOME_ANGLE, 'park home',
                                     radius=config.MOTION_JOINT_RADIUS)
                else:
                    print('>> Arm still faulted (error {}, state {}) — skipping park. '
                          'NOTE: suction may still be holding a card. Clear the error in '
                          'UFACTORY Studio (see the joint report above), then re-enable.'.format(
                              self._arm.error_code, self._arm.state))
            except Exception as e:
                print('>> Park error: {}'.format(e))
            self.alive = False

    # =====================================================================
    # COMBINED TEST  (Read Height + Tap-and-Go on the same card, per side)
    # =====================================================================
    def _measure_side_combined(self, cycle, side_label):
        """For the side currently facing out: scan the barcode, then run BOTH
        the read-height measurement and the tap-and-go measurement across every
        selected angle. Emits a read-height row and one tap-and-go row per angle.

        Returns True if the side was scanned and measured, False on a barcode/
        move failure (in which case a BARCODE FAIL row is recorded for each
        test and the caller drops the card).
        """
        name, barcode = self._goto_scan_barcode(cycle)
        if barcode is None:
            print('>> No barcode — skipping this side (both tests).')
            self._emit_result(cycle, None, {}, "BARCODE FAIL")
            self._emit_tapgo_result(cycle, None, [], side_label, None, "BARCODE FAIL")
            return False

        face = {"A": "front", "B": "back"}.get(side_label, "single side")
        angle_txt = ", ".join("{}°".format(a) for a in self.cfg_angles)

        # ── Phase 1: Read Height (gentle descents), one row for the side ──
        print('>> [Read Height] {} ({}) — {} angle(s)'.format(
            face, side_label or "n/a", angle_txt))
        angle_heights = {}
        for angle in self.cfg_angles:
            if not self.is_alive:
                break
            pose = self._staging_pose_for_angle(angle)
            heights = self._measure_orientation(
                "{}°".format(angle), pose, self.cfg_scans,
                clear_after=True, skip_fast_zone=False,
            )
            angle_heights[angle] = heights
        self._emit_result(cycle, (name, barcode, side_label), angle_heights, "")

        # ── Phase 2: Tap-and-Go (fast plunges), one row per angle ──
        print('>> [Tap and Go] {} ({}) — {} angle(s)'.format(
            face, side_label or "n/a", angle_txt))
        for angle in self.cfg_angles:
            if not self.is_alive:
                break
            times, err = self._tapgo_measure_angle(angle, side_label)
            self._emit_tapgo_result(cycle, (name, barcode), times, side_label, angle, err)
        return True

    def run_combined(self):
        """Combined run: pick → (per side) scan + Read Height + Tap-and-Go →
        optional flip → drop. Re-scans the barcode for each side."""
        try:
            print('>> Homing (fast)...')
            if not self._move_joint(config.HOME_ANGLE, 'home'):
                return
            print('>> Home reached. Combined test (Read Height + Tap-and-Go) on '
                  '{} card(s).'.format(self.cfg_cycles))
            print('>> Angles this run: {}'.format(
                ", ".join("{}°".format(a) for a in self.cfg_angles)))

            for i in range(self.cfg_cycles):
                if not self.is_alive:
                    break
                self._cur_cycle = i + 1
                self._progress(i + 1, self.cfg_cycles, "Picking card")
                print('>> ────────  Card {} of {} (Read Height + Tap-and-Go)  ────────'.format(
                    i + 1, self.cfg_cycles))
                t1 = time.monotonic()

                # ── Pick (with retries) — identical to the other flows ──
                pick_z = None
                pick_radius = (config.MOTION_POST_RELEASE_JOINT_RADIUS
                               if i > 0 else config.MOTION_JOINT_RADIUS)
                for attempt in range(self.cfg_retries):
                    if not self.is_alive:
                        break
                    if not self._move_joint(PICK_ANGLE, 'move to pick', radius=pick_radius):
                        break
                    self._set_suction(True, wait=False, delay_sec=0)
                    pick_z = self.smart_pick()
                    if pick_z is not None:
                        break
                    print('>> Pick attempt {} failed.'.format(attempt + 1))
                    self._set_suction(False, wait=False, delay_sec=0)

                if pick_z is None:
                    print('>> Skipping card {} (pick failed).'.format(i + 1))
                    self._move_joint(config.HOME_ANGLE, 'home after pick fail',
                                     radius=config.MOTION_JOINT_RADIUS)
                    self._emit_result(i + 1, None, {}, "PICK FAIL")
                    self._emit_tapgo_result(i + 1, None, [], "", None, "PICK FAIL")
                    continue

                time.sleep(config.POST_MOTION_PAUSE_S)
                code = self._arm.set_position(
                    z=config.POST_PICK_LIFT_MM, radius=config.MOTION_TCP_RADIUS,
                    speed=config.MOTION_TCP_SPEED, mvacc=config.MOTION_TCP_ACC,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift'):
                    break
                time.sleep(config.POST_MOTION_PAUSE_S)
                self._arm.set_state(0)

                flip = bool(getattr(self, "cfg_flip", False))

                # ── Side A ──
                okA = self._measure_side_combined(i + 1, "A" if flip else "")
                if not okA:
                    self._progress(i + 1, self.cfg_cycles, "Releasing card")
                    self._release_card()
                    print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                    continue

                # ── Optional flip → Side B ──
                if flip and self.is_alive:
                    self._progress(i + 1, self.cfg_cycles, "Clearing reader")
                    if not self._ensure_clearance_above_reader():
                        break
                    self._progress(i + 1, self.cfg_cycles, "Flipping card")
                    if not self._flip_card():
                        print('>> Flip failed — recording FLIP FAIL for side B.')
                        self._emit_result(i + 1, None, {}, "FLIP FAIL")
                        self._emit_tapgo_result(i + 1, None, [], "B", None, "FLIP FAIL")
                        self._release_card()
                        print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                        continue
                    self._measure_side_combined(i + 1, "B")

                # ── Drop and move on ──
                self._progress(i + 1, self.cfg_cycles, "Dropping card")
                self._exit_reader_and_release()
                print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))

        except Exception as e:
            print('>> MainException (combined): {}'.format(e))
        finally:
            try:
                if self._stop_event.is_set():
                    print('>> Abort — parking arm safely...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                    except Exception:
                        pass
                elif self._arm.error_code != 0 or (self._arm.state or 0) >= 4:
                    self.diagnose_fault('end of combined run')
                    print('>> Attempting one recovery so the arm can park...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                        time.sleep(0.3)
                    except Exception:
                        pass
                if self._arm.error_code == 0 and (self._arm.state or 0) < 4:
                    self._set_suction(False, wait=True, delay_sec=0)
                    self._move_joint(config.HOME_ANGLE, 'park home',
                                     radius=config.MOTION_JOINT_RADIUS)
                else:
                    print('>> Arm still faulted (error {}, state {}) — skipping park. '
                          'NOTE: suction may still be holding a card. Clear the error in '
                          'UFACTORY Studio (see the joint report above), then re-enable.'.format(
                              self._arm.error_code, self._arm.state))
            except Exception as e:
                print('>> Park error: {}'.format(e))
            self.alive = False
            try:
                self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
                self._arm.release_state_changed_callback(self._state_changed_callback)
            except Exception:
                pass
            self._arm.disconnect()
            print('>> Arm disconnected. Done.')

    # =====================================================================
    # DEADZONE TEST  (continuous read + slow ascent from reader top)
    # =====================================================================
    def _deadzone_floor_above_table(self):
        """TCP height above table with card face at the calibrated reader top."""
        reader_h = self._assumed_reader_height()
        if reader_h is None:
            return None
        return config.tcp_above_table_for_card_face(reader_h)

    def _deadzone_height_above_reader(self):
        """Current card-face height above reader top (mm), or None."""
        h_table = self._height_above_table()
        return self._read_height_above_reader(h_table)

    def _deadzone_listen_step(self, listener, dwell_s):
        """True if a credential wedge arrives within ``dwell_s``."""
        if listener is None:
            return False
        listener.reset()
        if DEADZONE_SETTLE_S > 0:
            time.sleep(DEADZONE_SETTLE_S)
        deadline = time.monotonic() + dwell_s
        while time.monotonic() < deadline and self.is_alive:
            if listener.read_detected():
                return True
            time.sleep(0.02)
        return listener.read_detected()

    def _deadzone_restore_reader(self, card):
        """Reload the card's normal (non-continuous) HWG after a deadzone scan."""
        if not card:
            return
        try:
            configure_reader_for_card(card, log_fn=print, continuous=False)
        except Exception as e:
            print(">> Deadzone: restore reader config failed ({})".format(e))

    def _deadzone_measure_angle(self, angle, side_label=""):
        """Slow ascent from reader top; detect mid-field read gaps (deadzones).

        The arm ALWAYS performs the slow stepped ascent — it never aborts just
        because the card is silent at the floor (readers commonly need a small
        air gap and won't read pressed flat). It seeks the first read on the
        way up, then watches for a mid-field gap.

        Deadzone vs end-of-field (plain language):
          • Seeking — no read yet; keep climbing until the first read (entry).
          • Deadzone — reads stop for ≥ GAP_CONFIRM_STEPS, then resume before
            EOF_STEPS. The gap is inside the field; height = first loss (mm).
          • Exit / end-of-field — reads stop and stay stopped for EOF_STEPS, OR
            the card hits the max height / time cap. That final silence is NOT
            logged as a deadzone (unless a gap-and-resume already happened).

        Returns (result_dict, error_flag). result_dict keys:
          deadzones (list mm), entry_height_mm, exit_height_mm, steps.
        """
        empty = {"deadzones": [], "entry_height_mm": "",
                 "exit_height_mm": "", "steps": 0}
        if CardReadListener is None:
            print(">>   Deadzone: read listener unavailable.")
            return empty, "NO LISTENER"
        floor = self._deadzone_floor_above_table()
        if floor is None:
            print(">>   Deadzone: reader height unknown — calibrate first.")
            return empty, "NO CALIB"

        step = float(getattr(self, "cfg_final_step_mm", 1.0) or 1.0)
        speed = float(getattr(self, "cfg_descent_speed", 18.0) or 18.0)
        pose = self._staging_pose_for_angle(angle)
        if not self._move_to_staging(pose, "deadzone staging {}°".format(angle)):
            return empty, "MOVE FAIL"

        # Approach from above, then settle onto the MARK floor (card touching).
        if not self._move_to_approach_for_orientation("{}°".format(angle)):
            return empty, "MOVE FAIL"
        print(
            ">>   Deadzone {}° — descend to reader top, then ascend "
            "{:.1f}mm steps @ {:.1f} mm/s (preset {})".format(
                angle, step, speed, getattr(self, "cfg_preset", "?"),
            )
        )
        if not self._move_to_height_above_table(
                floor, "deadzone floor {}°".format(angle),
                speed=min(speed * 2.0, 40.0),
                acc=config.READ_HEIGHT_DESCENT_ACC):
            return empty, "MOVE FAIL"

        listener = CardReadListener(tk_root=getattr(self, "tk_root", None))
        listener.start()
        deadzones = []
        exit_h = None
        entry_h = None          # first height where the card actually read
        steps = 0
        # SEEKING until the first continuous read. We DO NOT abort if the card
        # is silent at the floor — many readers need a small air gap and won't
        # read while the card is pressed flat against them. Instead we keep
        # ascending slowly and look for the first read on the way up.
        state = "SEEKING"
        miss_streak = 0
        loss_height = None
        ever_read = False
        t0 = time.monotonic()
        err = ""

        try:
            # One listen at the floor to seed the state — but never fatal.
            got = self._deadzone_listen_step(
                listener, DEADZONE_FLOOR_READ_TIMEOUT_S)
            if got:
                state = "READING"
                ever_read = True
                entry_h = self._deadzone_height_above_reader()
                print(">>   Deadzone {}°: reading at floor{} — ascending".format(
                    angle,
                    "" if entry_h is None else " ({:.2f}mm above reader)".format(entry_h),
                ))
            else:
                print(
                    ">>   Deadzone {}°: no read at floor — ascending slowly to "
                    "seek the first read.".format(angle)
                )

            # Always perform the slow stepped ascent, regardless of the floor
            # read. SEEKING climbs until the first read; READING/GAP then map
            # any mid-field deadzone.
            while self.is_alive and not err:
                if (time.monotonic() - t0) >= DEADZONE_MAX_TRAVEL_S:
                    exit_h = self._deadzone_height_above_reader()
                    print(">>   Deadzone {}°: max travel time — exit at {:.2f}mm".format(
                        angle, exit_h if exit_h is not None else -1))
                    break

                cur = self._deadzone_height_above_reader()
                if cur is not None and cur >= DEADZONE_MAX_ABOVE_READER_MM:
                    exit_h = cur
                    print(">>   Deadzone {}°: max height {:.1f}mm — exit".format(
                        angle, DEADZONE_MAX_ABOVE_READER_MM))
                    break

                # One ascent step (same step/speed as read-height final preset).
                code = self._arm.set_position(
                    z=step, radius=0,
                    speed=speed, mvacc=config.READ_HEIGHT_DESCENT_ACC,
                    relative=True, wait=True,
                )
                if not self._check_code(code, "deadzone ascent step"):
                    err = "MOVE FAIL"
                    break
                steps += 1
                cur = self._deadzone_height_above_reader()
                got = self._deadzone_listen_step(listener, DEADZONE_DWELL_S)

                if got:
                    if not ever_read:
                        ever_read = True
                        entry_h = cur
                        print(">>   Deadzone {}°: first read at {:.2f}mm above "
                              "reader".format(
                                  angle, entry_h if entry_h is not None else -1))
                    if state == "GAP" and loss_height is not None:
                        # Resume after a confirmed gap → this IS a deadzone.
                        dz = round(loss_height, 2)
                        deadzones.append(dz)
                        print(
                            ">>   Deadzone {}°: GAP→READ — deadzone at "
                            "{:.2f}mm above reader".format(angle, dz)
                        )
                    state = "READING"
                    miss_streak = 0
                    loss_height = None
                    continue

                # No read this step.
                miss_streak += 1
                if state == "SEEKING":
                    # Haven't entered the readable field yet — keep climbing.
                    continue
                if state == "READING":
                    if miss_streak == 1:
                        loss_height = cur  # first loss height (mm above reader)
                    if miss_streak >= DEADZONE_GAP_CONFIRM_STEPS:
                        state = "GAP"
                        print(
                            ">>   Deadzone {}°: read lost near {:.2f}mm "
                            "(gap pending)".format(
                                angle, loss_height if loss_height is not None else -1)
                        )
                elif state == "GAP":
                    if miss_streak >= DEADZONE_EOF_STEPS:
                        # Sustained silence → left the field (NOT a deadzone).
                        exit_h = loss_height if loss_height is not None else cur
                        print(
                            ">>   Deadzone {}°: end of field at {:.2f}mm "
                            "(no resume — not a deadzone)".format(
                                angle, exit_h if exit_h is not None else -1)
                        )
                        break

            if exit_h is None and not err:
                exit_h = self._deadzone_height_above_reader()
            if not ever_read and not err:
                # Climbed the full range and the card never read at any height.
                print(">>   Deadzone {}°: no read at any height (0–{:.0f}mm).".format(
                    angle, DEADZONE_MAX_ABOVE_READER_MM))
                err = "NO READ"
        finally:
            try:
                listener.stop()
            except Exception:
                pass

        self._clear_reader_after_side()
        result = {
            "deadzones": deadzones,
            "entry_height_mm": "" if entry_h is None else round(entry_h, 2),
            "exit_height_mm": "" if exit_h is None else round(exit_h, 2),
            "steps": steps,
        }
        return result, err

    def _emit_deadzone_result(self, idx, card, angle, result, error_flag):
        """Record one card/angle deadzone row for CSV / live UI."""
        name = barcode = None
        if card:
            name, barcode = card[0], card[1]
        deadzones = list((result or {}).get("deadzones") or [])
        found = "Y" if deadzones else "N"
        heights_txt = (
            ", ".join("{:.2f}".format(h) for h in deadzones) if deadzones else ""
        )
        row = {
            "kind": "deadzone",
            "run": getattr(self, "cfg_run_id", 1),
            "card_num": idx,
            "angle": "{}°".format(angle) if angle is not None else "",
            "card_title": name or "",
            "card_code": (barcode or "").upper(),
            "deadzone_found": found,
            "deadzone_heights_mm": heights_txt,
            "exit_height_mm": (result or {}).get("exit_height_mm", ""),
            "error_skip": error_flag or "",
        }
        self.results.append(row)
        if self._on_result:
            self._on_result(row)

    def _deadzone_measure_side(self, idx, card_name, barcode, side_label):
        """Deadzone-scan every selected angle for the face currently out."""
        card = getattr(self, "_current_card", None)
        for angle in self.cfg_angles:
            if not self.is_alive:
                break
            self._progress(
                self._cur_cycle, self.cfg_cycles,
                "Deadzone {}°{}".format(
                    angle,
                    " (side {})".format(side_label) if side_label else "",
                ),
            )
            result, err = self._deadzone_measure_angle(angle, side_label)
            self._emit_deadzone_result(
                idx, (card_name, barcode), angle, result, err,
            )
        # Restore normal (non-continuous) lockout after the side is done.
        self._deadzone_restore_reader(card)

    def run_deadzone(self):
        """Deadzone run: pick → scan/config continuous → touch reader → slow ascent."""
        try:
            print('>> Homing (fast)...')
            if not self._move_joint(config.HOME_ANGLE, 'home'):
                return
            print(
                '>> Home reached. Deadzone on {} card(s) — continuous read, '
                'ascend from reader top (preset {}, {:.1f}mm @ {:.1f} mm/s).'.format(
                    self.cfg_cycles,
                    getattr(self, "cfg_preset", "?"),
                    float(getattr(self, "cfg_final_step_mm", 1.0) or 1.0),
                    float(getattr(self, "cfg_descent_speed", 18.0) or 18.0),
                )
            )
            print(
                '>> Deadzone rule: gap+resume = deadzone at first loss; '
                'sustained no-read ({} steps) / max {:.0f}mm / {:.0f}s = exit '
                '(not a deadzone).'.format(
                    DEADZONE_EOF_STEPS, DEADZONE_MAX_ABOVE_READER_MM,
                    DEADZONE_MAX_TRAVEL_S,
                )
            )

            for i in range(self.cfg_cycles):
                if not self.is_alive:
                    break
                self._cur_cycle = i + 1
                self._progress(i + 1, self.cfg_cycles, "Picking card")
                print('>> ─────────  Card {} of {} (Deadzone)  ─────────'.format(
                    i + 1, self.cfg_cycles))
                t1 = time.monotonic()

                pick_z = None
                pick_radius = (config.MOTION_POST_RELEASE_JOINT_RADIUS
                               if i > 0 else config.MOTION_JOINT_RADIUS)
                for attempt in range(self.cfg_retries):
                    if not self.is_alive:
                        break
                    if not self._move_joint(PICK_ANGLE, 'move to pick', radius=pick_radius):
                        break
                    self._set_suction(True, wait=False, delay_sec=0)
                    pick_z = self.smart_pick()
                    if pick_z is not None:
                        break
                    print('>> Pick attempt {} failed.'.format(attempt + 1))
                    self._set_suction(False, wait=False, delay_sec=0)

                if pick_z is None:
                    print('>> Skipping card {} (pick failed).'.format(i + 1))
                    self._move_joint(config.HOME_ANGLE, 'home after pick fail',
                                     radius=config.MOTION_JOINT_RADIUS)
                    self._emit_deadzone_result(i + 1, None, None, {}, "PICK FAIL")
                    continue

                time.sleep(config.POST_MOTION_PAUSE_S)
                code = self._arm.set_position(
                    z=config.POST_PICK_LIFT_MM, radius=config.MOTION_TCP_RADIUS,
                    speed=config.MOTION_TCP_SPEED, mvacc=config.MOTION_TCP_ACC,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift'):
                    break
                time.sleep(config.POST_MOTION_PAUSE_S)
                self._arm.set_state(0)

                # Barcode + continuous HWG (short lockout for repeated wedge).
                name, barcode = self._goto_scan_barcode(i + 1, continuous=True)
                if barcode is None:
                    print('>> No barcode — skipping, releasing card.')
                    self._progress(i + 1, self.cfg_cycles, "Releasing card")
                    self._release_card()
                    self._emit_deadzone_result(i + 1, None, None, {}, "BARCODE FAIL")
                    print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))
                    continue

                flip = bool(getattr(self, "cfg_flip", False))
                self._deadzone_measure_side(
                    i + 1, name, barcode, "A" if flip else "")

                if flip and self.is_alive:
                    self._ensure_clearance_above_reader()
                    if self._flip_card():
                        nameB, barcodeB = self._goto_scan_barcode(
                            i + 1, continuous=True)
                        if barcodeB is None:
                            print('>> Side B: no barcode after flip.')
                            self._emit_deadzone_result(
                                i + 1, (name, barcode), None, {}, "BARCODE FAIL")
                        else:
                            self._deadzone_measure_side(i + 1, nameB, barcodeB, "B")
                    else:
                        print('>> Flip failed — recording FLIP FAIL for side B.')
                        self._emit_deadzone_result(
                            i + 1, (name, barcode), None, {}, "FLIP FAIL")

                self._progress(i + 1, self.cfg_cycles, "Dropping card")
                self._exit_reader_and_release()
                print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))

        except Exception as e:
            print('>> MainException (deadzone): {}'.format(e))
        finally:
            try:
                if self._stop_event.is_set():
                    print('>> Abort — parking arm safely...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                    except Exception:
                        pass
                elif self._arm.error_code != 0 or (self._arm.state or 0) >= 4:
                    self.diagnose_fault('end of deadzone run')
                    print('>> Attempting one recovery so the arm can park...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                        time.sleep(0.3)
                    except Exception:
                        pass
                if self._arm.error_code == 0 and (self._arm.state or 0) < 4:
                    self._set_suction(False, wait=True, delay_sec=0)
                    self._move_joint(config.HOME_ANGLE, 'park home',
                                     radius=config.MOTION_JOINT_RADIUS)
                else:
                    print('>> Arm still faulted (error {}, state {}) — skipping park. '
                          'NOTE: suction may still be holding a card. Clear the error in '
                          'UFACTORY Studio (see the joint report above), then re-enable.'.format(
                              self._arm.error_code, self._arm.state))
            except Exception as e:
                print('>> Park error: {}'.format(e))
            self.alive = False
