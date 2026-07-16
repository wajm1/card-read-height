# Architecture inventory (Phase 1)

**Branch:** `refactor/gui-declutter`  
**Scope:** read-only inventory of the working tree as of this document.  
**Rule:** no deletions or moves until the deletion list below is explicitly approved.

This document maps every Python module under `Automation/`, what imports what, which paths operators actually run, and what looks dead vs load-bearing.

---

## 1. System purpose (operator view)

Credential **read-height** and **tap-and-go** testing for rf IDEAS WAVE ID readers using a **UFACTORY Lite 6** arm, a USB keyboard-wedge barcode scanner, and RRMTool CLI (HWG+) configuration.

Typical flow:

1. Arm picks a card from the stack.
2. Barcode identifies the card → HWG configures the reader.
3. Arm presents the card at selected wrist angles and measures read height (and/or tap-and-go timing).
4. Results land in `results/` CSV; baselines can update `files/AllCards.csv`.

**Workspace root** = parent of `Automation/`. `config.py` resolves `files/`, `results/`, and logs relative to that root. Do not move those folders without updating path logic.

---

## 2. Directory map (current)

```
card-read-height/
├── README.md, docs/          ← operator docs (SETUP / USAGE / API / TROUBLESHOOTING)
├── files/                    ← AllCards.csv, card_readers.json, hwg/*.hwg+
├── results/                  ← test CSVs (Keep/ curated)
└── Automation/               ← all runnable Python (cwd for scripts)
    ├── config.py             ← central settings + path helpers
    ├── requirements.txt
    ├── barcode/scanner.py
    ├── reader/
    │   ├── cli.py            ← RRMTool wrappers (used by robot + GUI)
    │   ├── ReaderConfig.py   ← barcode→HWG only (no robot)
    │   └── ReaderConfigSDK.py← USB HID SDK CLI (no RRMTool)
    ├── robot/
    │   ├── move.py           ← RobotMain core motion library
    │   ├── move2.py          ← experimental reverse characteriser
    │   ├── cardreadheight.py ← primary CLI test runner
    │   ├── cardheight.py     ← interactive Z jogger (commissioning)
    │   └── test_settings.py  ← CLI-tunable params object
    └── gui/
        ├── gui.py            ← primary Tk GUI (~3859 lines)
        ├── arm_gl.py         ← embedded OpenGL STL viewer (USED)
        ├── arm3d.py          ← matplotlib FK skeleton (IMPORTED, UNUSED)
        ├── robot_viewer.py   ← browser three.js mesh server
        ├── ros2_bridge.py    ← optional UDP→ROS2 process
        ├── lite6.urdf, lite6_viewer.html   ← also copied under viewer/
        └── viewer/meshes/visual/*.stl      ← required for Live arm / browser view
```

No `.py` files exist at the repo root.

---

## 3. Entry points

| Script | Documented? | Role |
|--------|-------------|------|
| `python gui/gui.py` | Yes (primary) | Tk app: checklist → test select → run → CSV |
| `python robot/cardreadheight.py …` | Yes (primary CLI) | CLI orchestration; `--gui` delegates to `gui.gui.main` |
| `python reader/ReaderConfig.py` | Yes | Barcode → configure reader only |
| `python reader/ReaderConfigSDK.py …` | Yes | HID about/read/set/beep (runs on load; no `__main__` guard) |
| `python robot/move.py` | Library / API only | Has `__main__` but not in operator Run sections |
| `python robot/move2.py` | **No** | Experimental reverse characteriser |
| `python robot/cardheight.py` | Mentioned as helper | Interactive Z jog; runs on import |
| `python gui/ros2_bridge.py` | Docstring only | Separate ROS2 env; receives GUI UDP |

Preserve signatures and these entry paths through the refactor.

---

## 4. Dependency graph (project-local)

