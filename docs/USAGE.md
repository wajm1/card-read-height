# Usage

How to run read-height / tap-and-go tests, from the GUI or the command line.

> Run all commands from the **`Automation/`** directory. The entry-point scripts add the
> project root to `sys.path`, so `import config` and the package imports resolve correctly.

## GUI

```bash
cd Automation
python gui/gui.py
```

The GUI (`gui/gui.py` → `app.App` / `gui_robot.GuiRobot`):

- Runs a **device checklist** (robot, reader, barcode scanner) as a startup gate.
- Lets you choose **Read Height**, **Tap and Go**, or both (**Combined**), set card
  count, angles, flip, and descent preset, then **Run**.
- Streams live status/log output and shows each card's results as they complete.
- **Exports** / autosaves results to CSV in `results/`.
- Optional **Live arm** (OpenGL) and **browser mesh viewer** if assets/deps are present.

You can also open the GUI from the runner: `python robot/cardreadheight.py --gui`
(imports `gui.gui.main`).

## Command line

The main CLI entry point is `robot/cardreadheight.py` (parallel orchestrator to
`GuiRobot` — not driven by GUI presets):

```bash
cd Automation
python robot/cardreadheight.py [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--ip ADDR` | `config.ROBOT_IP` | xArm/Lite 6 IP address |
| `--cycles N` | `config.CARD_STACK_COUNT` (14) | Number of cards to test |
| `--scans N` | `1` | Slow measured scans per card (for averaging) |
| `--dry-run` | off | Validate the CSV/results pipeline **without** the robot |
| `--reader-config` | off | With `--dry-run`, also load the A001 HWG to the reader |
| `--gui` | off | Open the live control GUI instead of running headless |

Examples:

```bash
# Standard 14-card run
python robot/cardreadheight.py

# 5 cards, 3 averaged scans each, against a specific robot
python robot/cardreadheight.py --cycles 5 --scans 3 --ip 192.168.1.177

# No robot — just confirm the reader/CSV path works
python robot/cardreadheight.py --dry-run --reader-config
```

CLI descent parameters live in `robot/test_settings.py` (`TestSettings`). The GUI
does **not** import that module.

## Reader-only tools

Configure the reader without the robot or GUI.

**Scan-and-configure loop** — scan a card, the reader is configured, repeat
(Ctrl+C to quit):

```bash
python reader/ReaderConfig.py
```

**Direct USB HID tool:**

```bash
python reader/ReaderConfigSDK.py about          # reader info
python reader/ReaderConfigSDK.py read           # read current config
python reader/ReaderConfigSDK.py set-cepas      # configure for CEPAS
python reader/ReaderConfigSDK.py set-card TYPE   # configure for a named card type
python reader/ReaderConfigSDK.py beep [count]    # beep the reader
```

## Optional tools

```bash
python tools/cardheight.py                 # interactive Z jogger (commissioning)
python tools/experimental/move2.py         # reverse characteriser (dev-only)
# In a ROS2 env (not the GUI Python):
python tools/ros2/ros2_bridge.py --udp-port 9870
```

## Output

Results are written to **`results/`** (the repository-root `results/` folder) as
timestamped CSVs. Curated results you want to keep in version control go in
**`results/Keep/`** (everything else in `results/` is git-ignored).

HWG loads come from **`files/hwg/`**.

## How a test run works (read-height)

1. **Pick** — robot grips a card from the stack (`smart_pick`).
2. **Scan** — it lifts and moves toward the scanner while listening for a barcode.
3. **Identify** — the barcode is matched in `files/AllCards.csv`; the matching HWG+
   under `files/hwg/` is loaded to the reader.
4. **Measure** — GUI: multi-angle zone-in and/or tap-and-go; CLI: descend until read
   or hit the `READ_HEIGHT_MIN_MM` floor (a failure).
5. **Record** — results are appended to the results CSV (GUI may update AllCards averages).
