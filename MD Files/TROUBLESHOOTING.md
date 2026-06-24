# Troubleshooting Guide

Solutions to common problems.

---

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Hardware Connection](#hardware-connection)
3. [Reader Configuration](#reader-configuration)
4. [Robot Arm](#robot-arm)
5. [Barcode Scanning](#barcode-scanning)
6. [GUI Issues](#gui-issues)
7. [Performance](#performance)

---

## Installation Issues

### "ModuleNotFoundError: No module named 'hidapi'"

**Problem**: Python can't find the hidapi library.

**Solution**:
```bash
pip install hidapi
```

**Alternative** (if that fails):
```bash
pip uninstall hidapi hid -y
pip install hidapi==0.15.0
```

### "ModuleNotFoundError: No module named 'PyMyCobotCOBOT'"

**Problem**: Robot arm library not installed.

**Solution**:
```bash
pip install PyMyCobotCOBOT
```

### "No module named 'keyboard'"

**Problem**: Barcode scanner library missing.

**Solution**:
```bash
pip install keyboard
```

### "ImportError: cannot import name 'config'"

**Problem**: config.py not found in path.

**Solution**:
```bash
# Make sure you're in the Automation folder
cd "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\Testing\Automation"

# Then run scripts from there
python reader_config/ReaderConfigSDK.py about
```

### "Permission denied" on install

**Problem**: Don't have admin rights.

**Solution**:
```bash
# Install to user directory
pip install --user hidapi keyboard PyMyCobotCOBOT

# Or use virtual environment
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Hardware Connection

### "Could not open reader" or "Reader not found"

**Problem**: RFID reader not detected.

**Diagnosis**:
```bash
# Check if reader is listed
python reader_config/ReaderConfigSDK.py about
```

**Solutions**:

1. **Check USB connection**
   - Unplug and reconnect USB cable
   - Try different USB port
   - Check cable for damage

2. **Check Device Manager**
   - Press `Win+X`, select "Device Manager"
   - Look for "USB HID Devices" or similar
   - If there's a warning icon, right-click → Update driver

3. **Check reader power**
   - Ensure reader has power (LED indicator)
   - Try power cycle (unplug for 10 seconds)

4. **Test with different computer** (if possible)
   - Determines if it's computer or reader issue

5. **Reinstall hidapi**
   ```bash
   pip uninstall hidapi -y
   pip install hidapi
   ```

### "Could not connect to robot on COM3"

**Problem**: MyCobot280 not responding.

**Diagnosis**:
```bash
# Check Windows Device Manager
# Should see "COM3" or similar under "Ports (COM & LPT)"
```

**Solutions**:

1. **Check robot power**
   - Power on robot arm
   - LED indicators should light up

2. **Check USB cable**
   - Unplug and reconnect
   - Try different USB port
   - Check for visible damage

3. **Find correct COM port**
   ```bash
   # Open Device Manager (Win+X)
   # Expand "Ports (COM & LPT)"
   # Note the COM number
   
   # Update config.py
   # Change ARM_PORT = "COM3" to your COM number
   ```

4. **Fix serial port issues**
   - Right-click COM port in Device Manager
   - Select "Properties"
   - Go to "Port Settings"
   - Click "Advanced"
   - Uncheck "Use FIFO buffers"

5. **Test robot connection**
   ```bash
   python -c "
   from pymycobot.mycobot280 import MyCobot280
   mc = MyCobot280('COM3', 115200)
   print(mc.get_angles())
   mc.close()
   "
   ```

### "Barcode scanner not responding"

**Problem**: Barcode scanner not detected.

**Solutions**:

1. **Connect scanner**
   - Plug USB cable into computer
   - Wait 5 seconds for driver installation

2. **Test scanner**
   - Open Notepad
   - Scan a barcode
   - Should type characters

3. **Check Device Manager**
   - Should see USB HID device
   - If there's a warning, update driver

4. **Enable keyboard input**
   - Some scanners need setup
   - Check scanner manual
   - May need to scan configuration barcode

---

## Reader Configuration

### "HWG file not found"

**Problem**: Reader configuration file can't be located.

**Solutions**:

1. **Check file exists**
   ```bash
   # Should exist:
   Automation/reader_config/configs/cepas.hwg+
   ```

2. **Verify filename in config.py**
   ```python
   CARD_TYPE_MAP = {
       "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},  # Filename must match
   }
   ```

3. **Check file permissions**
   - Right-click file → Properties
   - Click "Security" → "Advanced"
   - Ensure your user has "Read" permission

4. **Verify path in CARD_TYPE_MAP**
   - Should be just filename: `"cepas.hwg+"`
   - NOT full path

### "Configuration failed" or "Not successfully loaded"

**Problem**: Reader won't accept configuration.

**Solutions**:

1. **Check reader connection**
   ```bash
   python reader_config/ReaderConfigSDK.py about
   ```

2. **Try simpler config**
   ```bash
   # Test with built-in CEPAS config
   python reader_config/ReaderConfigSDK.py set-cepas
   ```

3. **Check RRMTool path**
   - Edit config.py
   - Verify `RRM_CLI` path is correct
   - Verify RRMTool is installed

4. **Try alternative method**
   ```bash
   # Method 1: Direct HID
   python reader_config/ReaderConfigSDK.py set-cepas
   
   # Method 2: RRMTool
   python reader_config/ReaderConfig.py load cepas.hwg+
   ```

### "Invalid card type"

**Problem**: Card type not recognized.

**Solution**:

```bash
# List available card types
python reader_config/ReaderConfigSDK.py set-card HELP
# OR check config.py CARD_TYPES dictionary
```

Valid types:
```
OFF, AWID, CARDAX, CASI_RUSCO, CDVI, CEPAS, COTAG,
DEISTER_UID, DESFIRE, EM, HID_ICLASS_CSN, HID_PROX,
HID_PROX_UID, ISO14443A, ISO14443B, ISO15693,
MIFARE_CSN, MIFARE_ULTRALIGHT_CSN
```

---

## Robot Arm

### "Arm won't move"

**Problem**: Robot arm doesn't respond to commands.

**Solutions**:

1. **Check power**
   - Power switch ON
   - LED indicators lit

2. **Check connection**
   ```bash
   python robot_testing/jog_control.py
   # Should show "✅ Connected"
   ```

3. **Check joints**
   - Move joints manually
   - Check for mechanical binding
   - Look for warning messages

4. **Reset robot**
   - Power off for 10 seconds
   - Power back on
   - Wait 30 seconds for startup

5. **Test individual joints**
   ```python
   from pymycobot.mycobot280 import MyCobot280
   import config
   
   mc = MyCobot280(config.ARM_PORT, 115200)
   # Move each joint slowly
   mc.send_angles([10, 0, 0, 0, 0, 0], 10)  # Joint 1 only
   time.sleep(2)
   print(mc.get_angles())
   mc.close()
   ```

### "Arm moving to wrong position"

**Problem**: Robot doesn't go where told.

**Solutions**:

1. **Check calibration**
   - Use position_recorder.py to re-record positions
   - May need mechanical recalibration

2. **Verify position data**
   ```bash
   # Check saved positions
   cat data/position_data/card_positions.txt
   ```

3. **Reduce speed**
   - Slow movement is more accurate
   - Edit config.py: `ARM_SPEED = 30` (was 65)

4. **Check for obstacles**
   - Ensure no obstacles in path
   - Clear workspace

### "Pump not working"

**Problem**: Pneumatic pump won't turn on/off.

**Solutions**:

1. **Check air pressure**
   - Air compressor powered on?
   - Check pressure gauge

2. **Check hose connections**
   - Verify hoses connected properly
   - Look for leaks

3. **Test pump directly**
   ```bash
   python robot_testing/jog_control.py
   # Press 'P' to toggle pump
   # Should hear pump kick on/off
   ```

4. **Check pin configuration**
   - Edit test_runner.py or position_recorder.py
   - Verify pin numbers in `set_basic_output()`

---

## Barcode Scanning

### "Barcode not detected in GUI"

**Problem**: GUI doesn't recognize barcode input.

**Solutions**:

1. **Test scanner with Notepad**
   - Open Notepad
   - Scan barcode
   - Should see characters typed
   - If nothing appears, scanner issue

2. **Check barcode format in CARD_TYPE_MAP**
   ```python
   # Must match barcode prefix
   CARD_TYPE_MAP = {
       "A005": {...},  # Looks for "A005" in barcode
   }
   ```

3. **Barcode format mismatch**
   - Scan barcode in Notepad to see exact format
   - Update CARD_TYPE_MAP accordingly

4. **Keyboard not captured**
   - Make sure GUI window is in focus
   - Click on the barcode input field first

5. **Disable other keyboard listeners**
   - Close other applications using keyboard input
   - (Some apps like hotkey tools can interfere)

### "Scanned barcode but not recognized"

**Problem**: Barcode scans but doesn't match card type.

**Solutions**:

1. **Check barcode prefix**
   - Scan barcode in Notepad
   - Check what's actually there
   - Update CARD_TYPE_MAP if needed

2. **Example fix**
   ```python
   # If barcode is "A005_CEPAS_001"
   # Add to CARD_TYPE_MAP:
   CARD_TYPE_MAP = {
       "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
   }
   # Because matching looks for "A005" substring
   ```

3. **Check for case sensitivity**
   ```python
   # Matching is case-sensitive by default
   # If needed, convert to uppercase:
   barcode.upper()
   ```

---

## GUI Issues

### "GUI won't start"

**Problem**: Can't launch gui.py.

**Solutions**:

1. **Check Tkinter**
   ```bash
   python -m tkinter
   # Should open a small window
   ```

   If it doesn't work:
   ```bash
   # Reinstall Python with Tkinter
   # During Python installation, make sure "tcl/tk" is checked
   ```

2. **Check other errors**
   ```bash
   python robot_testing/gui.py
   # Read error messages carefully
   ```

3. **Update config.py**
   - Make sure all imports work first
   - Test in Python REPL:
   ```bash
   python -c "import config; print('OK')"
   ```

### "GUI crashes on start"

**Problem**: GUI launches then crashes.

**Solutions**:

1. **Check imports**
   ```bash
   python -c "
   import tkinter
   import keyboard
   import subprocess
   print('All imports OK')
   "
   ```

2. **Check config.py errors**
   ```bash
   python -c "
   import config
   print(f'PROJECT_ROOT: {config.PROJECT_ROOT}')
   print(f'Paths OK: {len(config.PATHS)} paths')
   "
   ```

3. **Run with error output**
   ```bash
   python robot_testing/gui.py 2>&1
   # Copy error message
   ```

### "Buttons don't work"

**Problem**: GUI responds but buttons are unresponsive.

**Solutions**:

1. **Check for errors in console**
   - Run from command line
   - Look for error messages
   - Copy and search online

2. **Check reader/robot connection**
   - Test independently:
   ```bash
   python reader_config/ReaderConfigSDK.py about
   python robot_testing/jog_control.py
   ```

3. **Check file permissions**
   - Ensure config files are readable
   - Ensure log directory is writable

---

## Performance

### "Tests running slowly"

**Problem**: Test cycle takes too long.

**Solutions**:

1. **Reduce descent steps**
   - Edit config.py: `DESCENT_STEP = 5.0` (instead of 2.0)
   - Fewer positions = faster test

2. **Increase speed**
   - Edit config.py: `DESCENT_SPEED = 30` (instead of 20)

3. **Reduce read timeout**
   - Edit config.py: `READ_TIMEOUT = 0.1` (instead of 0.15)
   - Reader responds faster

4. **Optimize positions**
   - Use position_recorder.py to find optimal approach
   - Fewer positions = fewer movements

### "Random test failures"

**Problem**: Tests sometimes fail without clear reason.

**Solutions**:

1. **Check reader connection**
   - Might be flaky USB connection
   - Try different USB port
   - Check cable

2. **Check for timeout issues**
   - Increase READ_TIMEOUT in config.py
   - `READ_TIMEOUT = 0.2` (instead of 0.15)

3. **Check robot calibration**
   - Re-record positions with position_recorder.py
   - Mechanical drift is common

4. **Check environmental factors**
   - RF interference?
   - Temperature extremes?
   - Humidity?

---

## Getting Help

### Collect Debug Info

When reporting issues, collect:

```bash
# Check Python version
python --version

# Check imports
python -c "
import hidapi
import keyboard
import PyMyCobotCOBOT
print('All dependencies OK')
"

# Check reader
python reader_config/ReaderConfigSDK.py about

# Check robot
python -c "
from pymycobot.mycobot280 import MyCobot280
import config
mc = MyCobot280(config.ARM_PORT, 115200)
print(mc.get_angles())
mc.close()
"

# Check config
python -c "import config; print(config.PROJECT_ROOT)"
```

### Check Logs

All issues logged to:
- `logs/test_results.txt` — Test failures
- `logs/rrm_tool.log` — Reader errors
- `logs/positions.txt` — Robot position issues

### Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError` | Missing library | `pip install <library>` |
| `Connection refused` | Port already in use | Close other apps |
| `File not found` | Wrong path | Check config.py |
| `Permission denied` | File locked | Close file, try again |
| `Timeout` | Device not responding | Power cycle device |

---

**Version**: 1.0  
**Last Updated**: 2025
