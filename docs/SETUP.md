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
  Windows-only modules such as `msvcrt` and `keyboard`).
- **RRMTool** (rf IDEAS Reader Management Tool) installed, for CLI-based reader config.

## 1. Install Python dependencies

```bash
cd Automation
pip install -r requirements.txt
```

`requirements.txt` pulls in:

- `keyboard` — barcode-scanner capture
- `xarm-python-sdk` — Lite 6 robot control
- `hid` / `hidapi` *(optional)* — only needed for direct USB HID reader config
  (`reader/ReaderConfigSDK.py`)

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

## 3. Verify connections

```bash
cd Automation

# Reader (direct USB HID) — prints reader info
python reader/ReaderConfigSDK.py about

# Robot + reader without motion — validates the pipeline and writes a dry-run CSV
python robot/cardreadheight.py --dry-run
```

## 4. Card → reader-config mapping

A scanned barcode is matched against **`files/AllCards.csv`** (at the repository root):

```csv
Barcode,Name,Part Number,Side
A001,CASI-RUSCO UID,620-IM-0013,A
A003,HID Prox UID (608x),600-I-0013,A
```

The card's **Name** maps directly to an HWG+ file of the same name in
`Automation/hwg/` (e.g. `CASI-RUSCO UID` → `Automation/hwg/CASI-RUSCO UID.hwg+`). To
support a new card:

1. Create/obtain its `.hwg+` file and drop it in `Automation/hwg/`.
2. Add a row to `files/AllCards.csv` whose `Name` matches the HWG filename (without the
   `.hwg+` extension).

(There is also a small `CARD_TYPE_MAP` in `config.py` used by the barcode-prefix path for
CEPAS test cards.)

## Project structure

```
card-read-height/
├── README.md
├── .gitignore
├── Automation/
│   ├── config.py            Central settings
│   ├── requirements.txt
│   ├── README.md            Quick reference
│   ├── barcode/scanner.py   Barcode capture + card lookup
│   ├── gui/gui.py           Tkinter GUI
│   ├── hwg/*.hwg+           Reader-config files (one per card technology)
│   ├── logs/                Runtime logs (git-ignored)
│   ├── reader/
│   │   ├── cli.py               RRMTool CLI helpers
│   │   ├── ReaderConfig.py      Scan-and-configure loop
│   │   └── ReaderConfigSDK.py   Direct USB HID tool
│   ├── robot/
│   │   ├── cardreadheight.py    Main test runner (CLI)
│   │   ├── move.py              RobotMain motion logic
│   │   ├── tools/cardheight.py        Standalone height helper
│   │   └── test_settings.py     Live-tunable test parameters
│   └── files/Robot Test Cards.xlsx
├── docs/                    This documentation
├── files/AllCards.csv       Barcode → card-type lookup
└── results/                 Test-output CSVs (Keep/ is retained)
```

> **Important:** `config.py` derives the workspace root as the folder *above*
> `Automation/`. Keep `files/` and `results/` at the top level, or update the `PATHS`
> dictionary in `config.py` to match.
