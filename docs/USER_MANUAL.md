<!-- Author: Wajahat Mahmood | Updated: 2026-07-30 | rf IDEAS — Proprietary and Confidential -->

# Credential Read Height Rig — User Manual

**Author:** Wajahat Mahmood
**Updated:** 2026-07-30
**Applies to:** UFACTORY Lite 6 arm + rf IDEAS WAVE ID reader + USB barcode wedge

> **What this document is.** A start-to-finish guide for someone who has *never*
> run this rig before. It covers physical setup, calibration, running each test,
> reading the results, troubleshooting the reader and barcode, adding new cards,
> and how to extend the program. Read it top to bottom the first time; after that
> use the section headings as a checklist.

rf IDEAS — Proprietary and Confidential

---

## 1. What the rig does

The arm picks a plastic credential from a bin, waves its **barcode** past a
scanner to identify the card, **configures** the WAVE ID reader for that card
type (using an `.hwg+` file via RRMTool), then presents the card to the reader to
measure one or more of:

| Test | Plain-English description | Output |
|------|---------------------------|--------|
| **Read Height** | Lower the card slowly at 0°/90°/180°/270° until the reader reads. Record how high above the reader the card first read. | mm above reader, per angle |
| **Tap and Go** | Plunge the card from ~100 mm above the reader straight down to the reader top at the arm's **max speed (500 mm/s)**, and time how long the reader takes to report the read. | milliseconds (ms) |
| **Deadzone** | Put the reader in **continuous read**, rest the card on the reader top, then rise slowly. Watch for a *dead spot* — a height where the card stops reading and then starts again. | deadzone height(s) in mm |

Results are written as CSV files to the `results/` folder, and Read Height runs
also produce a formatted Excel workbook.

---

## 2. One-time software setup

You only do this once per PC. See **[SETUP.md](SETUP.md)** for the full version.

1. Install Python 3.10+ (64-bit) and make sure `python` works in a terminal.
2. Open a terminal in the `Automation/` folder and install dependencies:

   ```bash
   cd Automation
   pip install -r requirements.txt
   ```

3. Install **RRMTool** (the rf IDEAS reader-configuration CLI). ⚠️ This is the
   **`RRM_Tool_WIN_v2.3.1`** package (contains `RRMTool_CLI.exe`), **not** the
   public "rf IDEAS Configuration Utility" `.msi` (a GUI that does not include the
   CLI). On this rig it lives at
   `…\card-read-heights\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe`
   and is pinned in `files/rrmtool_path.txt`. Full install details, verification,
   and the antivirus caveat are in **[SETUP.md](SETUP.md) §2**. The program also
   finds `RRMTool_CLI.exe` automatically in `C:\Program Files\rf IDEAS\RRMTool\`, on
   your PATH, or under `Downloads\RRM_Tool_*`. To point it elsewhere once, put the
   full path on the first line of **`files/rrmtool_path.txt`**. Locate the exe with:

   ```bat
   where /r C:\ RRMTool_CLI.exe
   ```

   Verify what the rig resolved (should print `True`):

   ```bat
   cd Automation && python -c "import config; print(config.RRM_CLI, config.RRM_CLI_FOUND)"
   ```

4. (Optional) For the embedded 3-D Live-arm view:
   `pip install pyopengltk PyOpenGL numpy`.

> **Admin note:** the barcode/credential capture uses a global keyboard hook
> (the `keyboard` package). On some Windows machines you must run the terminal
> **as Administrator** for scans to be captured.

---

## 3. Physical setup — do this before every session

Getting the hardware placed correctly is the single biggest cause of "it won't
read" problems. Work through this list every time.

### 3.1 Mount the reader securely, facing the arm
- Bolt or clamp the reader down so it **cannot shift** during a run. A reader
  that slides even 1–2 mm invalidates the calibrated tap location.
- Orient the reader so its **read face (the side with the rf IDEAS logo / antenna)
  points up and toward the arm**, i.e. the arm lowers the card flat onto that
  face. The card must be able to sit parallel and flat on the reader top.
- Keep the USB cable strain-relieved so it can't tug the reader.

### 3.2 Load the cards in the correct bin, barcodes toward the arm
- Place the credential stack in the **pick bin** the arm is taught to pick from
  (the `PICK_ANGLE` pose in `gui/constants.py`). Cards go in flat and squared up.
- Each card has a **barcode** (e.g. `A005`, `B012`). Load the cards so the
  **barcode faces the barcode scanner / toward the arm's scan pose**, not
  buried at the bottom. The arm lifts a card, turns to the scan pose, and waves
  it in front of the scanner; the barcode must be readable there.
- `A###` = front (side A), `B###` = back (side B). If you are running a **flip
  test**, both faces get scanned.

