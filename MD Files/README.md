# Documentation Index

Complete documentation for the RF IDEAS Automation System.

---

## Quick Navigation

### 🚀 **Just Getting Started?**
→ Start with [SETUP.md](SETUP.md) (Installation in 5 minutes)

### 💡 **How Do I Use This?**
→ Read [USAGE.md](USAGE.md) (Complete workflow guide)

### 🔧 **Building Custom Scripts?**
→ Check [API.md](API.md) (Developer reference)

### 🐛 **Something's Not Working?**
→ See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) (Debug guide)

---

## Documentation Files

### SETUP.md — Installation & Configuration

**What's inside:**
- System overview and workflow
- Hardware prerequisites
- Step-by-step installation
- Project structure explanation
- Configuration guide
- Common commands reference

**Read this if:**
- You're setting up for the first time
- You need to install dependencies
- You want to understand the project layout
- You're configuring for a new environment

**Time to read:** 10 minutes

---

### USAGE.md — How to Use the System

**What's inside:**
- Quick start (2 minutes)
- GUI application walkthrough
- Command-line tools reference
- Python API examples
- Workflow examples
- Data output formats
- Keyboard shortcuts

**Read this if:**
- You want to run tests
- You need to use the GUI
- You want to understand workflows
- You're looking for specific commands

**Time to read:** 15 minutes

---

### API.md — Developer Reference

**What's inside:**
- Config module documentation
- Reader module (ReaderConfigSDK)
- Robot module (MyCobot280)
- Barcode scanner integration
- Example Python scripts
- Error handling patterns

**Read this if:**
- You're writing custom scripts
- You need API references
- You want code examples
- You're extending functionality

**Time to read:** 20 minutes

---

### TROUBLESHOOTING.md — Debug & Help

**What's inside:**
- Installation problem solutions
- Hardware connection issues
- Reader configuration errors
- Robot arm problems
- Barcode scanning issues
- GUI problems
- Performance optimization

**Read this if:**
- Something isn't working
- You're getting error messages
- Tests are failing
- Performance is slow

**Time to read:** 5 minutes (per issue)

---

## Project Structure

```
Testing/
├── SETUP.md                 ← START HERE
├── USAGE.md
├── API.md
├── TROUBLESHOOTING.md
│
└── Automation/              ← Main project folder
    ├── config.py            ← Settings (edit to customize)
    ├── requirements.txt     ← Python dependencies
    ├── README.md            ← Quick reference
    │
    ├── reader_config/       ← Reader configuration
    │   ├── ReaderConfigSDK.py
    │   ├── ReaderConfig.py
    │   └── configs/
    │       └── cepas.hwg+
    │
    ├── robot_testing/       ← Robot control & testing
    │   ├── gui.py          ← Main entry point
    │   ├── test_runner.py
    │   ├── jog_control.py
    │   └── position_recorder.py
    │
    ├── data/                ← Test data
    │   ├── test_cards.xlsx
    │   └── position_data/
    │       └── card_positions.txt
    │
    └── logs/                ← Results & debugging
        ├── test_results.txt
        ├── rrm_tool.log
        └── positions.txt
```

---

## Workflow Overview

### 1. First Time Setup (30 minutes)

1. Read [SETUP.md](SETUP.md) — Installation steps
2. Run `pip install -r requirements.txt`
3. Test hardware connections
4. Launch GUI: `python robot_testing/gui.py`

### 2. Running Tests (5 minutes per test)

1. Open [USAGE.md](USAGE.md) — GUI walkthrough section
2. Launch GUI: `python robot_testing/gui.py`
3. Select test condition
4. Scan barcode
5. Click "Start Test"

### 3. Custom Development (varies)

1. Review [API.md](API.md) — Find what you need
2. Check example scripts in API.md
3. Write your script
4. Test with `python your_script.py`

### 4. Debugging Issues (varies)

