# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""GUI constants, brand theme, joint-limit helpers, and reader-library loaders.

Role
    Shared tunables and poses for the Tk read-height app. Imported by
    ``gui_robot``, ``app``, and ``widgets``. No hardware I/O.

Inputs / outputs
    Reads ``config`` defaults. Optional legacy ``files/card_readers.json`` is
    loaded if present (MARK READER TOP is the source of truth for height).
    Exports brand colors, joint-limit helpers
    (``nearest_j6_in_range``, ``joint_limit_issues``), CSV headers, and
    descent/Tap-and-Go pose constants.

Runtime behavior must stay identical to the pre-split monolith — change
values only with explicit operator approval.
"""

import os
import sys
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

import config
from barcode.scanner import is_bad_reference_height

# Telemetry UDP target for the optional ROS2 bridge (ros2_bridge.py).
# Override without editing code via environment variables, e.g.:
#   set ROS_BRIDGE_HOST=127.0.0.1   (WSL2 mirrored-networking mode)
#   set ROS_BRIDGE_HOST=172.24.x.x  (WSL2 NAT mode: the distro's IP)
TELEMETRY_UDP_HOST = os.environ.get("ROS_BRIDGE_HOST", "127.0.0.1")
TELEMETRY_UDP_PORT = int(os.environ.get("ROS_BRIDGE_PORT", "9870"))

DEFAULT_IP = config.ROBOT_IP
TABLE_Z = config.TABLE_Z_MM

# Read angles measured per card. 0° is the original "inline" orientation; each
# subsequent angle is the card rotated about its face normal (wrist / J6).
READ_ANGLES = (0, 90, 180, 270)

# Official Lite 6 joint limits (deg). Used to diagnose C23 "joint angle exceeds
# limit" faults by NAME instead of leaving the operator guessing in Studio.
LITE6_JOINT_LIMITS = [
    (-360.0, 360.0),   # J1
    (-150.0, 150.0),   # J2
    (-3.5,   300.0),   # J3
    (-360.0, 360.0),   # J4
    (-124.0, 124.0),   # J5
    (-360.0, 360.0),   # J6
]
JOINT_LIMIT_MARGIN_DEG = 1.5   # flag joints this close to a limit


def nearest_j6_in_range(target_j6, ref_j6, margin=None):
    """Return an angle physically identical to `target_j6` (i.e. target_j6 plus
    an integer number of full turns) that is as close as possible to `ref_j6`
    while staying strictly inside J6's ±limit.

    Because a full 360° turn of the wrist is physically identical, shifting the
    commanded value by ±360° never changes the card's real orientation — it only
    keeps the *number* the controller sees inside the legal range and picks the
    shortest wind. This is what prevents the C23 "J6 exceeds limit" fault when
    returning the card to the drop bin: without it a Cartesian traverse can
    resolve the wrist onto a revolution below -360°.
    """
    lo, hi = LITE6_JOINT_LIMITS[5]
    m = JOINT_LIMIT_MARGIN_DEG if margin is None else margin
    lo_safe, hi_safe = lo + m, hi - m
    # All candidate revolutions of target_j6 (they are all physically identical).
    candidates = [target_j6 + 360.0 * k for k in range(-3, 4)]
    in_range = [c for c in candidates if lo_safe <= c <= hi_safe]
    pool = in_range if in_range else candidates
    # Prefer the one closest to where the wrist already is (shortest, safe wind).
    return min(pool, key=lambda c: abs(c - ref_j6))


def joint_limit_issues(angles_deg):
    """Return human-readable issues for any joint at/past its limit."""
    issues = []
    for i, a in enumerate(list(angles_deg)[:6]):
        lo, hi = LITE6_JOINT_LIMITS[i]
        if a < lo or a > hi:
            issues.append("J{} = {:.1f}° is PAST its limit ({:.1f}..{:.1f}°)".format(
                i + 1, a, lo, hi))
        elif a < lo + JOINT_LIMIT_MARGIN_DEG or a > hi - JOINT_LIMIT_MARGIN_DEG:
            issues.append("J{} = {:.1f}° is AT its limit ({:.1f}..{:.1f}°)".format(
                i + 1, a, lo, hi))
    return issues

# Default reader shown when the GUI opens.
DEFAULT_READER_MODEL = "HIP2_SP"

# Step size for the SLOWEST (recorded) tap. The UFactory Lite 6 manual specs
# joint repeatability at ±0.2mm; consumer datasheets advertise ±0.5mm. The arm
# won't achieve absolute 0.1mm accuracy — but that isn't what this step does.
# We're sampling the descent position so that when the reader fires, the arm's
# reported Z is as close as possible to the true read height. 0.1mm is the
# smallest step that meaningfully differs from the arm's motion resolution;
# anything smaller wastes time without improving accuracy. Overrides both
# self.cfg_descent_step and config.READER_FINAL_DESCENT_STEP_MM for the
# recorded tap.
FINAL_TAP_STEP_MM = 0.1

# ── Test-speed presets ─────────────────────────────────────────────────────
# Zone taps are hard-coded to 3 (fast → middle → slow-recorded). Only the
# LAST (recorded) tap is used for the read height, so the preset picks how
# much accuracy vs speed you want on that final tap. Tap 1 (middle) scales
# alongside so the progression stays smooth from the always-aggressive coarse
# tap 0 down to the recorded tap 2.
#
# Accuracy is set mainly by the final step size (the arm stops and listens
# after each step, so the read is localized to within one step). Speed rises
# with step size since bigger steps don't need fine motion.
#   Slowest — 0.1mm  final step; tightest numbers (Lite 6 repeatability).
#   Slow    — 0.5mm
#   Medium  — 1.0mm  (default)
#   Fast    — 2.0mm
#   Fastest — 3.0mm  final step; quickest, least precise.
DESCENT_PRESETS = {
    "Slowest": {"final_step_mm": 0.1, "final_speed_mm_s": 5.0,
                "mid_step_mm":   1.0, "mid_speed_mm_s":   30.0},
    "Slow":    {"final_step_mm": 0.5, "final_speed_mm_s": 10.0,
                "mid_step_mm":   1.5, "mid_speed_mm_s":   40.0},
    "Medium":  {"final_step_mm": 1.0, "final_speed_mm_s": 18.0,
                "mid_step_mm":   2.5, "mid_speed_mm_s":   55.0},
    "Fast":    {"final_step_mm": 2.0, "final_speed_mm_s": 30.0,
                "mid_step_mm":   4.0, "mid_speed_mm_s":   75.0},
    "Fastest": {"final_step_mm": 3.0, "final_speed_mm_s": 45.0,
                "mid_step_mm":   5.0, "mid_speed_mm_s":   90.0},
}
DEFAULT_PRESET = "Medium"

# Fixed test parameters (previously exposed in the GUI). Zone taps controls
# the descent stages; remeasures = 1 means "record the slowest tap once, per
# angle" — repeats would just repeat the slowest descent at the same spot.
FIXED_ZONE_TAPS = 3
FIXED_REMEASURES = 1

# Between zone-in taps, rise this far above the last read point before the next
# (slower) descent. The config default (READER_REFINE_CLEARANCE_MM = 18mm) was
# too small — the card stayed inside the read zone, so the slow recorded tap
# began already reading and logged a too-high height. Add clearance so the card
# fully exits the read zone and re-enters cleanly on a fresh descent.
ZONE_REFINE_EXTRA_LIFT_MM = 22.0
REFINE_CLEARANCE_MM = config.READER_REFINE_CLEARANCE_MM + ZONE_REFINE_EXTRA_LIFT_MM

# Parameters for the FASTEST (first) tap of the zone-in. This tap only exists
# to find the general read zone — its height is NOT recorded — so we can be
# aggressive without any accuracy cost. Any overshoot is corrected by the
# refine lift and the subsequent (slower) taps. Values chosen for a good
# time/safety balance on the Lite 6 (max TCP 500 mm/s):
#   • 100 mm/s   — 20% of arm max; plenty of headroom
#   • 6 mm step  — coarse zone-finding; refine lift re-zones for the next tap
#   • 40 ms dwell — longer than typical reader fire latency (~20–30 ms), so
#                   the read event is caught reliably between steps
# Overrides config.READER_FAST_DESCENT_SPEED_MM_S / STEP_MM / DWELL_S for the
# FAST first tap only. The floor is still enforced by _max_drop_to_floor and
# config.READER_DESCENT_MIN_HEIGHT_MM, so the card cannot crush the reader.
FAST_TAP_SPEED_MM_S = 100.0
FAST_TAP_STEP_MM = 6.0
FAST_TAP_DWELL_S = 0.04

# ── Card drop-off ──────────────────────────────────────────────────────────
# Joint pose where the card is released. Hand-jogged in UFACTORY Studio to a
# verified-safe pose over the drop bin (read straight off the joint readout).
# J6 = 36.6° sits near the centre of the wrist range, so the move from any read
# angle to the drop never approaches the ±360° limit (no C23). The drop uses
# this pose exactly — all six joints, including the wrist.
DROP_ANGLE = [-54.2, 66.8, 108.9, 0.5, 41.9, 36.1]
# Clear at least this far above the drop point before descending to it, so the
# arm clears everything on the way over.
DROP_CLEARANCE_MM = 40.0
# OPTIONAL pure-joint hover pose ~DROP_CLEARANCE_MM above DROP_ANGLE. RECOMMENDED:
# in UFACTORY Studio go to DROP_ANGLE, jog straight up ~40mm, copy the six joint
# angles, and paste them here. When set, the hover is a pure joint move (safest —
# no Cartesian IK). When left None, the hover is computed from DROP_ANGLE via
# forward kinematics (a Cartesian move — works, but verify on a dry run).
DROP_HOVER_ANGLE = None

# ── Reader-descent staging pose (0°) ────────────────────────────────────────
# Hand-jogged in UFACTORY Studio so the card sits centred, 100% on top of the
# reader, at the 0° read orientation. This is the literal 0° staging pose; the
# 90°/180°/270° poses are the same joint pose with only the wrist (J6) rotated
# (+J6 = +physical° on this rig). Overrides config.READER_DESCENT_STAGING_INLINE.
# Per-card baseline heights and all descent/zone-in logic are unaffected — only
# the starting orientation/position above the reader changes.
READER_STAGING_0_ANGLE = [0.5, 13.6, 36.9, 0.1, 20.0, -270.8]

# Card face parallel to a flat reader on the table (UFactory tool-down RPY:
# roll = ±180°, pitch = 0°). Applied after every reader staging joint move so a
# tilted taught pose cannot leave the card non-parallel during read-height.
READER_PARALLEL_ROLL_DEG = 180.0
READER_PARALLEL_PITCH_DEG = 0.0

# ── Card pick pose (from the full stack) ────────────────────────────────────
# Joint pose the arm moves to before descending into the stack for smart_pick().
# Hand-jogged; overrides config.PICK_ANGLE. (This is the stack pick, NOT the
# flip re-grab pose — that's FLIP_REGRAB_POSE.)
PICK_ANGLE = [-43.1, 47.0, 72.2, 180.0, -23.5, -133.9]

# ── Flip station (optional "test both sides") ───────────────────────────────
# When enabled, after side A is measured the card is placed in the flip fixture,
# released, and re-picked flipped so side B faces the reader — then it re-scans
# the barcode and tests side B before dropping. A faithful translation of the
# Studio flip program: four joint moves down into the fixture, release, retract
# straight up, reposition, suction on, descend onto the card, settle, lift.
# All joint moves + pure-vertical relative Z (the "safe" Cartesian kind).
# Speeds are a touch conservative for the first hardware runs — raise once
# validated on the real cell.
FLIP_SET_DOWN_PATH = [
    [7.4, 25.7, 39.9, -262.7, 90.7, 25.5],
    [24.5, 38.1, 51.5, -245.1, 86.7, 24.0],
    [23.7, 51.3, 52.3, -244.6, 97.1, 7.1],
    [23.1, 67.1, 63.3, -250.6, 120.0, 3.3],
]
FLIP_RETRACT_LIFT_MM = 135.0    # straight up after releasing into the fixture
FLIP_REGRAB_POSE = [49.5, 39.8, 82.1, -180.6, -41.3, -42.0]
FLIP_GRAB_STROKE_MM = 54.0      # down onto the flipped card, then back up
# Non-critical moves (set-down path, re-grab approach, retract lift) run fast;
# the actual grab stroke (descend onto the card + lift it out) stays controlled.
FLIP_JOINT_SPEED = 180.0        # deg/s — set-down + approach (full transit speed)
FLIP_JOINT_ACC = 1100.0
FLIP_TCP_SPEED = 350.0          # mm/s — non-contact retract lift (fast)
FLIP_TCP_ACC = 3000.0
FLIP_GRAB_TCP_SPEED = 200.0     # mm/s — descend onto card + lift with card (controlled)
FLIP_GRAB_TCP_ACC = 2000.0
FLIP_RELEASE_DWELL_S = 0.2      # brief settle after releasing into the fixture
FLIP_SETTLE_S = 0.5             # vacuum-seal settle after re-gripping

# ── Reader calibration (manual arrow-key jog) ───────────────────────────────
# Step size per key press / button click (mm for translation, degrees for the
# wrist). Switchable live.
CALIB_STEP_PRESETS = {"Coarse": 10.0, "Medium": 1.0, "Fine": 0.1}
CALIB_DEFAULT_STEP = "Medium"
CALIB_JOG_TCP_SPEED = 60.0        # mm/s — gentle Cartesian jog
CALIB_JOG_TCP_ACC = 500.0
# When MARK READER TOP is pressed, lift straight up this far to capture the
# staging pose (well clear of the reader). Approach logic re-sets Z anyway.
CALIB_STAGING_LIFT_MM = 150.0
# Hard floor: never let the TCP go below this many mm above the table, so a jog
# can't drive the tool into the table. (You'll touch the reader top well before
# this on any real reader.)
CALIB_MIN_ABOVE_TABLE_MM = 2.0

# ── Results CSV layout ─────────────────────────────────────────────────────
# One row per card, four angles side-by-side. Averages grouped first (easy to
# scan), then per-angle min/max, then per-angle scan counts.
# ── Tap-and-Go test tuning ──
# Mirrors the UFactory Studio Blockly pattern (Lite 6 max TCP):
#   repeat N times:          # N = GUI "Taps per angle" (cfg_scans)
#     set TCP speed 500 / acc 50000
#     relative −Z stroke     (Wait=false)
#     wait DOWN_DWELL        # listen for credential wedge during this window
#     relative +Z stroke     (Wait=false)
#     wait UP_DWELL          # reader reset between taps
# Timing is ms from down-move fire → wedge read (not arrival-at-floor).
# Floor clamp: if a full stroke would go below MARK reader top (+ STOP gap),
# the relative down is shortened to stop AT the floor and the matching up uses
# that same distance — never crush the reader.
TAPGO_DESCENT_SPEED_MM_S = 500.0     # Lite 6 hardware max TCP speed (can't exceed)
TAPGO_DESCENT_ACC = 50000.0          # hard acceleration so it reaches max speed fast
TAPGO_STROKE_MM = 100.0              # relative ±Z stroke (Studio "move 100 mm")
TAPGO_APPROACH_ABOVE_READER_MM = TAPGO_STROKE_MM  # start high enough for a full stroke
TAPGO_DOWN_DWELL_S = 0.5             # fixed wait after firing the down move
TAPGO_UP_DWELL_S = 1.0               # fixed wait after firing the up move (reader reset)
TAPGO_STOP_ABOVE_FLOOR_MM = 0.0      # stop this far above reader top (0 = card touches)
# Listen window equals the down dwell (Studio wait after down). Kept as a named
# alias for CSV metadata / miss messages.
TAPGO_READ_TIMEOUT_S = TAPGO_DOWN_DWELL_S
# Back-compat alias (older code / docs referred to "reset dwell").
TAPGO_RESET_DWELL_S = TAPGO_UP_DWELL_S

TAPGO_CSV_HEADER = [
    "Run", "Card #", "Angle", "Card Title", "Card Code",
    "Taps", "Reads", "Misses", "Avg (ms)", "Min (ms)", "Max (ms)",
    "Tap times (ms)", "Error / Skip",
]

# ── Deadzone test tuning ──
# Ascend from MARK reader top (card touching) while the reader is in continuous
# keyboard-wedge mode. Step/speed come from DESCENT_PRESETS (same Slowest–Fastest
# as read-height). Distinguishing deadzone vs end-of-field (plain language):
#   • Deadzone: reading stops for a few steps, then resumes while still ascending
#     through the field. Logged height = first loss (mm above reader).
#   • End of field / exit: reading stops and stays stopped for EOF_STEPS, OR the
#     card reaches DEADZONE_MAX_ABOVE_READER_MM / max travel time. That final
#     loss is NOT a deadzone — the card simply left the readable range.
#   SEEKING → READING → GAP ─┬─ recover → deadzone recorded, back to READING
#                            └─ EOF_STEPS misses → exit (done; not a deadzone)
DEADZONE_GAP_CONFIRM_STEPS = 2   # min consecutive no-reads to treat as a real gap
DEADZONE_EOF_STEPS = 10          # consecutive no-reads after a read → end of field
DEADZONE_MAX_ABOVE_READER_MM = float(
    getattr(config, "READER_FALLBACK_SEARCH_ABOVE_READER_MM", 150.0)
)
DEADZONE_MAX_TRAVEL_S = 180.0    # hard time cap so ascent never runs forever
DEADZONE_DWELL_S = 0.40          # listen window per ascent step (> continuous lockout)
DEADZONE_SETTLE_S = 0.05         # brief settle after each step before listening
DEADZONE_FLOOR_READ_TIMEOUT_S = 3.0  # must see a continuous read at the floor first
DEADZONE_CSV_HEADER = [
    "Run", "Card #", "Angle", "Card Title", "Card Code",
    "Deadzone found", "Deadzone height(s) mm", "Exit height mm", "Error / Skip",
]

CSV_DATA_HEADER = [
    "Run", "Card #", "Card Title", "Card Code",
    # ASCII "deg" (not °) so Excel on Windows never shows mojibake "Â°"
    # Side is omitted — A/B is already encoded in Card Code (A### / B###).
    "0 deg Avg (mm)", "90 deg Avg (mm)", "180 deg Avg (mm)", "270 deg Avg (mm)",
    "0 deg Min", "0 deg Max", "90 deg Min", "90 deg Max",
    "180 deg Min", "180 deg Max", "270 deg Min", "270 deg Max",
    "0 deg Scans", "90 deg Scans", "180 deg Scans", "270 deg Scans",
    "Card Max (mm)", "Error / Skip",
]
CSV_WIDTH = len(CSV_DATA_HEADER)


def _csv_row(cells):
    """Pad/truncate a row to the fixed results width so every line aligns."""
    row = list(cells)
    while len(row) < CSV_WIDTH:
        row.append("")
    return row[:CSV_WIDTH]


def _parse_saved_avg(value):
    """Parse a saved average height; reject blanks, negatives and known-bad refs."""
    if value is None or value == "":
        return None
    try:
        v = float(value)
        if v < 0:
            return None
        if is_bad_reference_height(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


# wiggle tuning (barcode scan pose) — sourced from config
WIGGLE_DEG = config.WIGGLE_DEG
WIGGLE_LIFT_DEG = config.WIGGLE_LIFT_DEG
WIGGLE_SPEED = config.WIGGLE_SPEED
WIGGLE_ACC = config.WIGGLE_ACC
WIGGLE_PAUSE_S = config.WIGGLE_PAUSE_S

# ── rf IDEAS brand palette ─────────────────────────────────────────────────
BRAND = {
    'red': '#ED2024', 'red_hover': '#C9191D', 'text': '#58595B',
    'purple': '#494A8B', 'border': '#A7A9AC', 'divider': '#DCDCDE',
    'bg': '#F4F4F6', 'card': '#FFFFFF', 'light': '#EEEEEE',
    'dark': '#161618', 'log_bg': '#1C1C1F', 'green': '#2E9E5B',
    'amber': '#E8A13D', 'white': '#FFFFFF', 'subtle': '#8A8A8E',
}
FONT_H1    = ("Verdana", 14, "bold")
FONT_H2    = ("Verdana", 9, "bold")
FONT_BODY  = ("Verdana", 10)
FONT_SMALL = ("Verdana", 8)
FONT_BTN   = ("Verdana", 10, "bold")
FONT_MONO  = ("Consolas", 9)

# ── reader height library (table-to-top), loaded from card_readers.json ────
READER_HEIGHTS_PATH = os.path.join(AUTOMATION_ROOT, "..", "files", "card_readers.json")
SAFETY_MARGIN_MM = 5.0          # legacy; descent floor is config.READER_DESCENT_MIN_HEIGHT_MM


def load_reader_library(path=READER_HEIGHTS_PATH):
    """Optional legacy reader-height library (card_readers.json).

    Reader height for testing now comes from MARK READER TOP only. If the JSON
    file is absent, return empty heights and the fixed READER_TYPES list is used
    for the dropdown.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        models, heights = [], {}
        for r in data.get("card_readers", []):
            name = r.get("model") or r.get("id")
            if name is None:
                continue
            models.append(name)
            h = r.get("height_mm")
            heights[name] = float(h) if isinstance(h, (int, float)) else None
        if heights:
            return models, heights
    except FileNotFoundError:
        pass
    except Exception as e:
        print("Reader library ignored ({}): {}".format(path, e))
    base = list(getattr(config, "READER_MODELS", []))
    return base, {m: None for m in base}


