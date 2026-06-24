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

## What the system does

1. The **Lite 6 robot arm** picks a card from a stack.
2. While moving to the scanner, it listens for a **barcode** to identify the card.
3. It looks the barcode up in `files/AllCards.csv` to get the card type, then loads the
   matching **HWG+ file** from `Automation/hwg/` to configure the reader.
4. It lowers the card toward the **reader**, stepping down until a read is detected.
5. It records the **read height** (the highest point at which the card still reads) to a
   CSV in `results/`.

## Hardware

- **UFACTORY Lite 6** robot arm — connected over the network (`ROBOT_IP` in `config.py`).
- **rf IDEAS WAVE ID reader** — configured via the RRMTool CLI and/or direct USB HID.
- **USB barcode scanner** — acts as a keyboard; captured by `barcode/scanner.py`.

## Software components

| Component | File | Role |
|-----------|------|------|
| Settings | `Automation/config.py` | All paths, robot IP, test parameters, card map |
| Test runner | `Automation/robot/cardreadheight.py` | Main command-line entry point |
| GUI | `Automation/gui/gui.py` | Tkinter control + live monitoring |
| Robot motion | `Automation/robot/move.py` | `RobotMain` — pick, move, descend-until-read |
| Reader (CLI) | `Automation/reader/cli.py` | RRMTool CLI helpers used by the runner/GUI |
| Reader (HID) | `Automation/reader/ReaderConfigSDK.py` | Direct USB HID reader tool |
| Reader (loop) | `Automation/reader/ReaderConfig.py` | Scan-and-configure loop (no robot) |
| Barcode | `Automation/barcode/scanner.py` | Scan capture + card lookup |

## Version

- System: Credential Read Height Automation (Lite 6 / WAVE ID)
- Python: 3.10+ (uses `int | None` style type hints)
- Internal use only — rf IDEAS
