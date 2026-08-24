<!-- Author: Wajahat Mahmood | Updated: 2026-07-30 | rf IDEAS — Proprietary and Confidential -->

# Credential Read Height Automation

Automated credential **read-height**, **tap-and-go**, and **deadzone** testing for
rf IDEAS WAVE ID readers using a **UFACTORY Lite 6** robot arm, a USB keyboard-wedge
barcode scanner, and RRMTool CLI (HWG+) configuration.

The robot picks a card from a stack, scans its barcode to identify the card type,
configures the reader for that type, then presents the card at selected wrist angles
to measure **read height** and/or **tap-and-go** timing. Results land in `results/`
CSV; baselines can update `files/AllCards.csv`.

## Test modes (GUI)

| Mode | What it does |
|------|----------------|
| **Read Height** | Multi-angle zone-in descent; records height above reader per angle |
| **Tap and Go** | Plunge from ~100 mm at 500 mm/s to the calibrated reader top; records read time in ms |
| **Deadzone** | Continuous-read slow ascent from the reader top; records any mid-field dead spot |
| **Combined** | Tick Read Height + Tap-and-Go — both run on each card (optional flip for side B) |

> **New (2026-07-30):** reader calibration is now remembered across GUI restarts,
> the calibration Left/Right arrow keys are corrected, and the Comment field is
> reliably typable. A headless **test suite** (`Automation/tests/`) locks in
> current behavior. See **[DECISION_LOG.md](DECISION_LOG.md)**.

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
    ├── persistence/         ← calibration_store.py (remembers MARK READER TOP)
    ├── tests/               ← headless pytest suite (FakeArm; no hardware needed)
    └── tools/               ← optional helpers (cardheight, move2, ros2)
```

> **Paths matter:** `config.py` treats the folder *above* `Automation/` as the
> workspace root. HWG files live in **`files/hwg/`**, not `Automation/hwg/`.

## Quick start

Follow the full checklist: **[docs/SETUP.md](docs/SETUP.md)**
(Python, pip, packages, RRM CLI, hardware, smoke test).

```bash
cd Automation
python -m pip install -r requirements.txt

# Launch the GUI
python gui/gui.py

# …or run the CLI test
python robot/cardreadheight.py --cycles 14

# run the headless test suite (no robot/reader needed)
python -m pip install -r requirements-dev.txt
python -m pytest
```

## Documentation

- **[docs/USER_MANUAL.md](docs/USER_MANUAL.md)** — start-to-finish operator guide:
  physical setup, calibration, running each test, troubleshooting the reader and
  barcode, adding cards / HWG files, and extending the program. **Start here.**
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — module map, data/control flow,
  and the program-structure diagram (**[docs/architecture_diagram.svg](docs/architecture_diagram.svg)**).
- **[DECISION_LOG.md](DECISION_LOG.md)** — 2026-07-30 changes, commit plan, and flagged data issues.
- Reference: [docs/SETUP.md](docs/SETUP.md) · [docs/USAGE.md](docs/USAGE.md) ·
  [docs/API.md](docs/API.md) · [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) ·
  history in [REFACTOR_NOTES.md](REFACTOR_NOTES.md).

---

Internal use only — rf IDEAS — Proprietary and Confidential
