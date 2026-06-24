# Usage

How to run read-height tests, from the GUI or the command line.

> Run all commands from the **`Automation/`** directory. The entry-point scripts add the
> project root to `sys.path`, so `import config` and the package imports resolve correctly.

## GUI

```bash
cd Automation
python gui/gui.py
```

The GUI (`gui/gui.py`):

- Runs a **device checklist** (robot, reader, barcode scanner) as a startup gate.
- Lets you set card count, scans-per-card, and descent speed, then **Run**.
- Streams live status/log output and shows each card's read height as it completes.
- **Exports** results to a CSV in `results/`.

You can also open the GUI from the runner: `python robot/cardreadheight.py --gui`.

## Command line

The main entry point is `robot/cardreadheight.py`:

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

## Output

Results are written to **`results/`** (the repository-root `results/` folder) as
timestamped CSVs, e.g. `2026-06-23_15-59-05_RDR-800x1BxU_read_heights.csv`. Each row
captures timestamp, reader model, card name, barcode, side, and the measured read
height. Curated results you want to keep in version control go in **`results/Keep/`**
(everything else in `results/` is git-ignored).

## How a test run works

1. **Pick** — robot grips a card from the stack (`smart_pick`).
2. **Scan** — it lifts and moves toward the scanner while listening for a barcode.
3. **Identify** — the barcode is matched in `files/AllCards.csv`; the matching HWG+ file
   is loaded to the reader.
4. **Descend** — the robot lowers the card toward the reader side (A or B) in small
   steps until a read is detected, or it hits the `READ_HEIGHT_MIN_MM` floor (a failure).
5. **Record** — the read height is appended to the results CSV.
