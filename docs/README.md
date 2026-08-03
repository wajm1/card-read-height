# Documentation Index

Documentation for the rf IDEAS **Credential Read Height Automation** system.

| Doc | Read it when |
|-----|--------------|
| [SETUP.md](SETUP.md) | Installing and configuring for the first time |
| [USAGE.md](USAGE.md) | Running tests (GUI or command line) |
| [API.md](API.md) | Writing custom scripts against the modules |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Something isn't working |

The top-level [../README.md](../README.md) has the high-level overview and repository
layout. [../Automation/README.md](../Automation/README.md) is a one-page quick reference.
Refactor history: [../REFACTOR_NOTES.md](../REFACTOR_NOTES.md).

## What the system does

1. The **Lite 6 robot arm** picks a card from a stack.
2. While moving to the scanner, it listens for a **barcode** to identify the card.
3. It looks the barcode up in `files/AllCards.csv` to get the card type, then loads the
   matching **HWG+ file** from **`files/hwg/`** to configure the reader.
4. It presents the card for **Read Height** (multi-angle zone-in) and/or **Tap-and-Go**
   timing (GUI modes; CLI runner is read-height oriented).
5. It records results to a CSV in `results/` (baselines may update `files/AllCards.csv`).

## Hardware

- **UFACTORY Lite 6** robot arm — connected over the network (`ROBOT_IP` in `config.py`).
- **rf IDEAS WAVE ID reader** — configured via the RRMTool CLI and/or direct USB HID.
- **USB barcode scanner** — acts as a keyboard; captured by `barcode/scanner.py`.

## Software components

| Component | File | Role |
|-----------|------|------|
| Settings | `Automation/config.py` | All paths, robot IP, test parameters, card map |
| Test runner (CLI) | `Automation/robot/cardreadheight.py` | Headless entry; `--gui` → GUI |
| GUI entry | `Automation/gui/gui.py` | Thin launcher → `app.App` |
| GUI app / robot | `gui/app.py`, `gui/gui_robot.py` | Screens + GuiRobot orchestration |
| Robot motion | `Automation/robot/move.py` | `RobotMain` — pick, move, descend-until-read |
| Reader (CLI) | `Automation/reader/cli.py` | RRMTool CLI helpers used by the runner/GUI |
| Reader (HID) | `Automation/reader/ReaderConfigSDK.py` | Direct USB HID reader tool |
| Reader (loop) | `Automation/reader/ReaderConfig.py` | Scan-and-configure loop (no robot) |
| Barcode | `Automation/barcode/scanner.py` | Scan capture + card lookup |
| Optional tools | `Automation/tools/` | cardheight, move2, ros2_bridge |

## Version

- System: Credential Read Height Automation (Lite 6 / WAVE ID)
- Python: 3.10+ (uses `int | None` style type hints; GUI often run on 3.14)
- Internal use only — rf IDEAS
