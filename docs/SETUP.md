# Setup

Installation and configuration for the Credential Read Height Automation system.

## Prerequisites

**Hardware**

- UFACTORY **Lite 6** robot arm, powered on and reachable on the network.
- rf IDEAS **WAVE ID** reader connected by USB.
- USB **barcode scanner** (keyboard-wedge type).
- A card stack / fixture positioned for the robot's saved poses.

**Software**

- **Python 3.10+** on the control PC (Windows is the primary target — some scripts use
  Windows-only modules such as `msvcrt` and `keyboard`). In practice the GUI is often
  run under **Python 3.14**; **3.10+ remains the documented minimum**.
- **RRMTool** (rf IDEAS Reader Management Tool) installed, for CLI-based reader config.

## 1. Install Python dependencies

```bash
cd Automation
pip install -r requirements.txt
```

**Required** (from `requirements.txt`):

- `keyboard` — barcode-scanner capture
- `xarm-python-sdk` — Lite 6 robot control

**Optional:**

```bash
# Live arm panel inside the GUI
pip install pyopengltk PyOpenGL numpy

# Direct USB HID reader tool (reader/ReaderConfigSDK.py)
pip install hid
# or: pip install hidapi

# ROS2 bridge (tools/ros2/ros2_bridge.py) — run in a ROS2 environment
# (Ubuntu / WSL2), not the Windows GUI Python. See tools/ros2/README.txt.
```

Commented optional lines also appear in `Automation/requirements.txt`.

## 2. Configure `config.py`

All settings live in `Automation/config.py`. The values you are most likely to change:

```python
# Reader Management Tool CLI — auto-detected, or set the RRM_CLI env var / edit the path
RRM_CLI = resolve_rrm_cli()

# USB HID reader identity (for ReaderConfigSDK.py)
VENDOR_ID  = 0x0C27
PRODUCT_ID = 0x3BFA

# Lite 6 robot
ROBOT_IP        = "192.168.1.177"   # or set the ROBOT_IP env var
CARD_STACK_COUNT = 14               # cards per run

# Test defaults
DEFAULT_START_HEIGHT_MM = 120.0
DEFAULT_STEP_SIZE_MM    = 1.0
READ_HEIGHT_MIN_MM      = 10.0      # failure floor
```

The RRMTool path is resolved in this order: the `RRM_CLI` environment variable, then
`C:\Program Files\rf IDEAS\RRMTool\RRMTool_CLI.exe`, then a `~/Downloads/...` fallback.
Set `RRM_CLI` or edit `_RRM_CLI_CANDIDATES` if your install lives elsewhere.

## 3. Config / data files (workspace root)

| Path | Purpose |
|------|---------|
| `Automation/config.py` | Robot IP, speeds, poses, path helpers |
| `files/AllCards.csv` | Barcode → Name / Part Number / Side / saved averages |
| `files/hwg/*.hwg+` | One HWG+ per card technology (filename = AllCards **Name**) |
| `files/card_readers.json` | Reader library: `config` block + `card_readers[]` with `id`/`model`, `height_mm`, optional overrides |

**HWG path is `files/hwg/` — not `Automation/hwg/`.** (`config.PATHS["hwg"]` points at the workspace `files/hwg/` folder.)

`card_readers.json` template fields (briefly):

- `config.mode` — `"absolute"` (recommended) or `"relative"`
- `config.table_z_mm` — absolute Z of the table surface (calibrate once)
- `config.default_read_gap_mm`, `approach_clearance_mm`, `staging_angle_deg`, …
- Each `card_readers[]` entry: `id` / `model`, `height_mm`, optional `read_gap_mm`, `enabled`, `notes`

## 4. Verify the arm and pipeline

```bash
cd Automation

# Network reachability (replace with your ROBOT_IP)
ping 192.168.1.177

# Pipeline without motion — validates CSV/results path
python robot/cardreadheight.py --dry-run

# Optional: also load a sample HWG during dry-run
python robot/cardreadheight.py --dry-run --reader-config
```

**Pre-flight checklist**

1. Arm powered, no other session holding the connection (close UFACTORY Studio if needed).
2. Reader USB plugged; RRMTool_CLI found (`RRM_CLI` / Program Files).
3. Barcode scanner in keyboard-wedge mode (types into Notepad).
4. Card stack seated; HWG files present under `files/hwg/`.
5. For Live arm: meshes in `Automation/gui/viewer/meshes/visual/*.stl` and optional OpenGL deps installed.

## 5. Launch GUI and CLI

```bash
cd Automation

# GUI (primary)
python gui/gui.py

# Same GUI via CLI flag
python robot/cardreadheight.py --gui

# Headless CLI run
python robot/cardreadheight.py --cycles 14
```

## 6. Live arm / mesh assets

Meshes **must** be in:

```
Automation/gui/viewer/meshes/visual/
    link_base.stl, link1.stl … link6.stl
```

(singular `visual/`, not `visuals/`). The browser viewer also needs
`Automation/gui/viewer/lite6_viewer.html` and `lite6.urdf` beside that tree.

## Card → reader-config mapping

A scanned barcode is matched against **`files/AllCards.csv`**:

```csv
Barcode,Name,Part Number,Side
A001,CASI-RUSCO UID,620-IM-0013,A
A003,HID Prox UID (608x),600-I-0013,A
```

The card's **Name** maps to an HWG+ file of the same name in **`files/hwg/`**
(e.g. `CASI-RUSCO UID` → `files/hwg/CASI-RUSCO UID.hwg+`). To support a new card:

1. Drop its `.hwg+` file in `files/hwg/`.
2. Add a row to `files/AllCards.csv` whose `Name` matches the HWG filename (without `.hwg+`).

(`CARD_TYPE_MAP` in `config.py` is a small barcode-prefix fallback for CEPAS test cards.)

## Project structure

```
card-read-height/
├── README.md
├── ARCHITECTURE.md
├── REFACTOR_NOTES.md
├── docs/
├── files/
│   ├── AllCards.csv
│   ├── card_readers.json
│   └── hwg/*.hwg+
├── results/
└── Automation/
    ├── config.py
    ├── requirements.txt
    ├── README.md
    ├── barcode/scanner.py
    ├── gui/
    │   ├── gui.py, app.py, gui_robot.py
    │   ├── constants.py, widgets.py
    │   ├── arm_gl.py, robot_viewer.py
    │   └── viewer/…/meshes/visual/*.stl
    ├── reader/
    │   ├── cli.py
    │   ├── ReaderConfig.py
    │   └── ReaderConfigSDK.py
    ├── robot/
    │   ├── cardreadheight.py
    │   ├── move.py
    │   └── test_settings.py      # CLI only — GUI does not import this
    └── tools/
        ├── cardheight.py
        ├── experimental/move2.py
        └── ros2/ros2_bridge.py
```

> **Important:** `config.py` derives the workspace root as the folder *above*
> `Automation/`. Keep `files/` and `results/` at the top level, or update the `PATHS`
> dictionary in `config.py` to match.
