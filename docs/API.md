# API / Module Reference

Developer reference for scripting against the automation modules. Import paths assume the
project root (`Automation/`) is on `sys.path` — the entry-point scripts handle this, and
standalone scripts can replicate it:

```python
import os, sys
sys.path.insert(0, "/path/to/card-read-height/Automation")
```

Do not invent APIs beyond what these modules export today.

## `config`

Central configuration and path helpers.

```python
import config

config.ROBOT_IP                 # Lite 6 IP address
config.RRM_CLI                  # resolved RRMTool CLI path
config.VENDOR_ID, config.PRODUCT_ID   # USB HID reader identity
config.CARD_STACK_COUNT         # cards per run
config.CARD_TYPE_MAP            # barcode-prefix → card info (CEPAS test path)
config.PATHS                    # {"hwg","logs","results","files"} absolute paths
config.CSV_FIELDS               # result CSV column names (legacy / CLI-oriented)

config.get_hwg_path("CEPAS.hwg+")   # -> <workspace>/files/hwg/CEPAS.hwg+
config.get_results_path("x.csv")    # -> <workspace>/results/x.csv
config.ensure_paths_exist()         # create all PATHS dirs if missing
```

Key tunables (test defaults): `DEFAULT_START_HEIGHT_MM`, `DEFAULT_STEP_SIZE_MM`,
`READ_HEIGHT_MIN_MM`, `READ_HEIGHT_DWELL_S`, `READ_HEIGHT_SETTLE_S`, descent/approach
speeds and accelerations, and `TABLE_Z_MM`.

## `barcode.scanner`

```python
from barcode.scanner import BarcodeListener, lookup_card, check_barcode_scanner

ok, msg = check_barcode_scanner()        # (bool, message)

card = lookup_card("A001")               # look up by barcode in files/AllCards.csv
# -> {"name", "title", "hwg", "barcode", "side", "part_number", ...} or None

listener = BarcodeListener(on_barcode=lambda code: ...)
listener.start()                         # capture scans (keyboard-wedge)
listener.stop()
```

`lookup_card` resolves the card **Name** to an HWG+ file of the same name in
**`files/hwg/`**. CSV column names are matched flexibly (e.g. `Barcode`/`Code`/`ID`,
`Name`/`Card`/`Type`, `Side`). Baseline helpers (`update_all_cards_averages`,
`scrub_poisoned_card_baselines`, …) may rewrite `files/AllCards.csv`.

## `reader.cli`

RRMTool CLI helpers used by the runner and GUI.

```python
from reader.cli import (
    check_reader, get_reader_info, configure_reader_for_card,
    verify_reader_config_fast, get_reader_active_card_types,
)

ok, msg = check_reader()                 # reader present?
info = get_reader_info()                 # dict of reader details
ok = configure_reader_for_card(card, log_fn=print, verify=True)
ok, msg = verify_reader_config_fast(hwg_path)
```

## `reader.ReaderConfigSDK`

Direct USB HID reader control. Run as a CLI (`python reader/ReaderConfigSDK.py about`),
or import the `Reader` class:

```python
from reader.ReaderConfigSDK import Reader

reader = Reader()
if reader.open():
    ...        # about / read / set-cepas / set-card / beep
    reader.close()
```

Requires the `hid` library and a reader matching `VENDOR_ID`/`PRODUCT_ID` in `config.py`.
Note: the module currently dispatches CLI args on import (no `if __name__` guard).

## `reader.ReaderConfig`

A standalone scan-and-configure loop (no robot, no GUI): each scanned barcode is looked
up and the reader is configured for it. Run with `python reader/ReaderConfig.py`.

## `robot.move`

The working motion logic. `RobotMain` wraps the xArm SDK.

```python
from xarm.wrapper import XArmAPI
from robot.move import RobotMain

arm = XArmAPI("192.168.1.177", baud_checkset=False)
robot = RobotMain(arm)
robot.run()                  # full pick → scan → configure → descend sequence
```

Notable methods: `smart_pick()`, `_descend_until_read(max_drop, step, speed)`,
`_scan_barcode_and_config(timeout)`, `clean_stop()`, `is_alive()`.

## `robot.test_settings`

`TestSettings` holds CLI-tunable descent parameters for `cardreadheight.py`
(start height, step, min height, dwell, settle, descent/approach speeds).
Initialized from `config` defaults.

**The Tk GUI does not import this module.** GUI descent uses
`constants.DESCENT_PRESETS` / `GuiRobot.apply_preset`.

## `robot.cardreadheight`

The main CLI test runner. `CardReadHeightTest` orchestrates a full run and writes results;
`main()` parses CLI args (see [USAGE.md](USAGE.md)) and supports `--gui` and `--dry-run`.
`--gui` does `from gui.gui import main`.

## `gui` package

| Module | Role |
|--------|------|
| `gui.gui` | Entry: `main()` → `tk.Tk` + `app.App` |
| `gui.app` | `App` — checklist, test select, run panel, calibrator, CSV |
| `gui.gui_robot` | `GuiRobot(RobotMain)` — multi-angle / tap-and-go / combined |
| `gui.constants` | Brand, poses, `nearest_j6_in_range`, reader library loaders |
| `gui.widgets` | `flat_button`, `section_label`, `dot`, `number_stepper` |
| `gui.arm_gl` | Optional `ArmGLViewer` (needs pyopengltk / PyOpenGL / numpy) |
| `gui.robot_viewer` | Optional `RobotViewerServer` (stdlib HTTP + three.js) |

```python
from gui.gui import main
main()
```

Meshes for Live arm / browser view: `Automation/gui/viewer/meshes/visual/*.stl`.

## Optional `tools/`

| Script | Role |
|--------|------|
| `tools/cardheight.py` | Interactive Z jogger (hardcoded IP; not used by GUI/CLI) |
| `tools/experimental/move2.py` | Reverse walk+bisect characteriser |
| `tools/ros2/ros2_bridge.py` | UDP telemetry → ROS2 JointState (separate ROS2 Python) |
