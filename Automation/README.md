# rf IDEAS — Credential Read Height Automation

Automated credential read-height / tap-and-go testing using a **UFACTORY Lite 6**
robot arm and rf IDEAS **WAVE ID** readers. Full docs are in [`../docs/`](../docs/README.md).

## Folder layout

```
Automation/
├── config.py            # Central settings: paths, robot IP, poses, card map
├── requirements.txt     # Python dependencies (+ commented optional Live-arm lines)
├── README.md            # This quick reference
│
├── barcode/
│   └── scanner.py       # Barcode capture + card lookup (../files/AllCards.csv)
│
├── gui/
│   ├── gui.py           # Entry point — python gui/gui.py
│   ├── app.py           # Tk App (checklist, test select, run, CSV)
│   ├── gui_robot.py     # GuiRobot orchestration (subclass of RobotMain)
│   ├── constants.py     # Brand, poses, joint-limit helpers, reader library
│   ├── widgets.py       # Shared Tk helpers
│   ├── arm_gl.py        # Optional Live arm (OpenGL meshes)
│   ├── robot_viewer.py  # Optional browser three.js viewer
│   └── viewer/          # lite6 html/urdf + meshes/visual/*.stl
│
├── reader/
│   ├── cli.py               # RRMTool CLI helpers (used by runner/GUI)
│   ├── ReaderConfig.py      # Scan-and-configure loop (no robot)
│   └── ReaderConfigSDK.py   # Direct USB HID reader tool
│
├── robot/
│   ├── cardreadheight.py    # Main CLI test runner (--gui → gui.gui.main)
│   ├── move.py              # RobotMain motion logic
│   └── test_settings.py     # CLI-tunable params (not used by GUI)
│
├── tools/
│   ├── cardheight.py            # Commissioning Z jogger
│   ├── experimental/move2.py    # Quarantined reverse characteriser
│   └── ros2/ros2_bridge.py      # Optional UDP → ROS2 bridge
│
└── logs/                # Runtime logs (git-ignored)

../files/
├── AllCards.csv         # Barcode → card-type lookup
├── card_readers.json    # Reader model heights (GUI)
└── hwg/*.hwg+           # HWG+ reader-config files (one per card technology)

../results/              # Test output CSVs
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
