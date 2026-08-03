<!-- Author: Wajahat Mahmood | Updated: 2026-07-30 | rf IDEAS — Proprietary and Confidential -->

# Decision Log — Cleanup, Features & Docs (2026-07-30)

**Author:** Wajahat Mahmood
**Branch:** `refactor/cleanup-features-docs`
**Baseline:** branched from `main` (Bitbucket `robot-project-6/card-read-height`)

This log records what changed, why, how it was verified, and the exact Git/
Bitbucket commit plan to land it. It follows the phased, behavior-preserving
approach: **external behavior stays identical** except for the three explicitly
requested feature changes.

rf IDEAS — Proprietary and Confidential

---

## A. Summary of changes

| # | Type | What | Files |
|---|------|------|-------|
| 1 | `fix` | **Calibration arrow keys corrected** — Left/Right (and the on-screen ◀/▶ buttons) were inverted; now ← moves left, → moves right. Up/Down and W/S unchanged. | `Automation/gui/app.py` |
| 2 | `feat` | **Calibration persists across GUI restarts.** New store saves MARK READER TOP (height, floor, staging pose) to `files/calibration.json` per reader model; loaded on launch and on reader-change; recalibrating overwrites. | `Automation/persistence/calibration_store.py` (new), `Automation/gui/app.py` |
| 3 | `fix` | **Comment field is typable again.** The barcode wedge's global keyboard hook could swallow typed keys due to a focus-tracking race. Now the "operator is typing" state tracks the focused widget (and reacts to a click), so keys always pass through. | `Automation/barcode/scanner.py` |
| 4 | `refactor` | **Decouple I/O from logic.** `keyboard` (scanner) and `msvcrt` (move) are now imported lazily, so pure lookup/motion logic imports with no hardware/OS deps — which is what makes headless tests possible. Behavior on Windows is unchanged. | `Automation/barcode/scanner.py`, `Automation/robot/move.py` |
| 5 | `test` | **Headless safety net (60 tests).** `FakeArm` records SDK calls; `xarm`/`msvcrt` stubbed. Characterizes geometry, staging poses, CSV row math for all 3 tests, barcode/lookup, HWG editing, calibration persistence; plus a compile-all smoke gate. | `Automation/tests/*`, `Automation/pytest.ini`, `Automation/requirements-dev.txt` (new) |
| 6 | `docs` | **Author/date header** added to the top of every module. | 21 `.py` files |
| 7 | `docs` | **User manual, architecture reference, structure diagram, this log.** | `docs/USER_MANUAL.md`, `docs/ARCHITECTURE.md`, `docs/architecture_diagram.svg`, `DECISION_LOG.md`, `README.md` |
| 8 | `fix` | **RRMTool_CLI is located robustly** — resolve from `RRM_CLI` env, a set-once `files/rrmtool_path.txt`, Program Files / (x86), the PATH, and Downloads `RRM_Tool_*` folders; clear not-found help. Fixes "RRMTool_CLI not found → Reader configuration FAILED" when RRMTool isn't in the one hard-coded path. Barcode lookup was already fine. Documented the required package (`RRM_Tool_WIN_v2.3.1`, NOT the Config Utility) and its rig location in SETUP.md §2. | `Automation/config.py`, `Automation/reader/cli.py`, `files/rrmtool_path.txt` (new), `docs/SETUP.md`, `Automation/tests/test_rrm_resolve.py` (new) |
| 9 | `feat` | **Floor hold for low-profile readers** — when a read-height descent reaches its lowest point (calibrated reader top) with no read yet, it holds and keeps listening for `READER_DESCENT_FLOOR_DWELL_S` (0.5 s) before giving up, so readers that only read when the card is touching still register. Only adds time when nothing has read; higher-reading readers are unaffected. | `Automation/config.py`, `Automation/robot/move.py`, `Automation/tests/test_descend_floor_dwell.py` (new) |

> **Commit-plan note:** because the work spanned several requests, a few files
> (`config.py`, `move.py`, `scanner.py`, `app.py`) accumulated more than one
> logical change. The §C list groups by file; for strictly one-concern commits use
> `git add -p` to stage hunks, otherwise commit each file where it is listed and
> add the extra changes to a trailing `feat`/`fix` commit.

### Explicitly NOT changed (behavior preserved)
Motion primitives, poses, speeds, timings, joint-limit/C23 handling, CSV formats
and headers, the AllCards schema, and the Tap-and-Go / Deadzone algorithms. Per
decision, Tap-and-Go and Deadzone were **verified + documented**, not rebuilt —
they already matched the spec (100 mm plunge @ 500 mm/s recording ms; continuous-
read slow ascent detecting mid-field dead spots).

## B. Verification

- `python -m pytest` → **60 passed** with no hardware attached.
- `python -m py_compile` (via the smoke test) → every production module compiles.
- Decoupling proven: `barcode.scanner` and `robot.move` import with `keyboard`
  and `msvcrt` blocked.
- The three feature fixes were each reproduced/verified in isolation (the Comment
  focus-swap race, the arrow-key mapping, and the calibration round-trip).

