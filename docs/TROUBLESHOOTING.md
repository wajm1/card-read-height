# Troubleshooting

Common problems and fixes. Run commands from the `Automation/` directory.

## Installation

**`ModuleNotFoundError: No module named 'xarm'`**
Install dependencies: `pip install -r requirements.txt`. The robot SDK is
`xarm-python-sdk`.

**`ModuleNotFoundError: No module named 'keyboard'` / `'hid'`**
`keyboard` is required (barcode capture). `hid`/`hidapi` is only needed for
`reader/ReaderConfigSDK.py`: `pip install hid` (or `hidapi`).

**`ModuleNotFoundError: No module named 'config'`**
You're running from the wrong directory. Run scripts from `Automation/`
(e.g. `python robot/cardreadheight.py`), not from a subfolder.

## Robot (Lite 6 / xArm)

**Can't connect to the robot**

1. Confirm the arm is powered and on the network.
2. Check the IP: `ROBOT_IP` in `config.py`, or pass `--ip` to the runner.
3. Ping the arm from the control PC.
4. Make sure no other session (UFACTORY Studio, another script) holds the connection.

**Robot errors out or won't move**
Clear errors and re-home from UFACTORY Studio, then retry. The code calls
`clean_stop()` on shutdown; if a run was interrupted, power-cycle/clear before the next.

**Motion is in the wrong place**
The poses in `robot/move.py` (and mirrored in `robot/cardreadheight.py` /
`gui/gui.py`) are tuned to a specific fixture. If the fixture moved, the joint angles
(`PICK_ANGLE`, `BARCODE_SCAN_ANGLE`, `PLACE_*`, etc.) and `TABLE_Z_MM` need re-tuning.

## Reader (WAVE ID)

**`Could not connect to reader — check USB connection`** (from `ReaderConfigSDK.py`)

1. Confirm the reader is plugged in and enumerated.
2. Check `VENDOR_ID` / `PRODUCT_ID` in `config.py` match your reader.
3. Verify with `python reader/ReaderConfigSDK.py about`.

**RRMTool CLI not found**
The runner/GUI use the RRMTool CLI via `config.RRM_CLI`. If it isn't found, set the
`RRM_CLI` environment variable to the full path of `RRMTool_CLI.exe`, or edit
`_RRM_CLI_CANDIDATES` in `config.py`.

**Reader configures but the card won't read**

1. Confirm the card's HWG+ file exists in `Automation/hwg/` and its filename matches the
   **Name** column in `files/AllCards.csv` (e.g. `HID Prox UID (608x).hwg+`).
2. Try configuring directly: `python reader/ReaderConfigSDK.py set-card <type>`.
3. Check the read height isn't below the credential's range — see `READ_HEIGHT_SPEC_MM`
   in `config.py`.

## Barcode scanner

**Scans aren't detected**

1. The scanner must be in **keyboard-wedge** mode (test it in a text editor).
2. `barcode/scanner.py` uses the `keyboard` library — on Windows it may need to run as
   administrator.
3. Verify: `python -c "from barcode.scanner import check_barcode_scanner; print(check_barcode_scanner())"`

**`Barcode scan timed out or card not found`**
The barcode isn't in `files/AllCards.csv`, or the scan didn't arrive within the timeout.
Confirm the barcode value has a matching row, then rescan.

## GUI

**GUI won't launch**
Ensure Tkinter is available (`python -m tkinter` opens a test window) and run
`python gui/gui.py` from `Automation/`.

**Device checklist won't pass**
The checklist gates on robot, reader, and scanner. Use the reader/robot/barcode checks
above to find which one is failing before retrying.

## Quick diagnostics

```bash
cd Automation
python reader/ReaderConfigSDK.py about       # reader
python robot/cardreadheight.py --dry-run     # pipeline without the robot
python -c "import config; print('config OK')"
```
