"""Central configuration for rf IDEAS Credential Read Height Automation.

Role
    Single source of truth for robot IP, speeds, poses, height math, card-type
    map, and workspace path helpers. Imported by nearly every Automation module.

Inputs
    Environment overrides: ``RRM_CLI``, ``ROBOT_IP``. Optional candidate paths
    for RRMTool_CLI on Windows.

Outputs / side effects
    Resolves absolute paths under workspace ``files/`` (incl. ``files/hwg/``),
    ``results/``, and ``Automation/logs/``. Does not talk to hardware itself;
    callers use these values when driving the arm / RRMTool / CSV I/O.

Workspace root is the parent of ``Automation/`` — do not move ``files/`` or
``results/`` without updating ``PATHS`` here.
"""

import os

AUTOMATION_ROOT = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.dirname(AUTOMATION_ROOT)

# ---- RRMTool / reader ----
_RRM_CLI_CANDIDATES = [
    os.environ.get("RRM_CLI"),
    r"C:\Program Files\rf IDEAS\RRMTool\RRMTool_CLI.exe",
    os.path.expanduser(
        r"~\Downloads\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe"
    ),
]


def resolve_rrm_cli() -> str:
    """Return the first existing RRMTool_CLI path, or the Program Files default."""
    for path in _RRM_CLI_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return _RRM_CLI_CANDIDATES[1]


RRM_CLI = resolve_rrm_cli()

# USB HID (ReaderConfigSDK.py)
VENDOR_ID = 0x0C27
PRODUCT_ID = 0x3BFA
CARD_TYPES = {
    "CEPAS": 0x7A01,
}

# ---- Motion speeds (transit) — matches release→next-pick pick leg (180°/s) ----
# Card drop sequence intentionally uses RELEASE_* below (move + pause + suction off).
MOTION_JOINT_SPEED = 180
MOTION_JOINT_ACC = 1100
MOTION_HOME_SPEED = MOTION_JOINT_SPEED
MOTION_HOME_ACC = MOTION_JOINT_ACC
MOTION_FAST_JOINT_SPEED = MOTION_JOINT_SPEED
MOTION_FAST_JOINT_ACC = MOTION_JOINT_ACC
MOTION_TRANSIT_JOINT_SPEED = MOTION_JOINT_SPEED
MOTION_TRANSIT_JOINT_ACC = MOTION_JOINT_ACC
MOTION_PARK_JOINT_SPEED = MOTION_JOINT_SPEED
MOTION_PARK_JOINT_ACC = MOTION_JOINT_ACC
MOTION_TCP_SPEED = 400
MOTION_TCP_ACC = 3000
# Faster vertical moves when clearing the reader after scans
MOTION_EXIT_TCP_SPEED = 500
MOTION_EXIT_TCP_ACC = 4000
MOTION_TCP_RADIUS = 25.0
MOTION_JOINT_RADIUS = 60.0
MOTION_POST_RELEASE_JOINT_RADIUS = 80.0
MOTION_PICK_DESCENT_SPEED = 150
MOTION_PICK_DESCENT_ACC = 2000
POST_PICK_LIFT_MM = 50
POST_MOTION_PAUSE_S = 0.0
# Barcode wiggle at scan pose
WIGGLE_DEG = 4.0
WIGGLE_LIFT_DEG = 3.0
WIGGLE_SPEED = 150
WIGGLE_ACC = 900
WIGGLE_PAUSE_S = 0.10

# ---- Lite 6 robot ----
ROBOT_IP = os.environ.get("ROBOT_IP", "192.168.1.177")
ROBOT_SPEED_SCALE = 0.50
ROBOT_DESCENT_SPEED_MM_S = 5.0
ROBOT_TABLE_Z_FLOOR_MM = None
ROBOT_PICK_Z_DECREMENT_MM = 2.0
BIN_DEPTH_MM = 53.0
CARD_STACK_COUNT = 14

