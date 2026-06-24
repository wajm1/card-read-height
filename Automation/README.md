# rf IDEAS — Credential Read Height Automation

Automated credential read-height testing using a **UFACTORY Lite 6** robot arm and
rf IDEAS **WAVE ID** readers. Full docs are in [`../docs/`](../docs/README.md).

## Folder layout

```
Automation/
├── config.py            # Central settings: paths, robot IP, test params, card map
├── requirements.txt     # Python dependencies
├── README.md            # This quick reference
│
├── barcode/
│   └── scanner.py       # Barcode capture + card lookup (files/AllCards.csv)
│
├── gui/
│   └── gui.py           # Tkinter control + monitoring GUI
│
├── hwg/                 # HWG+ reader-config files (one per card technology)
│   └── *.hwg+
│
├── reader/
│   ├── cli.py               # RRMTool CLI helpers (used by runner/GUI)
│   ├── ReaderConfig.py      # Scan-and-configure loop (no robot)
│   └── ReaderConfigSDK.py   # Direct USB HID reader tool
│
├── robot/
│   ├── cardreadheight.py    # Main test runner (CLI entry point)
│   ├── move.py              # RobotMain motion logic
│   ├── cardheight.py        # Standalone height helper
│   └── test_settings.py     # Live-tunable test parameters
│
├── logs/                # Runtime logs (git-ignored)
└── files/
    └── Robot Test Cards.xlsx   # Reference card list
```

## Setup

```bash
pip install -r requirements.txt
```

Edit `config.py` for `RRM_CLI`, `ROBOT_IP`, and the card mapping.

## Run

```bash
# GUI
python gui/gui.py

# Command line (see ../docs/USAGE.md for all options)
python robot/cardreadheight.py --cycles 14
python robot/cardreadheight.py --dry-run     # no robot — validate pipeline
```

## Reader tools

```bash
python reader/ReaderConfig.py                # scan-and-configure loop
python reader/ReaderConfigSDK.py about       # reader info (direct USB HID)
python reader/ReaderConfigSDK.py set-cepas   # configure for CEPAS
```

---

Internal use only — rf IDEAS
