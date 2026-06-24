# RF IDEAS Automation System — Complete Setup Guide

Welcome! This guide walks you through setting up and using the RF IDEAS Automation System for automated credential read height testing.

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Project Structure](#project-structure)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)

---

## System Overview

### What This System Does

This automated testing system combines three core components:

1. **RFID Reader Configuration** — Barcode scanner detects card type → system auto-configures reader
2. **Robot Arm Control** — MyCobot280 robotic arm positions credentials at different heights
3. **Test Execution** — Measures read success rate at each height position

### Workflow

```
Scan Barcode
     ↓
Detect Card Type
     ↓
Load Reader Configuration
     ↓
Position Credential via Robot Arm
     ↓
Read Success/Failure at Each Height
     ↓
Log Results
```

---

## Prerequisites

### Hardware Required

- **RFID Reader** — RF IDEAS RDR-805 (USB connection)
- **Barcode Scanner** — Any USB barcode scanner
- **Robot Arm** — MyCobot280 (connected on COM3 by default)
- **Test Credentials** — Various card types to test

### Software Required

- **Python 3.8+** — [Download](https://www.python.org/downloads/)
- **RRMTool_CLI** (optional) — For advanced reader configuration
  - Download: RF IDEAS website
  - Path: `C:\Users\wmahmood\Downloads\RRM_Tool_WIN_v2.3.1\RRM_Tool_WIN_v2.3.1\RRM_Tool_exe\RRMTool_CLI.exe`

### System Requirements

- Windows 10/11
- 500MB free disk space
- USB ports for reader, scanner, robot

---

## Installation

### Step 1: Install Python Dependencies

```bash
cd "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\Testing\Automation"
pip install -r requirements.txt
```

This installs:
- `hidapi` — USB HID reader communication
- `PyMyCobotCOBOT` — Robot arm control
- `keyboard` — Barcode scanner input capture
- `openpyxl` — Excel test data handling

### Step 2: Verify Hardware Connections

**RFID Reader:**
```bash
python reader_config/ReaderConfigSDK.py about
```
Should output: `✅ Reader opened: 0xc27:0x3bfa`

**Robot Arm:**
```bash
python robot_testing/jog_control.py
```
Should output: `✅ Connected on COM3`

**Barcode Scanner:**
- Connect to any USB port
- Test by scanning a barcode in Notepad (should type characters)

### Step 3: Create Virtual Environment (Optional but Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

---

## Quick Start

### Launch the Main GUI

```bash
cd "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\Testing\Automation"
python robot_testing/gui.py
```

### Test Workflow

1. **Select Test Condition** — Choose from 4 preset angles or "All 4 conditions"
2. **Scan Card Barcode** — Present card to scanner
3. **Confirm Configuration** — System shows detected card type
4. **Start Test** — Robot automatically positions card at each height
5. **View Results** — Results saved to `logs/test_results.txt`

---

## Project Structure

```
Testing/
└── Automation/
    ├── config.py                    # Centralized settings
    ├── requirements.txt             # Python dependencies
    ├── README.md                    # Quick reference
    ├── SETUP.md                     # This file
    ├── USAGE.md                     # Detailed usage guide
    ├── API.md                       # Developer reference
    │
    ├── reader_config/               # Reader configuration
    │   ├── ReaderConfigSDK.py       # USB HID direct control
    │   ├── ReaderConfig.py          # RRMTool_CLI wrapper
    │   ├── configs/                 # Reader config files
    │   │   └── cepas.hwg+           # CEPAS card config
    │   └── README.md                # Reader docs
    │
    ├── robot_testing/               # Robot arm & testing
    │   ├── gui.py                   # Main GUI app
    │   ├── test_runner.py           # Test logic
    │   ├── jog_control.py           # Manual control
    │   ├── position_recorder.py     # Record positions
    │   └── README.md                # Robot docs
    │
    ├── data/                        # Test data
    │   ├── test_cards.xlsx          # Card definitions
    │   └── position_data/           # Recorded positions
    │       └── card_positions.txt   # Position data
    │
    ├── logs/                        # Output & results
    │   ├── test_results.txt         # Test results
    │   ├── rrm_tool.log             # Reader logs
    │   └── positions.txt            # Position logs
    │
    └── docs/                        # Documentation
        ├── SETUP.md                 # Setup guide (this file)
        ├── USAGE.md                 # Usage guide
        ├── API.md                   # API reference
        ├── TROUBLESHOOTING.md       # Help & debugging
        └── EXAMPLES.md              # Code examples
```

---

## Configuration

### Edit config.py

All settings are centralized in `config.py`:

```python
# Robot connection
ARM_PORT = "COM3"          # Change if robot on different port
ARM_SPEED = 65             # Movement speed (0-100)

# Test parameters
DESCENT_SPEED = 20         # Speed during careful descent
DESCENT_STEP = 2.0         # Millimeters per step
DESCENT_DELAY = 0.2        # Seconds between steps
READ_TIMEOUT = 0.15        # Seconds to wait for read

# Reader path
RRM_CLI = r"C:\Users\wmahmood\Downloads\RRM_Tool_WIN_v2.3.1\..."
```

### Add New Card Types

1. **Get barcode prefix** — e.g., "A005" for CEPAS front
2. **Create config file** — Ask your reader admin
3. **Save to `reader_config/configs/`** — e.g., `my_card.hwg+`
4. **Update config.py:**

```python
CARD_TYPE_MAP = {
    "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
    "B005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
    "NEW1": {"name": "My New Card", "hwg": "my_card.hwg+"},  # Add this
}
```

---

## Common Commands

### Reader Configuration

```bash
# View reader info
python reader_config/ReaderConfigSDK.py about

# Set to CEPAS
python reader_config/ReaderConfigSDK.py set-cepas

# Save config to file
python reader_config/ReaderConfig.py save my_config.hwg

# Load config from file
python reader_config/ReaderConfig.py load my_config.hwg
```

### Robot Control

```bash
# Manual jog with keyboard
python robot_testing/jog_control.py

# Record new positions
python robot_testing/position_recorder.py

# Run tests (via GUI preferred)
python robot_testing/test_runner.py
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'hidapi'"

**Solution:**
```bash
pip install hidapi
```

### "Could not connect to robot on COM3"

**Check:**
1. Robot arm is powered on
2. USB cable is connected
3. Device Manager shows COM3 device
4. Another app isn't using the port

**Fix:**
- Update `ARM_PORT` in `config.py` to correct port
- Close other serial port applications

### "HWG file not found"

**Check:**
1. File exists in `reader_config/configs/`
2. Filename matches `CARD_TYPE_MAP` in `config.py`
3. File isn't locked by another program

### "Barcode not detected"

**Check:**
1. Barcode scanner is connected (USB)
2. Test in Notepad — should type characters
3. Barcode format matches `CARD_TYPE_MAP`
4. Check `logs/` for error details

### GUI won't start

**Check:**
```bash
# Verify Tkinter is installed
python -m tkinter
# Should show a small window

# Check for import errors
python -c "import tkinter; print('OK')"
```

---

## Getting Help

### Check Documentation

- **How do I use X?** → See `USAGE.md`
- **I'm a developer** → See `API.md`
- **Something broke** → See `TROUBLESHOOTING.md`
- **I want code examples** → See `EXAMPLES.md`

### Check Logs

All important events are logged:
- `logs/test_results.txt` — Test data
- `logs/rrm_tool.log` — Reader output
- `logs/positions.txt` — Robot positions

### Run Diagnostics

```bash
# Test all imports
python -c "
import config
from reader_config.ReaderConfigSDK import Reader
print('✅ All imports OK')
"

# Check paths
python -c "
import config
for name, path in config.PATHS.items():
    print(f'{name}: {path}')
"
```

---

## Next Steps

1. ✅ Install dependencies
2. ✅ Connect and verify hardware
3. ✅ Read `USAGE.md` for detailed workflows
4. ✅ Run first test with GUI
5. ✅ Review `API.md` if customizing code

---

## Support

- **Issues**: Check `logs/` and console output
- **Questions**: Review documentation in `docs/` folder
- **Bugs**: Record in `logs/` and create issue note

---

**Last Updated**: 2025
**Version**: 1.0