## C. Commit plan (run on your machine — see note D)

Each file below appears in exactly one commit, so the history is reviewable by
concern. Run from the repo root on branch `refactor/cleanup-features-docs`.

```bash
# 1) GUI feature fixes: calibration persistence + arrow-key inversion
git add Automation/gui/app.py Automation/persistence/calibration_store.py
git commit -m "feat(gui): persist reader calibration across restarts; fix calibration arrow keys"

# 2) Comment-field typing fix + keyboard decouple
git add Automation/barcode/scanner.py
git commit -m "fix(barcode): stop the wedge hook swallowing keys typed in text fields; lazy-import keyboard"

# 3) Motion core decouple
git add Automation/robot/move.py
git commit -m "refactor(robot): lazy-import msvcrt so the motion core imports headless"

# 4) Test safety net
git add Automation/tests Automation/pytest.ini Automation/requirements-dev.txt
git commit -m "test: add headless characterization suite (FakeArm + xarm/msvcrt stubs)"

# 5) RRMTool_CLI path resolution fix (reader-config failure)
git add Automation/config.py Automation/reader/cli.py files/rrmtool_path.txt \
        Automation/tests/test_rrm_resolve.py
git commit -m "fix(config): locate RRMTool_CLI via env / files/rrmtool_path.txt / PATH / Downloads; clearer not-found help"

# 6) Author/date headers on the remaining modules
git add Automation/Goer.py Automation/gui/constants.py \
        Automation/gui/gui.py Automation/gui/gui_robot.py Automation/gui/widgets.py \
        Automation/gui/arm_gl.py Automation/gui/robot_viewer.py \
        Automation/reader/ReaderConfig.py Automation/reader/ReaderConfigSDK.py \
        Automation/robot/cardreadheight.py \
        Automation/robot/test_settings.py Automation/tools/cardheight.py \
        Automation/tools/format_results_xlsx.py Automation/tools/experimental/move2.py \
        Automation/tools/ros2/ros2_bridge.py _inspect_dump.py
git commit -m "docs: add author/date headers to all modules"

# 7) Documentation
git add docs/USER_MANUAL.md docs/ARCHITECTURE.md docs/architecture_diagram.svg \
        DECISION_LOG.md README.md
git commit -m "docs: add user manual, architecture reference, structure diagram, decision log"

git push -u origin refactor/cleanup-features-docs
```

Then open Bitbucket PRs grouped by concern (features / fixes / tests / docs) so a
reviewer can read each diff on its own.

## D. Environment note — why I did not commit for you

Work was done through a sandbox that can create and overwrite files in the
OneDrive-synced repo but **cannot unlink files**, and a stale
`.git/index.lock` (dated 12:35, pre-existing) could not be removed. Git commits
therefore could not run from here. All edits are on disk on branch
`refactor/cleanup-features-docs`; the commands above are ready to run on your
machine. If Git complains about the lock, delete `.git/index.lock` first.

> There were also **pre-existing uncommitted changes** in the working tree before
> this session (e.g. `gui_robot.py`, `cli.py`, `ReaderConfigSDK.py`,
> `requirements.txt`, `AllCards.csv`, several `files/hwg/*` line-ending changes,
> `docs/*`). Some of those files also received an author/date header from this
> session. Review those diffs and fold them into the appropriate commit above (or
> a preceding `chore: baseline` commit) as you see fit.

## E. Deferred physical moves (need `git mv` / `git rm` — sandbox can't delete)

Low-risk tidying I recommend but could not perform (they require removing files):

```bash
git mv Automation/Goer.py Automation/tools/Goer.py         # commissioning helper belongs with tools/
git rm _inspect_dump.py _inspect_output.txt                # root-level scratch (already captured in results/Keep)
```

Quarantine rather than delete anything whose purpose is unclear. `Goer.py` is a
standalone "mark reader, rise N mm" commissioning aid — safe to keep under
`tools/`. `_inspect_*` are one-off inspection scratch files.

Also recommended (optional, needs approval — touches contracts):
- Rename `reader/ReaderConfig.py` / `ReaderConfigSDK.py` to snake_case for
  consistency. **Deferred** because the documented CLI path and operator muscle
  memory reference `ReaderConfig.py`.
- Wrap `ReaderConfigSDK.py`'s CLI dispatch in `if __name__ == "__main__"` (it
  currently runs on import).

## F. Data issues found in the card database (flagged, not auto-changed)

Cross-checking `files/AllCards.csv` against `files/hwg/`:
- **`Cotag UID`** (barcodes `A002` / `B002`) is in the CSV but has **no**
  `files/hwg/Cotag UID.hwg+`. Those cards will fail to configure until the HWG is
  added.
- **`files/hwg/iCLASS SEOS - Prox.hwg+`** exists but **no** CSV row references it
  (orphan).

Per the guardrails, these are flagged for you to resolve rather than changed
automatically (adding/removing card data changes behavior).

---

rf IDEAS — Proprietary and Confidential — 2026-07-30