TABLE_Z_MM = 59.81
SMART_PICK_TABLE_Z_MM = 61.0
PICK_SEARCH_STEP_MM = 3.0
PICK_SEARCH_MAX_MM = 55.0
PICK_TABLE_CLEARANCE_MM = 2.0

# Commissioned joint poses (degrees)
HOME_ANGLE = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
PICK_ANGLE = [-43.6, 50.0, 71.5, 180.0, -19.8, -134.4]
BARCODE_SCAN_ANGLE = [-43.7, 48.5, 71.5, 142.4, -74.1, -106.1]
PLACE_ANGLE_SIDE_A = [4.2, 27.4, 39.5, 186.7, -10.4, -90]
PLACE_ANGLE_SIDE_B = [4.2, 27.4, 39.5, 186.7, -10.4, -180]
RELEASE_ANGLE = [44.4, 58.7, 76.5, 168.6, -14.4, -112.8]
# Fast smooth move to drop zone, brief pause, then suction off
RELEASE_SPEED = 180
RELEASE_ACC = 1100
RELEASE_DWELL_S = 0.25
# GUI read-height poses use a slightly offset wrist angle
PLACE_ANGLE_SIDE_A_GUI = [4.2, 27.4, 39.5, 186.7, -10.4, -93.4]
PLACE_ANGLE_SIDE_B_GUI = [4.2, 27.4, 39.5, 186.7, -10.4, -183.4]

# Staging poses before reader descent — inline vs orthogonal (90° wrist), not card face A/B
READER_DESCENT_STAGING_INLINE = [0.5, 15.9, 39.9, 0.1, 26.7, -0.8]
READER_DESCENT_STAGING_ORTHOGONAL = [0.5, 15.9, 39.9, 0.1, 26.7, -90.8]
READER_DESCENT_STAGING_ANGLE_A = READER_DESCENT_STAGING_INLINE  # alias
READER_DESCENT_STAGING_ANGLE_B = READER_DESCENT_STAGING_ORTHOGONAL  # alias
READER_DESCENT_STAGING_ANGLE = READER_DESCENT_STAGING_INLINE  # alias
READER_DESCENT_SPEED_MM_S = 10.0
READER_DESCENT_STEP_MM = 2.0
# Pause after each step, then listen this long for a credential read before stepping again
READER_DESCENT_SETTLE_S = 0.25
READER_DESCENT_DWELL_S = 0.65
# Fast first pass: find read zone quickly; height is NOT recorded
READER_FAST_DESCENT_SPEED_MM_S = 80.0
READER_FAST_DESCENT_STEP_MM = 4.0
READER_FAST_DWELL_S = 0.15
# Finest step on the final (recorded) zone-in tap
READER_FINAL_DESCENT_STEP_MM = 1.0
# After fast locate, rise this many mm above that point before slow measured scans
READER_REFINE_CLEARANCE_MM = 18.0
READER_REFINE_MAX_DROP_MM = 22.0
# Card read face is this many mm above TCP when suction is holding the card.
SUCTION_CUP_CARD_OFFSET_MM = 4.0


def card_face_above_table_from_tcp(tcp_above_table_mm: float) -> float:
    """Convert measured TCP height to card read-face height (mm above table)."""
    return tcp_above_table_mm + SUCTION_CUP_CARD_OFFSET_MM


def tcp_above_table_for_card_face(card_face_above_table_mm: float) -> float:
    """TCP Z target so the card read face sits at the given height above table."""
    return card_face_above_table_mm - SUCTION_CUP_CARD_OFFSET_MM