READER_LIBRARY, READER_HEIGHTS = load_reader_library()
# Fixed dropdown — heights are captured live via MARK READER TOP, not from JSON.
READER_TYPES = ["PICO", "HIP2_SP", "MICRO", "NANO_USBA", "MINI_DESKTOP", "OTHER"]

# Nominal table-to-top heights (mm) kept in code so a run still works when
# card_readers.json is absent. MARK READER TOP always overrides these.
NOMINAL_READER_HEIGHTS_MM = {
    "PICO": 25.0,
    "HIP2_SP": 44.0,
    "MICRO": 18.0,
    "NANO_USBA": 40.0,
    "MINI_DESKTOP": 40.0,
}


def _reader_height_for(name):
    """Nominal reader height (mm, table-to-top) for a dropdown label.

    Order: optional card_readers.json → built-in nominal table → None (OTHER).
    MARK READER TOP takes priority over both (handled by the caller).
    """
    if not name:
        return None
    key = name.strip().upper()
    for k, v in READER_HEIGHTS.items():
        if str(k).strip().upper() == key and v is not None:
            return v
    return NOMINAL_READER_HEIGHTS_MM.get(key)


def _default_reader_model():
    """HIP2_SP when available, otherwise the first model in the library."""
    if DEFAULT_READER_MODEL in READER_TYPES:
        return DEFAULT_READER_MODEL
    return READER_TYPES[0] if READER_TYPES else DEFAULT_READER_MODEL