### 3.3 Calibrate the reader (see §5) — now remembered between sessions
- The arm needs to know exactly where the **reader top** is. You set this once
  with **CALIBRATE READER → MARK READER TOP**. As of 2026-07-30 this is **saved
  to disk per reader model** and reloaded automatically next time you open the
  GUI, so you do **not** have to re-calibrate every session — only when you move
  the reader or switch to a different reader.

---

## 4. Running a test (step by step)

1. **Open a terminal** in `Automation/` and launch the GUI:

   ```bash
   cd Automation
   python gui/gui.py
   ```

2. **Pre-Run Device Check** screen appears. Enter the **Robot IP**
   (default `192.168.1.177`) and click each **TEST**:
   - *Robot arm connected & ready* — confirms the arm answers at that IP.
   - *Card reader connected (USB)* — confirms RRMTool sees the reader.
   - *Barcode scanner* — scan any card's barcode within 15 s to confirm the wedge.

   All three must pass to unlock **CONTINUE TO TEST**. (There is a small
   *Skip checks →* link if you already know the rig is good.)

3. **Choose test(s).** Tick one or more:
   - **Read Height** and **Tap and Go** can run **together** on each card.
   - **Deadzone** runs **alone** (it reconfigures the reader for continuous read).

4. **Set parameters** on the left panel:
   - **Reader type** — pick your model (PICO, HIP2_SP, MICRO, NANO_USBA,
     MINI_DESKTOP, or OTHER). If a calibration is saved for it, a status line
     confirms it was loaded.
   - **Comment (file header)** — free text written into the CSV header. *(You can
     now type here reliably — see the fix note in §8.)*
   - **Cards** — how many credentials to run.
   - **Taps per angle** — how many measurements/taps to average per angle.
   - **Test speed** — descent/ascent preset (Slowest → Fastest) for Read Height
     and Deadzone.
   - **Read angles** — which of 0°/90°/180°/270° to test.
   - **Both sides (flip)** — test side A, flip the card, then test side B.

5. **CALIBRATE READER** first if you have not (see §5).

6. Press **START TEST**. The right panel shows live progress, a pass/fail dot,
   a results table per test, and an activity log. Press **STOP / ABORT** at any
   time for a safe stop (or press **Q** in the launching terminal).

7. When the run ends, the CSV path(s) are logged and shown. Files land in
   `results/`. Use **EXPORT CSV / EXCEL** to re-save and build the formatted
   Excel report.

---

## 5. Calibration mode (MARK READER TOP)

Calibration teaches the arm the exact card **tap location** and **reader top
height**. Open it with **CALIBRATE READER** on the main screen.

1. The arm connects and moves to the staging pose over the reader, and **suction
   turns on** — place a card on the suction cup.
2. **Jog** the arm until the card *just touches* the reader top:
   - **Arrow keys** move the card in X/Y (over the reader). *(Left/Right were
     inverted before 2026-07-30 and are now corrected — ← moves left, → moves
     right, matching the on-screen ◀/▶ buttons.)*
   - **W** = up, **S** = down (height).
   - **Step size** radio buttons (or keys **1**/**2**/**3**) switch between
     Coarse (10 mm), Medium (1 mm), and Fine (0.1 mm).
   - A hard floor stops the tool from driving into the table.
3. When the card is resting on the reader top, press **MARK READER TOP**. The arm
   records the reader-top height and the approach staging pose, then lifts clear.
4. **It is now saved.** The captured height/floor/approach pose is written to
   `files/calibration.json` under this reader model. Next time you open the GUI
   and select the same reader, it is loaded automatically. **To change it, simply
   calibrate again** — re-marking overwrites the saved value.

> If you move the reader or the table, re-calibrate. The GUI stores the table
> height used at capture time and can tell if it has drifted.

---

## 6. Understanding the three tests in detail

### 6.1 Read Height
For each selected angle the arm does a fast "find the zone" descent (not
recorded), then progressively slower descents; only the **final, slowest tap** is
recorded. The recorded number is the card-face height above the reader top when
the reader fired. Accuracy is set by the **Test speed** preset (Slowest = 0.1 mm
final steps).

**Low-profile readers (card must be touching):** when a descent reaches its
lowest point (the calibrated reader top) without a read yet, the arm now **holds
there and keeps listening** for a moment before giving up, so a reader that only
reads while the card is essentially touching still gets caught. The hold length is
`READER_DESCENT_FLOOR_DWELL_S` in `config.py` (default **0.5 s**). This only adds
time when nothing has read — readers that read higher up during the descent are
unaffected. For a very low reader, **calibrate it first** (MARK READER TOP at the
point where the card just touches) so the descent floor is the true reader top.