1. Run diagnostic: `python reader_config/ReaderConfigSDK.py about`
2. Check logs in `Automation/logs/`
3. Find error in [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
4. Apply fix

---

## Common Tasks

### "How do I test a card?"
→ See [USAGE.md](USAGE.md) — "GUI Application" section

### "I need to add a new card type"
→ See [SETUP.md](SETUP.md) — "Add New Card Types" section

### "How do I change robot speed?"
→ See [API.md](API.md) — "Robot Settings" section

### "My reader won't configure"
→ See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — "Reader Configuration" section

### "I want to write a custom script"
→ See [API.md](API.md) — "Example Scripts" section

### "My barcode scanner isn't working"
→ See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — "Barcode Scanning" section

---

## Key Concepts

### Hardware Components

- **RFID Reader** — Detects credentials, configurable via HID
- **Barcode Scanner** — Identifies card type via USB input
- **Robot Arm** — Positions credentials at test heights

### Software Components

- **config.py** — Central settings file (edit here!)
- **GUI** — Main user interface (gui.py)
- **Reader Config** — HID communication (ReaderConfigSDK.py)
- **Robot Control** — Arm positioning (via PyMyCobotCOBOT)

### Workflow Steps

1. Scan barcode → Barcode scanner detects card type
2. Match barcode → CARD_TYPE_MAP shows config file
3. Load config → Reader configured for card type
4. Position card → Robot arm moves card to start position
5. Descent test → Robot steps down slowly, reading at each height
6. Log results → Results saved to logs/test_results.txt

---

## Important Settings (in config.py)

```python
# Robot connection
ARM_PORT = "COM3"           # USB port for robot

# Test parameters
DESCENT_SPEED = 20          # Speed during careful descent
DESCENT_STEP = 2.0          # Millimeters per step
READ_TIMEOUT = 0.15         # Seconds to wait for read

# Card type mapping
CARD_TYPE_MAP = {
    "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
}

# Reader path (optional)
RRM_CLI = r"C:\...\RRM_Tool_CLI.exe"
```

**Edit config.py if:**
- Robot is on different COM port
- You need to change speeds
- You're adding new card types
- You're updating RRMTool path

---

## Quick Reference

### Installation
```bash
cd Automation
pip install -r requirements.txt
```

### Launch GUI
```bash
python robot_testing/gui.py
```

### Test Reader
```bash
python reader_config/ReaderConfigSDK.py about
```

### Manual Jog
```bash
python robot_testing/jog_control.py
```

### Record Positions
```bash
python robot_testing/position_recorder.py
```

---

## File Legend

| File | Purpose | When to Read |
|------|---------|--------------|
| SETUP.md | Installation & config | First time setup |
| USAGE.md | How to use system | Running tests |
| API.md | Developer reference | Writing code |
| TROUBLESHOOTING.md | Debug & help | Something broke |
| README.md (Automation/) | Quick reference | Need quick info |
| config.py | Settings file | Customizing |

---

## Support Checklist

If something isn't working:

- [ ] Read relevant section in TROUBLESHOOTING.md
- [ ] Check logs in `Automation/logs/` folder
- [ ] Run diagnostic test for that component:
  - Reader: `python reader_config/ReaderConfigSDK.py about`
  - Robot: `python robot_testing/jog_control.py`
  - Config: `python -c "import config; print('OK')"`
- [ ] Check `config.py` for obvious errors
- [ ] Restart hardware (power cycle)
- [ ] Reinstall dependencies: `pip install -r requirements.txt`

---

## Version Information

- **System Version**: 1.0
- **Created**: June 2025
- **Python Version**: 3.8+
- **Last Updated**: 2025-06-09

---

## Getting Help

1. **Search the docs** — Use Ctrl+F to search all files
2. **Check logs** — Look in `Automation/logs/`
3. **Run diagnostics** — Test individual components
4. **Review examples** — See API.md for code samples
5. **Check TROUBLESHOOTING** — Most common issues covered

---

## Next Steps

✅ **Installation complete?** → Go to [SETUP.md](SETUP.md)

✅ **Ready to test?** → Go to [USAGE.md](USAGE.md)

✅ **Writing scripts?** → Go to [API.md](API.md)

✅ **Having issues?** → Go to [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

**Happy testing! 🚀**