```
                    ┌──────────── config.py ────────────┐
                    │                                   │
                    ▼                                   ▼
           barcode/scanner.py                    reader/cli.py
                    │                                   │
         ┌──────────┴──────────┐                        │
         ▼                     ▼                        ▼
   robot/move.py ◄──── robot/cardreadheight.py ◄── test_settings.py
         │                     │
         │                     └──(--gui)──► gui/gui.py
         │                                      │
         │                      ┌───────────────┼───────────────┐
         │                      ▼               ▼               ▼
         │                 arm_gl.py      robot_viewer.py   (UDP only)
         │                 [USED]         [optional]        ros2_bridge.py
         │                 arm3d.py                         [separate process]
         │                 [imported, unused]
         │
         └── subclasses ──► gui.GuiRobot
                         └── move2.ReadHeightCharacteriser  [nothing imports move2]

reader/ReaderConfig.py  → scanner + cli   (standalone)
reader/ReaderConfigSDK.py → config only   (standalone; no in-repo importers)
robot/cardheight.py     → XArmAPI only    (standalone; no in-repo importers)
```

### Runtime path from `gui.py` (load-bearing)

Hard imports (GUI will not start without them):

- `config`
- `xarm.wrapper.XArmAPI`
- `robot.move.RobotMain` (+ optional `CardReadListener`)
- `barcode.scanner` (listener, lookup, AllCards helpers)
- `reader.cli` (check / configure / info)

Optional try/except imports:

| Module | Used at runtime? |
|--------|------------------|
| `arm_gl` | **Yes** — Live arm panel (`ArmGLViewer`) |
| `robot_viewer` | **Yes** — “OPEN 3D MESH VIEW (browser)” |
| `arm3d` | **No** — imported; UI builds `ArmGLViewer` into `self._arm3d` |

`ros2_bridge` is never imported; GUI only sends UDP to `ROS_BRIDGE_HOST`/`ROS_BRIDGE_PORT`.

`robot.test_settings` is **not** imported by the GUI (docs that say GUI sliders update it are stale).

---

## 5. Per-module inventory

| File | ~Lines | Role | Imported by |
|------|--------|------|-------------|
| `config.py` | 224 | Paths, robot IP, speeds, poses, CARD_TYPE_MAP, height math | Nearly everything |
| `barcode/scanner.py` | 913 | Keyboard-wedge barcode + AllCards.csv lookup/baselines | move, move2, cardreadheight, gui, ReaderConfig |
| `reader/cli.py` | 159 | RRMTool_CLI subprocess helpers | move, move2, cardreadheight, gui, ReaderConfig |
| `reader/ReaderConfig.py` | 51 | Barcode→HWG loop (no robot) | — (entry only) |
| `reader/ReaderConfigSDK.py` | 396 | USB HID reader tool | — (entry only) |
| `robot/move.py` | 563 | **Core:** `RobotMain`, `CardReadListener`, `DescentResult` | gui, cardreadheight, move2 |
| `robot/move2.py` | 363 | Reverse walk+bisect characteriser | — |
| `robot/cardreadheight.py` | 704 | CLI test runner (`CardReadHeightTest`) | — (entry; `--gui` → gui) |
| `robot/cardheight.py` | 89 | Interactive Z height jogger | — |
| `robot/test_settings.py` | 21 | Mutable descent params for CLI | cardreadheight only |
| `gui/gui.py` | ~3859 | Tk UI + `GuiRobot` orchestration | cardreadheight (`--gui`) |
| `gui/arm_gl.py` | 269 | Embedded OpenGL STL viewer | gui (optional) |
| `gui/arm3d.py` | 213 | Matplotlib FK skeleton | gui import only; unused |
| `gui/robot_viewer.py` | 136 | Local HTTP three.js viewer | gui (optional) |
| `gui/ros2_bridge.py` | 124 | UDP → ROS2 JointState | — (separate process) |

### Pair notes

