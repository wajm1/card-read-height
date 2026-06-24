# config.py
# Central configuration for rf IDEAS Credential Read Height Automation

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

# ---- Lite 6 robot (TODO: set during commissioning) ----
ROBOT_IP = os.environ.get("ROBOT_IP", "192.168.1.177")
ROBOT_SPEED_SCALE = 0.50
ROBOT_DESCENT_SPEED_MM_S = 5.0
ROBOT_TABLE_Z_FLOOR_MM = None
ROBOT_PICK_Z_DECREMENT_MM = 2.0
BIN_DEPTH_MM = 53.0
CARD_STACK_COUNT = 14

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
READER_APPROACH_SPEED = 10
READER_APPROACH_ACC = 100

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

# Barcode prefix → card type + HWG filename (in hwg/)
CARD_TYPE_MAP = {
    "a005": {"name": "CEPAS", "title": "CEPAS", "hwg": "cepas.hwg+", "side": "A"},
    "b005": {"name": "CEPAS", "title": "CEPAS", "hwg": "cepas.hwg+", "side": "B"},
}

PATHS = {
    "hwg": os.path.join(AUTOMATION_ROOT, "hwg"),
    "logs": os.path.join(AUTOMATION_ROOT, "logs"),
    "results": os.path.join(WORKSPACE_ROOT, "results"),
    "files": os.path.join(WORKSPACE_ROOT, "Files"),
}

LOW_BAND_CARDS_CSV = os.path.join(PATHS["files"], "LowBandCards.csv")
TABLE_Z_MM = 59.81

CSV_FIELDS = [
    "Card Type", "Card Title", "Card Data", "Read Height Spec",
    "Read Height — Side A (mm)", "Read Height — Side A (in)",
    "Orthogonal Read Height — Side A (mm)",
    "Read Height — Side B (mm)", "Read Height — Side B (in)",
    "Orthogonal Read Height — Side B (mm)",
    "Average Read Height (mm)", "Error / Skip Flag",
]


def get_hwg_path(filename: str) -> str:
    return os.path.join(PATHS["hwg"], filename)


def get_log_path(filename: str) -> str:
    return os.path.join(PATHS["logs"], filename)


def get_results_path(filename: str) -> str:
    return os.path.join(PATHS["results"], filename)


def ensure_paths_exist() -> None:
    for key in PATHS:
        os.makedirs(PATHS[key], exist_ok=True)
