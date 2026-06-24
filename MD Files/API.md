# API Reference — RF IDEAS Automation

Developer reference for the automation system.

---

## Table of Contents

1. [Config Module](#config-module)
2. [Reader Module](#reader-module)
3. [Robot Module](#robot-module)
4. [Barcode Scanner](#barcode-scanner)

---

## Config Module

### Location
`Automation/config.py`

### Functions

#### `ensure_paths_exist()`

Creates all required directories if they don't exist.

```python
import config
config.ensure_paths_exist()
```

#### `get_config_path(filename)`

Returns full path to a reader config file.

```python
path = config.get_config_path("cepas.hwg+")
# Returns: C:\...\Automation\reader_config\configs\cepas.hwg+
```

#### `get_log_path(filename)`

Returns full path to a log file.

```python
log_path = config.get_log_path("test_results.txt")
# Returns: C:\...\Automation\logs\test_results.txt
```

### Constants

#### Paths Dictionary

```python
config.PATHS = {
    'reader_config': '...',     # Reader config directory
    'configs': '...',           # HWG config files
    'barcode_scanner': '...',   # Scanner utilities
    'robot_testing': '...',     # Robot control
    'data': '...',              # Test data
    'positions': '...',         # Position recordings
    'logs': '...',              # Log files
}
```

#### Robot Settings

```python
config.ARM_PORT = "COM3"                    # Serial port
config.ARM_SPEED = 65                       # Movement speed
config.DESCENT_SPEED = 20                   # Slow descent speed
config.DESCENT_STEP = 2.0                   # mm per step
config.DESCENT_DELAY = 0.2                  # Seconds between steps
config.READ_TIMEOUT = 0.15                  # Seconds to wait
config.CARD_THICKNESS = 0.76                # Card thickness mm
config.DESCENT_APPROACH_OFFSET = 50.0       # Approach distance
```

#### Descent Configuration

```python
config.DESCENT_RANGES = {
    4: 9,      # Position 5 to 10 (flat tap)
    11: 16,    # Position 12 to 17 (90° tap)
}

config.BARCODE_WAVE = (17, 18)  # Scan positions
config.STACK_TOP_IDX = 0        # Pick start
config.STACK_BTM_IDX = 1        # Pick end
config.DROP_IDX = 19            # Drop position
```

#### Card Type Mapping

```python
config.CARD_TYPE_MAP = {
    "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
    "B005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
}
```

#### Card Types

```python
config.CARD_TYPES = {
    "OFF": 0x0000,
    "AWID": 0xFA02,
    "CEPAS": 0x7A01,
    "HID_PROX": 0xEF04,
    # ... 18 total types
}

config.VENDOR_ID = 0x0C27
config.PRODUCT_ID = 0x3BFA
```

#### Colors

```python
config.COLORS = {
    'red': "#FF0000",
    'dark': "#1A1A1A",
    'gray': "#595959",
    'light': "#EEEEEE",
    'white': "#FFFFFF",
    'border': "#B7B7B7",
}
```

---

## Reader Module

### ReaderConfigSDK

Location: `Automation/reader_config/ReaderConfigSDK.py`

#### Class: Reader

```python
from reader_config.ReaderConfigSDK import Reader

reader = Reader()
```

##### Methods

**`open()`**

Open connection to reader.

```python
if reader.open():
    print("Connected")
else:
    print("Failed")
```

Returns: `bool` — Success status

**`close()`**

Close reader connection.

```python
reader.close()
```

**`get_luid()`**

Get reader LUID (Logical Unit ID) and firmware version.

```python
luid, fw = reader.get_luid()
print(f"LUID: {luid}, Firmware: {fw}")
# Output: LUID: 65535, Firmware: 144.2.0.2
```

Returns: `tuple` — (luid: int, firmware: str)

**`get_config_number()`**

Get active configuration info.

```python
active, total, card_type, priority = reader.get_config_number()
print(f"Config {active} of {total}, Card type: {card_type:#06x}")
```

Returns: `tuple` — (active: int, total: int, card_type: int, priority: int)

**`beep(count=1, long_beep=False)`**

Make reader beep.

```python
reader.beep(1)              # 1 short beep
reader.beep(3)              # 3 short beeps
reader.beep(2, long_beep=True)  # 2 long beeps
```

**`read_all()`**

Read all 40 bytes of configuration.

```python
config_data = reader.read_all()
if config_data:
    print(f"Config: {config_data.hex()}")
```

Returns: `bytearray` — 40-byte config (or None)

**`write_all(data)`**

Write 40-byte configuration.

```python
config_data = bytearray(40)
# ... set config bytes ...
if reader.write_all(config_data):
    print("Config written")
```

**`write_flash()`**

Save configuration to flash memory.

```python
reader.write_flash()
print("Saved to flash")
```

### ReaderConfig

Location: `Automation/reader_config/ReaderConfig.py`

Command-line tool for RRMTool_CLI integration.

```bash
python reader_config/ReaderConfig.py about
python reader_config/ReaderConfig.py read
python reader_config/ReaderConfig.py save config.hwg
python reader_config/ReaderConfig.py load config.hwg
```

---

## Robot Module

### Robot Control

Uses `PyMyCobotCOBOT` library.

```python
from pymycobot.mycobot280 import MyCobot280
import config

mc = MyCobot280(config.ARM_PORT, 115200)
```

#### Common Methods

**`send_angles(angles, speed)`**

Move to angles.

```python
# angles: [J1, J2, J3, J4, J5, J6] in degrees
mc.send_angles([0, 0, 0, 0, 0, 0], config.ARM_SPEED)
time.sleep(1)  # Wait for movement
```

**`get_angles()`**

Get current joint angles.

```python
angles = mc.get_angles()
print(f"Position: {angles}")
```

Returns: `list` — [J1, J2, J3, J4, J5, J6] angles

**`send_coords(coords, speed)`**

Move to Cartesian coordinates.

```python
# coords: [X, Y, Z, Rx, Ry, Rz]
mc.send_coords([200, 100, 150, 0, 0, 0], config.ARM_SPEED)
```

**`get_coords()`**

Get current position.

```python
coords = mc.get_coords()
print(f"Position: {coords}")
```

**`set_basic_output(pin, level)`**

Control I/O pins (pump, gripper).

```python
mc.set_basic_output(5, 0)   # Turn ON
mc.set_basic_output(5, 1)   # Turn OFF
```

**`close()`**

Close connection.

```python
mc.close()
```

### Example Workflow

```python
from pymycobot.mycobot280 import MyCobot280
import config
import time

# Connect
mc = MyCobot280(config.ARM_PORT, 115200)

# Home position
mc.send_angles([0, 0, 0, 0, 0, 0], config.ARM_SPEED)
time.sleep(2)

# Move to test position
mc.send_angles([0, 45, 30, 30, 0, 0], config.ARM_SPEED)
time.sleep(1)

# Get position
pos = mc.get_angles()
print(f"At: {pos}")

# Clean up
mc.close()
```

---

## Barcode Scanner

### Detection (GUI)

The GUI automatically captures barcode scanner input via keyboard events.

```python
from tkinter import Tk

class BarcodeListener:
    def __init__(self, callback):
        self.callback = callback      # Called when barcode scanned
        self.buf = ""
        self.active = False
    
    def start(self):
        """Start listening for barcode input"""
        # Uses keyboard.hook() to capture input
    
    def stop(self):
        """Stop listening"""
```

### Manual Barcode Processing

```python
def process_barcode(barcode):
    """Match barcode to card type"""
    import config
    
    for prefix, card_info in config.CARD_TYPE_MAP.items():
        if prefix in barcode:
            return card_info
    
    return None

# Usage
card = process_barcode("A005_123456")
if card:
    print(f"Found: {card['name']}")
    print(f"Config: {card['hwg']}")
```

---

## Test Runner

Location: `Automation/robot_testing/test_runner.py`

### Key Functions

```python
def find_file(filename):
    """Find file in multiple locations"""
    
def load_positions(filename):
    """Load recorded positions from file"""
    
def run_descent_test(reader, start_pos, descent_range, reader_id, barcode, cond):
    """Run descent test for a position range"""
    
def save_results(filename, results):
    """Save test results to file"""
```

### Example

```python
from robot_testing.test_runner import *
import config

# Load positions
positions = load_positions("card_positions.txt")

# Run test
results = run_descent_test(
    reader=reader,
    start_pos=positions[4],      # Position 5
    descent_range=(4, 9),         # Descent positions
    reader_id="RDR_001",
    barcode="A005",
    cond="TC1"
)

# Save results
save_results("test_results.txt", results)
```

---

## GUI Module

Location: `Automation/robot_testing/gui.py`

### Main Class: TestGUI

```python
import tkinter as tk
from robot_testing.gui import TestGUI

root = tk.Tk()
gui = TestGUI(root)
root.mainloop()
```

### Layout

- **Header** — Title and version
- **Left Panel** — Controls (test selection, logging)
- **Right Panel** — Reader info, status, results

---

## Example Scripts

### Script 1: Quick Test

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, 'Automation')

import config
from reader_config.ReaderConfigSDK import Reader

# Setup
config.ensure_paths_exist()
reader = Reader()

# Test reader
if reader.open():
    luid, fw = reader.get_luid()
    print(f"✅ Reader OK: LUID={luid}, FW={fw}")
    reader.close()
else:
    print("❌ Reader connection failed")
```

### Script 2: Configure and Test

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, 'Automation')

import config
from reader_config.ReaderConfigSDK import Reader, build_cepas_config

# Setup
reader = Reader()
if not reader.open():
    print("❌ Failed to open reader")
    exit(1)

# Configure for CEPAS
config_data = build_cepas_config()
if reader.write_all(config_data):
    reader.write_flash()
    print("✅ CEPAS configuration written")
else:
    print("❌ Configuration failed")

reader.close()
```

### Script 3: Robot Positioning

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, 'Automation')

import config
import time
from pymycobot.mycobot280 import MyCobot280

# Connect
mc = MyCobot280(config.ARM_PORT, 115200)

# Move through positions
positions = [
    [0, 0, 0, 0, 0, 0],
    [0, 30, 30, 30, 0, 0],
    [0, 45, 45, 45, 0, 0],
]

for i, pos in enumerate(positions):
    print(f"Moving to position {i+1}...")
    mc.send_angles(pos, config.ARM_SPEED)
    time.sleep(2)
    current = mc.get_angles()
    print(f"  Current: {current}")

mc.close()
```

---

## Error Handling

### Reader Errors

```python
try:
    reader.open()
    if not reader.open():
        print("Failed to open reader")
        # Reader not found or not responding
except Exception as e:
    print(f"Error: {e}")
    # USB communication error
```

### Robot Errors

```python
try:
    mc = MyCobot280(config.ARM_PORT, 115200)
except Exception as e:
    print(f"Failed to connect: {e}")
    # Port doesn't exist or robot not powered
```

### File Errors

```python
import os
config_file = config.get_config_path("cepas.hwg+")
if not os.path.exists(config_file):
    print(f"Config not found: {config_file}")
```

---

## Version History

- **1.0** (2025-06) — Initial release

---

**Last Updated**: 2025
