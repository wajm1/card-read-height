<!-- Author: Wajahat Mahmood | Updated: 2026-08-04 | rf IDEAS — Proprietary and Confidential -->

# Setup Guide — New PC Checklist

**Author:** Wajahat Mahmood  
**Updated:** 2026-08-04

> Do these steps **once** on each new control PC. Work top to bottom. After setup,
> day-to-day operation is in **[USER_MANUAL.md](USER_MANUAL.md)**.

rf IDEAS — Proprietary and Confidential

---

## Checklist (print / tick off)

1. [ ] Get the project folder
2. [ ] Install Python (+ pip)
3. [ ] Install Python packages
4. [ ] Install RRM CLI (reader config tool)
5. [ ] Point the project at `RRMTool_CLI.exe`
6. [ ] Connect hardware (robot / reader / barcode)
7. [ ] Smoke-test reader config (no robot motion)
8. [ ] Launch the GUI and run a first check

---

## Step 1 — Get the project folder

Clone or copy the repo so you have a folder like:

```
…\card-read-height\
├── Automation\          ← run everything from here
├── files\               ← AllCards.csv, hwg\, rrmtool_path.txt
├── results\
└── docs\
```

Open **PowerShell** or **Command Prompt** and go into `Automation`:

```bat
cd path\to\card-read-height\Automation
```

---

## Step 2 — Install Python and pip

1. Download **Python 3.10 or newer (64-bit)** from  
   https://www.python.org/downloads/windows/
2. Run the installer. On the first screen, check:
   - **Add python.exe to PATH**
   - Then choose **Install Now** (or Customize → include **pip**)
3. Close and reopen your terminal, then confirm:

```bat
python --version
pip --version
```

Expected: Python **3.10+** and a pip version line.  
If `python` is not found, try `py -3 --version` (Windows Python launcher).

> Use **one** Python for this project. Prefer `python` / `pip` from the same
> install. If you have several Pythons: `py -3.12 -m pip …`.

---

## Step 3 — Install project packages

Still in `Automation\`:

```bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

That installs the required packages:
- `keyboard` — barcode / credential keyboard-wedge capture  
- `xarm-python-sdk` — UFACTORY Lite 6 arm control  

**Optional (recommended for the Live-arm 3-D view in the GUI):**

```bat
python -m pip install pyopengltk PyOpenGL numpy
```

**Optional (developers only — unit tests):**

```bat
python -m pip install -r requirements-dev.txt
python -m pytest
```

**Confirm:**

```bat
python -c "import keyboard, xarm; print('OK')"
```

---

## Step 4 — Install RRM CLI (required for reader configure)

The project loads `.hwg+` files by calling **`RRMTool_CLI.exe`**. Without it,
barcode lookup still works but every configure fails.

### Get the right download

1. Open: https://www.rfideas.com/support/tools/downloads  
2. Under **Remote Reader Management (RRM)**, download  
   **RRM CLI – Windows** (currently **v2.3.1**).

| Download | Use it? |
|----------|---------|
| **RRM CLI – Windows** | **Yes** — this has `RRMTool_CLI.exe` |
| Configuration Utility – Windows | No (GUI only; you may already have it) |
| Configuration Card Manager | No |
| Smartcard Manager | No |

3. Unzip the package (no admin install required). You should find:

```
…\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe
```

A good place on the rig PC is next to the project, e.g.:

```
…\card-read-heights\
├── RRM_Tool_WIN_v2.3.1\…
└── card-read-height\          ← this repo
```

**Find it anytime:**

```bat
where /r C:\ RRMTool_CLI.exe
```

### Antivirus note (managed rf IDEAS PCs)

If `RRMTool_CLI.exe` **vanishes** after unzipping, CrowdStrike/IT may have
quarantined it. Ask IT for an exclusion on that folder/exe, then restore the
file.

---

## Step 5 — Point the project at RRMTool_CLI.exe

Edit **`files/rrmtool_path.txt`** (in the project root `files\`, not under
`Automation\`). Put the **full path** to the exe on the first non-comment line:

```
C:\Users\…\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe
```

Save the file. Then confirm from `Automation\`:

```bat
python -c "import config; print(config.RRM_CLI); print('FOUND=', config.RRM_CLI_FOUND)"
```

Must print the path and **`FOUND= True`**.

Other ways the app can find it (if you prefer not to edit the file):
1. Set env var `RRM_CLI` to the full path to the exe  
2. Install/copy it to `C:\Program Files\rf IDEAS\RRMTool\RRMTool_CLI.exe`  
3. Leave it under `Downloads\RRM_Tool_*` (auto-searched)

---

## Step 6 — Connect hardware

| Device | What to do |
|--------|------------|
| **Lite 6 arm** | Power on; same LAN as the PC. Default IP in `config.py` is `192.168.1.177`. Change once if needed: `set ROBOT_IP=192.168.1.xxx` |
| **WAVE ID reader** | Plug into USB. Close UFACTORY Studio / other apps that hold the arm or reader if they conflict |
| **Barcode scanner** | USB keyboard-wedge. On some PCs run the terminal/GUI **as Administrator** so scans are captured |

**Confirm robot network:**

```bat
ping 192.168.1.177
```

**Confirm card data is present** (usually already in the repo):
- `files\AllCards.csv`
- `files\hwg\*.hwg+` (filename must match each card **Name** + `.hwg+`)

---

## Step 7 — Smoke-test reader config (no robot)

```bat
cd path\to\card-read-height\Automation
python reader\ReaderConfig.py
```

Scan a known card barcode. Expected: card name prints, then
**`Reader configured.`**  
If you see `RRMTool_CLI not found`, go back to Steps 4–5.

---

## Step 8 — Launch the GUI

```bat
cd path\to\card-read-height\Automation
python gui\gui.py
```

1. Pass the Pre-Run Device Check (robot / reader / barcode).  
2. **CALIBRATE READER → MARK READER TOP** once (saved for next times).  
3. Pick a test and run a single card before a full batch.

Full operator flow: **[USER_MANUAL.md](USER_MANUAL.md)**.

---

## Quick reference — commands from a cold start

```bat
cd path\to\card-read-height\Automation
python -m pip install -r requirements.txt
python -c "import config; print(config.RRM_CLI_FOUND)"
python reader\ReaderConfig.py
python gui\gui.py
```

---

## Where things live

| Path | Purpose |
|------|---------|
| `Automation\` | All runnable Python (`gui`, `reader`, `robot`) |
| `Automation\requirements.txt` | Runtime pip packages |
| `files\rrmtool_path.txt` | Pins `RRMTool_CLI.exe` (set once per PC) |
| `files\AllCards.csv` | Barcode → card name / part / side |
| `files\hwg\*.hwg+` | Per-card reader configs |
| `files\calibration.json` | Saved MARK READER TOP (auto) |
| `results\` | Output CSV / Excel |
| `docs\USER_MANUAL.md` | How to run the rig day to day |

---

## If something fails

| Symptom | Fix |
|---------|-----|
| `python` / `pip` not found | Reinstall Python with **Add to PATH**; reopen terminal |
| `ModuleNotFoundError` | From `Automation\`: `python -m pip install -r requirements.txt` |
| `FOUND= False` / Reader config FAILED | Install **RRM CLI – Windows**, set `files\rrmtool_path.txt` |
| Barcode never captured | Run as Administrator; confirm wedge types into Notepad |
| Arm won’t connect | Ping IP; close UFACTORY Studio; check `ROBOT_IP` |

More detail: **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

---

rf IDEAS — Proprietary and Confidential — 2026-08-04