# ---- Test defaults ----
RETRY_COUNT = 3
DWELL_TIME_S = 0.15
DEFAULT_START_HEIGHT_MM = 120.0
DEFAULT_STEP_SIZE_MM = 1.0
DEFAULT_READ_SPEC_MM = 63.5
READ_HEIGHT_MIN_MM = 10.0
READ_HEIGHT_DWELL_S = 0.40
READ_HEIGHT_SETTLE_S = 0.25
READ_HEIGHT_DESCENT_SPEED = 5
READ_HEIGHT_DESCENT_ACC = 50
READER_APPROACH_SPEED = 400
READER_APPROACH_ACC = 3000
# Fallback when no saved card average (mm above reader top) — approach start height
READER_FALLBACK_SEARCH_ABOVE_READER_MM = 150.0
# Bogus reference band: blank stored baselines ±10 mm of 70 (in-zone wedge reads)
READER_BAD_REFERENCE_BAND_LOW_MM = 60.0
READER_BAD_REFERENCE_BAND_HIGH_MM = 80.0
# Legacy exports (mm above table): arm stuck in zone reads this band above reader top
READER_INZONE_STUCK_LOW_ABOVE_READER_MM = 14.0
READER_INZONE_STUCK_HIGH_ABOVE_READER_MM = 32.0
# After finishing inline/orthogonal on one wrist angle, rise to this height above reader
READER_CLEAR_AFTER_SIDE_ABOVE_READER_MM = 40.0
# Before moving to release: minimum height above reader top to clear the read area
READER_PRE_RELEASE_CLEARANCE_ABOVE_READER_MM = 50.0
# Deprecated: was a relative lift from staging; GUI now uses saved averages + clearance
READER_DESCENT_START_LIFT_MM = 70.0
# When a saved average exists: start this many mm above that avg (mm above reader top)
READER_APPROACH_CLEARANCE_MM = 15.0
# Lowest allowed TCP height: this many mm above the table surface
READER_DESCENT_MIN_HEIGHT_MM = 44.0
# Hard ceiling on a single descent move (after the pre-lift)
READER_DESCENT_MAX_DROP_MM = 250.0

READ_HEIGHT_SPEC_MM = {
    "typical_min": 25.4,
    "typical_max": 101.6,
}

READER_MODELS = [
    "Mini Desktop", "HIP2", "NANO", "MICRO", "PICO", "OTHER",
]

TEST_MODES = [
    "Barcode driven",
    "Side A only",
    "Side B (flip test)",
]

SPEED_PRESETS = {
    "Slow": 0.10,
    "Medium": 0.50,
    "Fast": 1.00,
}

# Barcode prefix → card type + HWG filename (fallback when not in AllCards.csv)
CARD_TYPE_MAP = {
    "a005": {"name": "CEPAS", "title": "CEPAS", "hwg": "CEPAS.hwg+", "side": "A"},
    "b005": {"name": "CEPAS", "title": "CEPAS", "hwg": "CEPAS.hwg+", "side": "B"},
}

PATHS = {
    "hwg": os.path.join(WORKSPACE_ROOT, "files", "hwg"),
    "logs": os.path.join(AUTOMATION_ROOT, "logs"),
    "results": os.path.join(WORKSPACE_ROOT, "results"),
    "files": os.path.join(WORKSPACE_ROOT, "files"),
}

ALL_CARDS_CSV = os.path.join(PATHS["files"], "AllCards.csv")

CSV_FIELDS = [
    "Card Type", "Card Title", "Card Data", "Read Height Spec",
    "Read Height — Side A (mm)", "Read Height — Side A (in)",
    "Orthogonal Read Height — Side A (mm)",
    "Read Height — Side B (mm)", "Read Height — Side B (in)",
    "Orthogonal Read Height — Side B (mm)",
    "Average Read Height (mm)", "Error / Skip Flag",
]


def get_hwg_path(filename: str) -> str:
    """Absolute path under ``files/hwg/`` for an HWG+ filename."""
    return os.path.join(PATHS["hwg"], filename)


def get_log_path(filename: str) -> str:
    """Absolute path under ``Automation/logs/``."""
    return os.path.join(PATHS["logs"], filename)


def get_results_path(filename: str) -> str:
    """Absolute path under workspace ``results/``."""
    return os.path.join(PATHS["results"], filename)


def ensure_paths_exist() -> None:
    """Create ``PATHS`` directories (hwg, logs, results, files) if missing."""
    for key in PATHS:
        os.makedirs(PATHS[key], exist_ok=True)
