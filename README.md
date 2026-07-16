# Credential Read Height Automation

Automated credential **read-height** and **tap-and-go** testing for rf IDEAS WAVE ID
readers using a **UFACTORY Lite 6** robot arm, a USB keyboard-wedge barcode scanner,
and RRMTool CLI (HWG+) configuration.

The robot picks a card from a stack, scans its barcode to identify the card type,
configures the reader for that type, then presents the card at selected wrist angles
to measure **read height** and/or **tap-and-go** timing. Results land in `results/`
CSV; baselines can update `files/AllCards.csv`.

## Test modes (GUI)

| Mode | What it does |
|------|----------------|
| **Read Height** | Multi-angle zone-in descent; records height above reader per angle |
| **Tap and Go** | Fast plunge timing to a calibrated reference; records tap times |
| **Combined** | Tick both — Read Height then Tap-and-Go on each card (optional flip for side B) |

## Repository layout

```
card-read-height/
├── README.md, ARCHITECTURE.md, REFACTOR_NOTES.md
├── docs/                    ← SETUP / USAGE / API / TROUBLESHOOTING
├── files/
│   ├── AllCards.csv         ← barcode → card / baselines
│   ├── card_readers.json    ← reader model heights (GUI)
│   └── hwg/*.hwg+           ← reader-config files (NOT under Automation/)
├── results/                 ← test CSVs (Keep/ curated)
└── Automation/              ← all runnable Python (cwd for scripts)
    ├── config.py            ← central settings + path helpers
    ├── requirements.txt
    ├── barcode/scanner.py
    ├── gui/                 ← Tk GUI (split modules)
    │   ├── gui.py           ← entry: python gui/gui.py
    │   ├── app.py           ← App shell (checklist, run, CSV)
    │   ├── gui_robot.py     ← GuiRobot orchestration
    │   ├── constants.py, widgets.py
    │   ├── arm_gl.py        ← optional Live arm (OpenGL)
    │   ├── robot_viewer.py  ← optional browser mesh viewer
    │   └── viewer/meshes/visual/*.stl
    ├── reader/              ← RRMTool + HID tools
    ├── robot/               ← move.py + cardreadheight.py CLI
    └── tools/               ← optional helpers (cardheight, move2, ros2)
```

> **Paths matter:** `config.py` treats the folder *above* `Automation/` as the
> workspace root. HWG files live in **`files/hwg/`**, not `Automation/hwg/`.

## Quick start

```bash
cd Automation
pip install -r requirements.txt

# Launch the GUI
python gui/gui.py

# …or run the CLI test
python robot/cardreadheight.py --cycles 14
```

See **[docs/SETUP.md](docs/SETUP.md)** for installation and configuration,
**[docs/USAGE.md](docs/USAGE.md)** for how to run tests, **[docs/API.md](docs/API.md)**
for the module reference, and **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** when
something breaks. Refactor history: **[REFACTOR_NOTES.md](REFACTOR_NOTES.md)**.

---

Internal use only — rf IDEAS