### 6.2 Tap and Go
Mirrors the UFactory Studio tap pattern at the Lite 6's hardware maximum:
- Start ~**100 mm** above the reader (runway to reach top speed).
- Plunge straight down at **500 mm/s** to the calibrated reader top.
- Start a millisecond timer at the plunge and stop it when the reader reports the
  read (keyboard-wedge event). That elapsed time in **ms** is the tap time.
- Lift, wait for the reader to reset, repeat for *Taps per angle*.
- The floor is clamped at the calibrated reader top so the card never crushes the
  reader.

CSV columns: taps, reads, misses, avg/min/max ms, and every individual tap time.

### 6.3 Deadzone
- The reader is loaded with a **continuous-read** HWG (short lockout) so it keeps
  reporting while a card stays in the field.
- The card is placed on the reader top, then **rises slowly** in preset-sized
  steps, listening at each step.
- **Deadzone** = reading stops for a couple of steps and then **resumes** while
  still climbing — a genuine gap inside the field. Its height (mm above reader) is
  recorded.
- **Exit / end of field** = reading stops and *stays* stopped (10 steps) or the
  card reaches the max height. That final loss is *not* a deadzone — the card
  simply left the readable range.

---

## 7. Reader & barcode troubleshooting

### 7.1 `ReaderConfig.py` — test the barcode → reader-config chain by hand
When a run can't read a card, isolate whether the **barcode** and **reader
configuration** work, without any robot motion:

```bash
cd Automation
python reader/ReaderConfig.py
```

Then scan a card's barcode by hand (or hold it to the wedge). The tool will:
1. Print the barcode it captured — *if nothing prints, the scanner/wedge is the
   problem* (USB, admin rights, or the barcode facing the wrong way).
2. Look the barcode up in `AllCards.csv` — *"Unknown barcode" means the code is
   not in the CSV* (see §7.3).
3. Load the matching `.hwg+` and configure the reader — *a failure here points at
   RRMTool, the reader USB, or a missing HWG file*.

Press **Ctrl+C** to quit. This is the fastest way to answer "is it the scanner,
the card database, or the reader?"

### 7.2 `ReaderConfigSDK.py` — talk to the reader directly over USB HID
For low-level reader checks that don't use RRMTool at all (requires
`pip install hid`):

```bash
cd Automation
python reader/ReaderConfigSDK.py about      # firmware, active config, card type
python reader/ReaderConfigSDK.py read       # dump the current 40-byte config
python reader/ReaderConfigSDK.py beep 3     # make the reader beep (confirms USB)
python reader/ReaderConfigSDK.py set-cepas  # apply a CEPAS config (asks to confirm)
```

Use `beep` first — if the reader beeps, USB HID is healthy and the problem is
elsewhere.

### 7.3 Common problems and fixes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| **"RRMTool_CLI not found … Reader configuration FAILED"** (barcode still resolves, e.g. B033→Seos) | RRMTool isn't installed at the expected path | Put the exe's full path on line 1 of `files/rrmtool_path.txt` (find it with `where /r C:\ RRMTool_CLI.exe`), or set `RRM_CLI`. Verify with `python -c "import config; print(config.RRM_CLI_FOUND)"`. |
| Barcode check never passes / no scan captured | Wedge not focused; not running as admin; barcode facing away from the arm | Run the terminal as Administrator; reload cards barcode-out; try `ReaderConfig.py` |
| "Unknown barcode — not in AllCards.csv" | Card's code isn't in the database | Add a row to `AllCards.csv` (§7.4) |
| "HWG file not found" | The card's HWG file name doesn't match its `Name` in the CSV | Rename/create the `.hwg+` so it matches the `Name` exactly (§7.4) |
| Reader never reads during a run | Reader not calibrated, or reader shifted | Re-run **CALIBRATE READER → MARK READER TOP** |
| Low reader misses reads — card doesn't seem to wait/touch | Descent floor above the reader top, or the reader needs the card touching + a beat | Calibrate at the touch point (MARK READER TOP); the arm holds `READER_DESCENT_FLOOR_DWELL_S` (0.5 s) at the floor — raise it in `config.py` if the reader needs longer |
| Arm stops with error **C23** (joint limit) | A joint is at/past its limit | In UFACTORY Studio → Manual Mode, drag the flagged joint back toward mid-range, Clear Error, Enable. The log names the exact joint. |
| Can't type in the **Comment** field | (Fixed 2026-07-30.) Previously a focus race let the wedge hook swallow keys | Update to the current build; click the field and type. If a card is sitting on a live reader it can still inject characters — move it away while typing. |
| Reader detected but tap times are all "miss" | Reader reset time too short, or reader top mis-calibrated | Recalibrate; increase *Taps per angle* dwell; confirm the card actually touches at the reference. |