- **`move.py` vs `move2.py`:** `move.py` is the production motion library. `move2.py` subclasses it for an alternate reverse-characterisation strategy; not referenced by GUI/CLI docs.
- **`arm_gl.py` vs `arm3d.py`:** Live panel uses OpenGL meshes (`arm_gl`). `arm3d` is leftover; attribute name `_arm3d` on `App` now holds an `ArmGLViewer`.
- **`cardreadheight.py` vs `cardheight.py`:** Former is the full CLI test. Latter is a tiny commissioning jogger with hardcoded IP / table Z (does not use `config.py`).
- **`GuiRobot` vs `CardReadHeightTest`:** Two parallel orchestrators on top of `RobotMain` (GUI vs CLI). Not duplicate files; both load-bearing for their entry paths.

---

## 6. `gui.py` — top-level symbols

| Symbol | Purpose |
|--------|---------|
| `_TelemetryUDP` | Fire-and-forget JSON/UDP joint + result packets for optional ROS bridge |
| `nearest_j6_in_range` | Wrap J6 ±360° to keep wrist near a reference within joint limits |
| `joint_limit_issues` | Human-readable Lite 6 joint-limit diagnostics |
| `_csv_row` | Normalize cells for CSV writing |
| `_parse_saved_avg` | Parse a saved average height string to float |
| `load_reader_library` | Load `files/card_readers.json` reader heights |
| `_reader_height_for` | Look up one reader model’s height |
| `_default_reader_model` | Default reader name from library |
| `GuiRobot` | GUI subclass of `RobotMain`: multi-angle zone-in, flip, tap-and-go, combined, telemetry |
| `flat_button` | Styled Tk button helper |
| `section_label` | Section header label helper |
| `dot` | Status color dot widget |
| `number_stepper` | ± stepper for Int/DoubleVars |
| `App` | Full Tk application (screens, run control, calibrator, viewers) |
| `_StdoutToQueue` | Redirect stdout lines into the activity log queue |
| `main` | `Tk()` + `App` + `mainloop` |

### Natural seams inside `gui.py` (for Phase 3 split)

1. **Constants / brand / joint limits / CSV headers / reader library** (~L113–447)
2. **`GuiRobot`** — motion + test loops (~L453–2080)
3. **Widget helpers** (~L2082–2145)
4. **`App` UI** — checklist, test select, main panel, results (~L2147–3390)
5. **Reader calibrator** (~L3392–3726)
6. **ROS2 telemetry + mesh viewer wiring** (~L3728–3830)
7. **`_StdoutToQueue` + `main`** (~L3833–end)

### `GuiRobot` method groups

- Fault / init / presets: `diagnose_fault`, `init_gui`, `apply_preset`
- Floors / staging geometry: `_staging_pose_for_angle`, `_reader_floor_*`, `_max_drop_to_floor`
- Barcode / side: `_scan_barcode_and_config`, `_resolve_card_side`
- Motion helpers: `_move_joint`, `_move_to_height_*`, `_clear_reader_*`, `_release_card`, `_flip_card`
- Zone-in measurement: `_zone_*`, `_fast_locate_read`, `_slow_measure_read`, `_measure_orientation`
- Runners: `run`, `run_tap_and_go`, `run_combined`
- Telemetry / abort: `start_telemetry`, `request_abort`

### `App` method groups

- Screens: `show_checklist`, `show_test_select`, `show_main`, `show_calibrator`
- Device checks: `_check_robot`, `_check_reader_dev`, `_check_barcode`
- Run control: `_on_start`, `_run_worker`, `_on_stop`, `_poll`, CSV autosave/export
- Calibrator: `_calib_*`
- Viewers: `_open_mesh_viewer`, `_feed_telemetry`, `_on_telem_toggle`, `_on_close`

Launch:

```python
def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
```

Also reachable via `python robot/cardreadheight.py --gui` → `from gui.gui import main`.

---

## 7. Fixed paths the app must keep working

