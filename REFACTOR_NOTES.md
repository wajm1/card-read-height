# Refactor notes (`refactor/gui-declutter`)

Handoff for Phases 1–5 of the GUI declutter / modular split. **Documentation and
layout only for Phases 4–5** — no intentional motion, timing, pose, or CSV
behavior changes.

## Summary of files added / moved / deleted

### Phase 2 — declutter

| Action | Path |
|--------|------|
| **DELETED** | `gui/arm3d.py` (unused matplotlib FK skeleton; never load-bearing) |
| **MOVED** | `robot/move2.py` → `tools/experimental/move2.py` (quarantine) |
| **MOVED** | `robot/cardheight.py` → `tools/cardheight.py` |
| **MOVED** | `gui/ros2_bridge.py` → `tools/ros2/ros2_bridge.py` |
| **DEDUPED** | Duplicate `gui/lite6_*.{html,urdf}` beside `gui.py` — canonical only under `gui/viewer/` |
| **ADDED** | `tools/README.md`, `tools/ros2/README.txt` |
| **DELETED earlier** | `Automation/hwg/*` (HWG lives at workspace `files/hwg/`) |

### Phase 3 — GUI split

| Action | Path |
|--------|------|
| **ADDED** | `gui/constants.py` — brand, poses, joint-limit helpers, reader library |
| **ADDED** | `gui/widgets.py` — Tk helpers |
| **ADDED** | `gui/gui_robot.py` — `GuiRobot` cut from monolith |
| **ADDED** | `gui/app.py` — `App` + telemetry/stdout helpers |
| **THINNED** | `gui/gui.py` — entry only (`main` + `if __name__`) |
| **KEPT** | `gui/arm_gl.py`, `gui/robot_viewer.py`, `gui/viewer/` |

### Phase 4 — documentation

| Action | Path |
|--------|------|
| **REFRESHED** | Module/API docstrings across `Automation/**/*.py` |
| **REFRESHED** | Root `README.md`, `Automation/README.md`, `docs/*` |
| **UPDATED** | `requirements.txt` — commented optional Live-arm / HID lines |

### Phase 5 — this file + architecture status

| Action | Path |
|--------|------|
| **ADDED** | `REFACTOR_NOTES.md` (this document) |
| **UPDATED** | `ARCHITECTURE.md` — Phases 2–3 complete; points here |

## Final directory tree (Automation focus)

```
Automation/
├── config.py
├── requirements.txt
├── README.md
├── barcode/
│   └── scanner.py
├── gui/
│   ├── gui.py              # entry: python gui/gui.py
│   ├── app.py
│   ├── gui_robot.py
│   ├── constants.py
│   ├── widgets.py
│   ├── arm_gl.py
│   ├── robot_viewer.py
│   └── viewer/
│       ├── lite6.urdf
│       ├── lite6_viewer.html
│       └── meshes/visual/*.stl
├── reader/
│   ├── cli.py
│   ├── ReaderConfig.py
│   └── ReaderConfigSDK.py
├── robot/
│   ├── move.py
│   ├── cardreadheight.py
│   └── test_settings.py
└── tools/
    ├── README.md
    ├── cardheight.py
    ├── experimental/
    │   └── move2.py
    └── ros2/
        ├── README.txt
        └── ros2_bridge.py
```

Workspace (outside Automation): `files/AllCards.csv`, `files/card_readers.json`,
`files/hwg/*.hwg+`, `results/`.

## Entry path confirmation

- `gui/gui.py` still defines `main()` and `if __name__ == "__main__": main()`.
- `robot/cardreadheight.py --gui` still does `from gui.gui import main as gui_main`
  (verified by grep during Phase 5).

Primary operator launch:

```bash
cd Automation
python gui/gui.py
```

## Deliberately left alone

- **`robot/move.py` motion primitives** — timings, poses, pick/descend logic unchanged
  (docstrings only in Phase 4).
- **CSV formats / AllCards schema** — no format changes.
- **Poses and timings** in `config.py` / `gui/constants.py` — values untouched;
  docstrings/comments preserved.
- **`GuiRobot` method bodies** — cut-and-paste extraction; no behavior rewrite.
- **Parallel CLI `CardReadHeightTest`** — still a separate orchestrator from `GuiRobot`.
- **`tools/cardheight.py` hardcoded IP / TABLE_Z** — intentional isolation for commissioning.
- **`ReaderConfigSDK.py` runs on import** — no `if __name__` guard added (behavior preserved).
- **Pre-existing unused imports** flagged by pyflakes — left for a clean-up follow-up.

## Suggested follow-ups (behavior-change ideas deferred)

- Commit-clean unused imports reported by pyflakes.
- Unify or clearly share helpers between `GuiRobot` and `CardReadHeightTest`.
- Wrap `ReaderConfigSDK.py` CLI dispatch in `if __name__ == "__main__"`.
- Drop hardcoded IP in `tools/cardheight.py`; read `config.ROBOT_IP` / `TABLE_Z_MM`.
- Optional: richer fixture CAD in the browser workcell (current markers are boxes).
- Optional: idle joint polling when the arm is connected but a test is not running.

## Hybrid workcell view (post-refactor feature)

Done on this branch after Phase 5:

- Compact always-on-top Tk main panel; embedded OpenGL Live-arm panel removed from UI.
- Auto-open browser viewer (`robot_viewer` / `viewer/lite6_viewer.html`) with `/stations`
  (Drop, pick up, Reader, Flip from `constants` joint poses) and card mesh when
  `suction` is true on `/joints`.
- `GuiRobot._set_suction` mirrors vacuum state for the viewer without changing SDK call args.

## Doc discrepancies corrected

| Old (wrong) | Correct |
|-------------|---------|
| HWG under `Automation/hwg/` | **`files/hwg/`** via `config.PATHS["hwg"]` |
| GUI updates `robot/test_settings.py` live | GUI does **not** import it; CLI only |
| Monolithic `gui/gui.py` as sole GUI module | Split: `gui.py` + `app` / `gui_robot` / `constants` / `widgets` |
| `robot/tools/cardheight.py`, `gui/ros2_bridge.py`, `robot/move2.py` | Under **`tools/`** (`cardheight`, `ros2/`, `experimental/move2`) |
| Mesh path `visuals/` | **`viewer/meshes/visual/`** (singular) |
| Live arm described as matplotlib `Arm3DCanvas` | **`ArmGLViewer`** (`arm_gl.py`) |
| Project tree showing `Automation/hwg` / missing `tools/` | Trees in README / SETUP / Automation README match reality |

## Phase 5 verification

```
python -m compileall Automation
→ exit 0 (all modules listed; no errors)

python -m pyflakes Automation
→ exit 1 (pre-existing unused imports / unused local only):
  Automation\barcode\scanner.py:188:9: 'keyboard as _kb' imported but unused
  Automation\gui\arm_gl.py:105:13: 'numpy' imported but unused
  Automation\gui\arm_gl.py:106:13: 'OpenGL.GL' imported but unused
  Automation\gui\arm_gl.py:107:13: 'pyopengltk.OpenGLFrame' imported but unused
  Automation\gui\gui_robot.py:1419:17: local variable 'error_flag' is assigned to but never used
  Automation\reader\ReaderConfigSDK.py:27:1: 'io' imported but unused
  Automation\tools\cardheight.py:22:1: 'time' imported but unused

Entry paths:
  gui/gui.py — def main() + if __name__ == "__main__"
  cardreadheight.py — from gui.gui import main as gui_main (--gui)
```
