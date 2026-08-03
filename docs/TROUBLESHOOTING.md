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

**C23 / joint angle exceeds limit**
Usually a wrist (J6) wrap past ±360°. The GUI uses `nearest_j6_in_range` (in
`gui/constants.py`) to pick a physically identical J6 revolution that stays inside
limits and close to the current wrist. Drop/release paths also recenter toward
`DROP_ANGLE` so Cartesian moves do not wind the wrist out of range. If C23 still
fires, check the activity log for `diagnose_fault` output naming which joint is at limit.

**Pick fail**
`smart_pick` search-descends at the pick pose until suction engages. Confirm the
card stack height, suction cup, and `PICK_ANGLE` / pick-search limits in `config.py`.
Clear any prior suction-off state and retry from a known-good home.

**Motion is in the wrong place**
Poses in `robot/move.py` and GUI constants (`READER_STAGING_0_ANGLE`, `PICK_ANGLE`,
`DROP_ANGLE`, etc.) are tuned to a specific fixture. If the fixture moved, re-tune
those joint angles and `TABLE_Z_MM`.

## Reader (WAVE ID)

**`Could not connect to reader — check USB connection`** (from `ReaderConfigSDK.py`)

1. Confirm the reader is plugged in and enumerated.
2. Check `VENDOR_ID` / `PRODUCT_ID` in `config.py` match your reader.
3. Verify with `python reader/ReaderConfigSDK.py about`.

**RRMTool CLI / RRM_CLI missing**
The runner/GUI use the RRMTool CLI via `config.RRM_CLI`. If it isn't found, set the
`RRM_CLI` environment variable to the full path of `RRMTool_CLI.exe`, or edit
`_RRM_CLI_CANDIDATES` in `config.py`. Checklist and `reader.cli.check_reader()` will
fail until this path is valid.

**Reader configures but the card won't read**

1. Confirm the card's HWG+ file exists in **`files/hwg/`** (not `Automation/hwg/`)
   and its filename matches the **Name** column in `files/AllCards.csv`
   (e.g. `HID Prox UID (608x).hwg+`).
2. Try configuring directly: `python reader/ReaderConfigSDK.py set-card <type>`.
3. Check the read height isn't below the credential's range — see `READ_HEIGHT_SPEC_MM`
   in `config.py`.

## Barcode scanner

**Scans aren't detected**

1. The scanner must be in **keyboard-wedge** mode (test it in a text editor).
2. `barcode/scanner.py` uses the `keyboard` library — on Windows it may need to run as
   administrator.
3. Verify: `python -c "from barcode.scanner import check_barcode_scanner; print(check_barcode_scanner())"`

**Barcode fail / timeout / not in AllCards**
The barcode isn't in `files/AllCards.csv`, the scan didn't arrive within the timeout,
or the wedge burst was missed. Confirm the barcode value has a matching row, ensure
the scanner isn't fighting a focused GUI text field, then rescan.

## GUI / Live arm / meshes

**GUI won't launch**
Ensure Tkinter is available (`python -m tkinter` opens a test window) and run
`python gui/gui.py` from `Automation/`.

**Device checklist won't pass**
The checklist gates on robot, reader, and scanner. Use the reader/robot/barcode checks
above to find which one is failing before retrying.

**Live arm needs pyopengltk**
The embedded Live arm panel requires `pyopengltk`, `PyOpenGL`, and `numpy`. Without
them the panel shows an install hint; the rest of the GUI still runs.
`pip install pyopengltk PyOpenGL numpy`.

**Mesh files not found**
Meshes must be under `Automation/gui/viewer/meshes/visual/` (singular **`visual`**,
not `visuals`). Wrong path or a leftover copy under `__pycache__/…/visuals/` will
make Live arm / browser viewer fail while the test run itself still works.

**HWG path**
Always `files/hwg/`. Older docs incorrectly said `Automation/hwg/` — that folder is
gone; `config.get_hwg_path()` resolves under the workspace `files/hwg/` directory.

## Quick diagnostics

```bash
cd Automation
python reader/ReaderConfigSDK.py about       # reader (needs hid)
python robot/cardreadheight.py --dry-run     # pipeline without the robot
python -c "import config; print(config.PATHS['hwg']); print('config OK')"
```

## Doc discrepancies corrected (Phase 4)

- HWG directory documented as `files/hwg/` (was wrongly `Automation/hwg/`).
- Project tree matches post-refactor layout (`gui/` split modules, `tools/`, no
  `robot/tools/cardheight`).
- GUI does **not** drive `robot/test_settings.py` (CLI-only).