| Path | Used for |
|------|----------|
| `Automation/config.py` | All settings |
| `files/AllCards.csv` | Barcode → card / baselines |
| `files/hwg/*.hwg+` | Reader config loads |
| `files/card_readers.json` | Reader model heights (GUI) |
| `results/` | Output CSVs |
| `Automation/gui/viewer/meshes/visual/*.stl` | Live arm + browser viewer |
| `Automation/gui/viewer/{lite6_viewer.html,lite6.urdf}` | Browser viewer assets |

Duplicates today: `lite6_viewer.html` / `lite6.urdf` also sit beside `gui.py`. Browser path expects them under `viewer/`.

---

## 8. Deletion / quarantine candidates (NEED YOUR SIGN-OFF)

**Do not delete until confirmed.** When unsure, treat as load-bearing.

| Item | Evidence | Proposed action | Risk if wrong |
|------|----------|-----------------|---------------|
| `gui/arm3d.py` | try-imported; never referenced after import; Live arm uses `arm_gl` | **Delete** (or move to `tools/legacy/`) | None for current GUI path; lose matplotlib fallback skeleton |
| `robot/move2.py` | Nothing imports it; undocumented entry | **Quarantine** to `tools/experimental/` or delete | Lose reverse-characteriser script |
| `robot/cardheight.py` | Nothing imports it; documented as helper; hardcoded IP | **Keep** as `tools/` or ask — used during table-Z commissioning? | Lose interactive Z jogger |
| `gui/ros2_bridge.py` | Not imported; optional UDP consumer | **Keep**, relocate under `tools/ros2/` | Breaks ROS telemetry workflow if moved without docs |
| Duplicate `gui/lite6_*.{html,urdf}` (beside gui.py) | Canonical copies under `viewer/` | After sign-off, remove duplicates if viewer copies are complete | Browser view if viewer/ incomplete |
| Stale `__pycache__/viewer/meshes/visuals/` | Wrong path leftover | Safe to ignore/delete (bytecode cache) | None |

### Explicitly **not** candidates for deletion

- `move.py`, `cardreadheight.py`, `gui.py`, `scanner.py`, `cli.py`, `config.py`
- `arm_gl.py`, `robot_viewer.py`, `viewer/meshes/`
- `ReaderConfig.py`, `ReaderConfigSDK.py` (documented operator tools)
- `test_settings.py` (CLI path)

---

## 9. Stale documentation vs code (note only; fix in Phase 4)

- API / Automation README imply GUI updates `test_settings.py` live — **GUI does not import it**.
- Comments in `gui.py` still say “Arm3DCanvas” / matplotlib for the Live arm — actually `ArmGLViewer`.
- Mesh path must be `viewer/meshes/visual/` (singular); a prior mis-copy used `__pycache__/…/visuals/`.

---

## 10. Proposed Phase 2 target layout (proposal only — no moves yet)

Something in this family, after deletion sign-off:

```
Automation/
  config.py                 # stays (or thin re-export at top level later)
  gui/
    gui.py                  # thin entry → App wiring
    app.py / widgets.py / … # Phase 3 extractions
    arm_gl.py
    viewer/                 # meshes + html + urdf
  robot/                    # core motion + CLI runner
  barcode/
  reader/
  tools/                    # optional / experimental / ROS / commissioning
    ros2_bridge.py
    move2.py?               # if kept
    cardheight.py?          # if kept
    arm3d.py?               # if kept as legacy
```

Exact tree will be proposed again in Phase 2 after your deletion decisions.

---

## 11. Phase 1 wait state

**Stopped here per instructions.** Next step needs your confirmation on the deletion list in §8:

1. Delete `arm3d.py`? (Y/N / quarantine)
2. Delete or quarantine `move2.py`?
3. Keep / move / delete `cardheight.py`?
4. Keep `ros2_bridge.py` under `tools/ros2/`?
5. Remove duplicate `lite6_*` beside `gui.py` once `viewer/` copies verified?

After sign-off → Phase 2 (declutter tree, small commits, compile + pyflakes each step).
