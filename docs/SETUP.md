<!-- Author: Wajahat Mahmood | Updated: 2026-08-03 | rf IDEAS — Proprietary and Confidential -->

# Setup Guide — Credential Read Height Rig

**Author:** Wajahat Mahmood **Updated:** 2026-08-03

> Follow these steps in order to bring the rig up on a fresh (or repaired) PC.
> Each step says **what to do** and **how to confirm it worked**. If reader
> configuration is failing, jump straight to **Step 2 (RRMTool)** — that is the
> usual culprit. Operating instructions are in **[USER_MANUAL.md](USER_MANUAL.md)**.

rf IDEAS — Proprietary and Confidential

---

## What you need

**Hardware**
- UFACTORY **Lite 6** arm, powered on and reachable on the network.
- rf IDEAS **WAVE ID** reader on USB.
- USB **barcode scanner** (keyboard-wedge type).
- Card stack seated in the pick bin; reader mounted per **USER_MANUAL §3**.

**Software**
- **Python 3.10+** (Windows is the target; some scripts use Windows-only modules).
- **RRMTool** — the rf IDEAS reader-config CLI (**Step 2** — required).

---

## Step 1 — Python and dependencies

```bash
cd Automation
pip install -r requirements.txt
```

Installs `keyboard` (barcode capture) and `xarm-python-sdk` (Lite 6 control).

Optional extras:
```bash
pip install pyopengltk PyOpenGL numpy   # embedded Live-arm 3-D view
pip install -r requirements-dev.txt      # to run the test suite (pytest)
```

**Confirm:** `python --version` prints 3.10 or higher.

---

## Step 2 — RRMTool (REQUIRED — this is what configures the reader)

The rig configures the WAVE ID reader by shelling out to **`RRMTool_CLI.exe`**.
Without it, every card fails with *"RRMTool_CLI not found → Reader configuration
FAILED"* (barcode lookup still works, which is misleading).

### 2a. Get the RIGHT package

> ⚠️ **Not the same as the "rf IDEAS Configuration Utility."** The public
> Configuration Utility (`rfIDEASConfigurationUtility*.msi`) is a GUI and does
> **NOT** contain `RRMTool_CLI.exe`. You need the **RRM Tool** command-line
> package: **`RRM_Tool_WIN_v2.3.1`** (an internal rf IDEAS deliverable — get it
> from the rig owner / rf IDEAS engineering, not the public downloads page).

It is a portable zip; extract it (no admin install needed). Inside it is:
`…\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe`.

### 2b. Where it lives on THIS rig

On the current control PC it is installed here:

```
C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\card-read-heights\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe
```

(i.e. in the **`card-read-heights`** folder, one level **above** the `card-read-height`
project folder.)

### 2c. How the rig finds it

`config.py` resolves `RRMTool_CLI.exe` at startup, in priority order:
1. the `RRM_CLI` environment variable,
2. **`files/rrmtool_path.txt`** — a set-once override file (first non-comment line
   is the full path),
3. `C:\Program Files\rf IDEAS\RRMTool\` and `Program Files (x86)`,
4. the system `PATH`,
5. common `Downloads\RRM_Tool_*` folders.

On this rig it is pinned via **`files/rrmtool_path.txt`**, whose active line is the
full path in **2b**. If RRMTool ever moves, update that one line (or re-run the
finder command below) — nothing else changes.

Finder command (locates the exe and rewrites `files/rrmtool_path.txt`):
```powershell
$h = Get-ChildItem "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\card-read-heights","C:\Program Files\rf IDEAS" -Recurse -Filter RRMTool_CLI.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($h) { $h.FullName | Set-Content -Encoding ascii "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\card-read-heights\card-read-height\files\rrmtool_path.txt"; "PINNED -> $($h.FullName)" } else { "not found" }
```

### 2d. Confirm it works

```powershell
cd "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\card-read-heights\card-read-height\Automation"
python -c "import config; print(config.RRM_CLI, config.RRM_CLI_FOUND)"
```
Must print the path and **`True`**. If `False`, the exe is not where the file
points — re-check 2b/2c.

### 2e. Antivirus note (important on this rig)

This PC runs **CrowdStrike Falcon + Kaseya** (rf IDEAS IT managed). The original
RRMTool was removed once already. If `RRMTool_CLI.exe` **disappears** after you
place it, CrowdStrike is quarantining it — **ask rf IDEAS IT to add a Falcon
exclusion for `RRMTool_CLI.exe` (or the `RRM_Tool_WIN_v2.3.1` folder).** You cannot
override Falcon yourself on a managed machine. Keeping the exe inside the
OneDrive-synced `card-read-heights` folder also means it re-syncs to the rig.

---

## Step 3 — Robot connection

`Automation/config.py` holds the robot IP (default `192.168.1.177`). Override
without editing code:
```bat
set ROBOT_IP=192.168.1.xxx
```
**Confirm:** `ping 192.168.1.177` replies, and no other app (e.g. UFACTORY Studio)
is holding the connection.

---

## Step 4 — Card database and HWG files

- `files/AllCards.csv` — maps each barcode to `Name, Part Number, Side`.
- `files/hwg/*.hwg+` — one reader-config file per card; the filename must equal the
  CSV **`Name`** exactly, plus `.hwg+` (e.g. `Name = HID Prox UID (608x)` →
  `files/hwg/HID Prox UID (608x).hwg+`). See **USER_MANUAL §7.4** for the exact rule
  and how to add a card.

**Confirm:** the cards you plan to run have both a CSV row and a matching HWG file.

---

## Step 5 — First-run verification (do this before a full run)

Test the barcode → reader-config chain with **no robot motion**:
```bash
cd Automation
python reader/ReaderConfig.py
```
Scan a card. Expected: it prints the card name and **"Reader configured."** If you
see the RRMTool "not found" help instead, return to **Step 2**.

Then launch the app:
```bash
python gui/gui.py
```
Work through the Pre-Run Device Check (robot / reader / barcode all pass), calibrate
the reader once (**USER_MANUAL §5** — it's remembered afterwards), and run a test.

---

## Step 6 — (Developers) run the test suite

```bash
cd Automation
pip install -r requirements-dev.txt
python -m pytest
```
Runs with **no hardware attached** and must be all-green after any code change.

---

## Where things live

| Path | Purpose |
|------|---------|
| `…\card-read-heights\RRM_Tool_WIN_v2.3.1\…\RRM_Tool_exe\RRMTool_CLI.exe` | **RRMTool CLI** (reader config) — Step 2 |
| `card-read-height/files/rrmtool_path.txt` | Pins the RRMTool path (set once) |
| `card-read-height/files/AllCards.csv` | Barcode → card / part / side |
| `card-read-height/files/hwg/*.hwg+` | Per-card reader configs |
| `card-read-height/files/calibration.json` | Saved MARK READER TOP calibration (auto) |
| `card-read-height/results/` | Output CSVs / Excel |
| `card-read-height/Automation/` | All runnable Python |

> `config.py` treats the folder **above** `Automation/` (`card-read-height/`) as the
> workspace root; keep `files/` and `results/` there.

---

rf IDEAS — Proprietary and Confidential — 2026-08-03