### 7.4 Adding new cards to `AllCards.csv` and the HWG-name rule

`files/AllCards.csv` maps a **barcode** to a **card name**, **part number**, and
**side**. Columns: `Barcode,Name,Part Number,Side`.

To add a card:
1. Open `files/AllCards.csv` in a text editor or Excel.
2. Add a row, e.g. `A042,My New Card,700-X-1234,A` (and a `B042,…,B` row for the
   back if you test both sides).
3. **Create the matching HWG file.** The program builds the HWG filename directly
   from the `Name` column: **`<Name>.hwg+`**. So a card named `My New Card` needs
   `files/hwg/My New Card.hwg+`.

   **The rule, precisely:**
   - The HWG filename must equal the `Name` column **exactly** — same letters,
     same **internal spaces**, same capitalization — plus the `.hwg+` extension.
     Example: `Name = HID Prox UID (608x)` → `files/hwg/HID Prox UID (608x).hwg+`.
   - **Leading/trailing spaces are trimmed** before matching, so a stray trailing
     space in the CSV (e.g. `CEPAS `) still maps to `CEPAS.hwg+`. Do **not** rely
     on this — keep the CSV clean.
   - It is safest to add **no extra spaces** and to copy the exact reader-produced
     HWG file into `files/hwg/` and name the CSV `Name` to match it character for
     character.

4. Save. Re-run `ReaderConfig.py` and scan the new card to confirm it looks up and
   configures.

> **Known data gaps (flagged, not auto-changed):** `Cotag UID` (barcodes
> `A002`/`B002`) is in the CSV but has **no** `files/hwg/Cotag UID.hwg+`, so those
> cards will fail to configure until you add that file. Conversely
> `files/hwg/iCLASS SEOS - Prox.hwg+` exists but no CSV row references it. Resolve
> these before relying on those cards.

---

## 8. Notes on the 2026-07-30 changes (what changed and why)

- **Comment field is now typable.** The barcode wedge is captured by a global
  keyboard hook; a focus-tracking race could leave the "operator is typing" flag
  off and let the hook swallow the first characters. The fix tracks which field
  holds focus (and also reacts to a click), so typing always passes through.
- **Calibration arrow keys corrected.** Left/Right were reversed relative to the
  on-screen ◀/▶ buttons; they now agree.
- **Calibration is remembered.** MARK READER TOP is saved to
  `files/calibration.json` per reader model and reloaded on launch; recalibrate to
  change it.

None of these changed the motion, timing, poses, or CSV formats.

---

## 9. Running and extending the test suite

The rig ships with an automated test suite that runs **with no hardware attached**
(a `FakeArm` stands in for the robot, and the barcode/OS modules are stubbed).

```bash
cd Automation
pip install -r requirements-dev.txt
python -m pytest
```

You should see all tests pass. Run this **after any code change** — it locks in
the geometry math, the per-angle staging poses, the CSV row math for all three
tests, barcode/lookup behavior, HWG editing, and calibration persistence.

**To add a test:** drop a `test_*.py` file in `Automation/tests/`. Use the
`gui_robot` fixture (a `GuiRobot` wired to a `FakeArm`) to exercise motion logic;
assert against `fake_arm.calls` to check the exact sequence of arm commands a
change must preserve. See `tests/test_result_rows.py` for the pattern.

## 10. Extending the program

- **Add a card / reader / HWG:** §7.4 (cards) and `gui/constants.py`
  (`READER_TYPES`, `NOMINAL_READER_HEIGHTS_MM`).
- **Tune a test:** all tuning constants live in `gui/constants.py`
  (`TAPGO_*`, `DEADZONE_*`, `DESCENT_PRESETS`, `CALIB_*`) and `config.py`
  (speeds, poses, floors). Change values there, then run the test suite.
- **Add a new test mode:** implement a `run_<name>()` method on `GuiRobot`
  (`gui/gui_robot.py`) following `run_tap_and_go` / `run_deadzone`; add its result
  row shape and a results tab in `gui/app.py`; wire it into `show_test_select` and
  `_run_worker`. Add characterization tests alongside.
- **Architecture reference:** see **[ARCHITECTURE.md](ARCHITECTURE.md)** for the
  module map, data/control flow, and the program-structure diagram.

---

rf IDEAS — Proprietary and Confidential — 2026-07-30
