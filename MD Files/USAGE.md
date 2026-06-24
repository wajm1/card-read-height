# Usage Guide — RF IDEAS Automation System

Complete guide to using the automated credential testing system.

---

## Quick Start (2 minutes)

```bash
cd "C:\Users\wmahmood\OneDrive - rfIDEAS\Documents\Testing\Automation"
python robot_testing/gui.py
```

1. Select test condition
2. Scan card barcode
3. Click "Start Test"
4. Wait for completion
5. Results saved to `logs/test_results.txt`

---

## GUI Application

### Launch

```bash
python robot_testing/gui.py
```

### Screen Layout

```
╔════════════════════════════════════════════════════════╗
║  RF IDEAS — Credential Read Height Test                ║
╠════════════════════════════════════════════════════════╣
║                                                        ║
║  TEST CONFIGURATION                                    ║
║  ┌─ Test Condition ──────────────────────────────────┐ ║
║  │ [TC1 — Inline 0°                               ▼] │ ║
║  └────────────────────────────────────────────────────┘ ║
║                                                        ║
║  BARCODE SCANNING                                      ║
║  ┌─ Scan Card Barcode ───────────────────────────────┐ ║
║  │ [Ready to scan...]                                 │ ║
║  └────────────────────────────────────────────────────┘ ║
║                                                        ║
║  READER STATUS                                         ║
║  ✅ Reader: Ready                                      ║
║  ✅ ARM: Ready                                         ║
║  ⏳ Card: Waiting for scan                            ║
║                                                        ║
║  CONTROLS                                              ║
║  [Start Test]  [Clear]  [Exit]                         ║
║                                                        ║
║  OUTPUT LOG                                            ║
║  ┌────────────────────────────────────────────────────┐ ║
║  │ Waiting for barcode scan...                        │ ║
║  │                                                    │ ║
║  └────────────────────────────────────────────────────┘ ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
```

### Workflow

#### 1. Select Test Condition

```
Options:
  • TC1 — Inline 0°           (Card flat, direct approach)
  • TC2 — Inline 180°         (Card flat, opposite approach)
  • TC3 — Orthogonal 0°       (Card perpendicular, approach 1)
  • TC4 — Orthogonal 90°      (Card perpendicular, approach 2)
  • All 4 conditions          (Run all 4 in sequence)
```

#### 2. Scan Card Barcode

```
• Position barcode scanner near GUI window
• Scan the credential's barcode
• System auto-detects card type
• Reader auto-configures
```

Expected output:
```
✅ Barcode detected: A005
✅ Card type: CEPAS
✅ Configuration loaded
✅ Ready to test
```

#### 3. Start Test

```
• Click "Start Test" button
• Robot arm will:
  - Move to start position
  - Approach reader
  - Step down slowly (2mm per step)
  - Record reads at each height
  - Return to safe position
```

#### 4. View Results

```
Results saved to:
  logs/test_results.txt

Format:
  Card ID: A005
  Card Type: CEPAS
  Test Condition: TC1 — Inline 0°
  Height: 10mm | Read: YES
  Height: 8mm  | Read: YES
  Height: 6mm  | Read: NO
  ...
```

### Controls

**Buttons:**
- **Start Test** — Begin test cycle
- **Clear** — Clear log window
- **Exit** — Save results and exit

**Keyboard:**
- **Esc** — Emergency stop (stops robot immediately)
- **Enter** — Confirm scan (if manual entry)

---

## Command Line Tools

### Reader Configuration

#### View Reader Information

```bash
python reader_config/ReaderConfigSDK.py about
```

Output:
```
✅ Reader opened: 0xc27:0x3bfa
==================================================
READER INFO
==================================================
  VID:PID          : 0xc27:0x3bfa
  LUID             : 65535 / 0xFFFF
  Firmware         : 144.2.0.2
  Active config    : 4 of 4
  Active card type : 0x0000 (OFF)
  Card priority    : 0
```

#### Configure for CEPAS

```bash
python reader_config/ReaderConfigSDK.py set-cepas
```

#### Make Reader Beep

```bash
# 1 beep
python reader_config/ReaderConfigSDK.py beep 1

# 3 long beeps
python reader_config/ReaderConfigSDK.py beep 3
```

#### Set Specific Card Type

```bash
python reader_config/ReaderConfigSDK.py set-card CEPAS
python reader_config/ReaderConfigSDK.py set-card HID_PROX
python reader_config/ReaderConfigSDK.py set-card ISO14443A
```

Available types: `OFF`, `AWID`, `CARDAX`, `CASI_RUSCO`, `CDVI`, `CEPAS`, `COTAG`, `DEISTER_UID`, `DESFIRE`, `EM`, `HID_ICLASS_CSN`, `HID_PROX`, `HID_PROX_UID`, `ISO14443A`, `ISO14443B`, `ISO15693`, `MIFARE_CSN`, `MIFARE_ULTRALIGHT_CSN`

#### Read Current Configuration

```bash
python reader_config/ReaderConfig.py read
```

#### Save Configuration to File

```bash
python reader_config/ReaderConfig.py save my_config.hwg
```

#### Load Configuration from File

```bash
python reader_config/ReaderConfig.py load my_config.hwg
```

### Robot Control

#### Manual Jog Control

```bash
python robot_testing/jog_control.py
```

**Controls:**
```
UP    = Move arm up (J2 increases)
DOWN  = Move arm down (J2 decreases)
LEFT  = Rotate head left (J6)
RIGHT = Rotate head right (J6)
A/D   = Rotate base (J1)
W/S   = Move lower arm (J2)
R/F   = Move middle arm (J3)
T/G   = Move upper arm (J4)

+/-   = Increase/decrease step size
P     = Toggle pump (on/off)
H     = Home position
Q     = Quit
```

#### Record Positions

```bash
python robot_testing/position_recorder.py
```

**Controls:**
```
A/D        = Base rotate (J1)
W/S        = Lower arm (J2)
R/F        = Middle arm (J3)
T/G        = Upper arm (J4)
LEFT/RIGHT = Head tilt (J5)
UP/DOWN    = Head rotate (J6)

SPACE = Save current position
N     = Rename last position
U     = Undo last position
V     = List all positions
H     = Home position
ESC   = Save all and exit
```

Positions saved to: `data/position_data/card_positions.txt`

#### Run Tests

```bash
python robot_testing/test_runner.py
```

---

## Python API (For Developers)

### Import Configuration

```python
import sys
sys.path.insert(0, 'C:\\Users\\wmahmood\\OneDrive - rfIDEAS\\Documents\\Testing\\Automation')
import config

# Access settings
print(config.ARM_PORT)           # "COM3"
print(config.PATHS['configs'])  # Path to configs
print(config.CARD_TYPE_MAP)     # Barcode mappings
```

### Reader Control

```python
from reader_config.ReaderConfigSDK import Reader

reader = Reader()
if reader.open():
    luid, fw = reader.get_luid()
    print(f"Firmware: {fw}")
    reader.beep(1)
    reader.close()
```

### Robot Control

```python
from pymycobot.mycobot280 import MyCobot280
import config

mc = MyCobot280(config.ARM_PORT, 115200)
mc.send_angles([0, 0, 0, 0, 0, 0], config.ARM_SPEED)  # Move to home
angles = mc.get_angles()  # Get current position
mc.close()
```

---

## Workflow Examples

### Example 1: Test Multiple Cards

```bash
# Card 1: CEPAS
echo "A005" | python robot_testing/test_runner.py

# Card 2: HID
echo "HID26" | python robot_testing/test_runner.py

# Card 3: ISO
echo "ISO1" | python robot_testing/test_runner.py
```

### Example 2: Custom Test Script

```python
import sys
sys.path.insert(0, 'Automation')

import config
from reader_config.ReaderConfigSDK import Reader
from pymycobot.mycobot280 import MyCobot280

# Setup
reader = Reader()
robot = MyCobot280(config.ARM_PORT, 115200)

# Configure for CEPAS
reader.open()
reader.beep(1)

# Move to start
robot.send_angles([0, 0, 0, 0, 0, 0], config.ARM_SPEED)

# Run test...
# ...

reader.close()
robot.close()
```

---

## Common Tasks

### Add New Test Condition

Edit `config.py`:

```python
TEST_CONDITIONS = [
    "TC1 — Inline 0°",
    "TC2 — Inline 180°",
    "TC3 — Orthogonal 0°",
    "TC4 — Orthogonal 90°",
    "TC5 — My New Condition",    # Add this
    "All 4 conditions",
]
```

### Change Robot Speed

Edit `config.py`:

```python
ARM_SPEED = 65  # Change to 30-100
```

### Change Robot Port

Edit `config.py`:

```python
ARM_PORT = "COM3"  # Change to COM4, COM5, etc.
```

### Add New Card Type

1. Get `.hwg+` configuration file from reader admin
2. Save to `reader_config/configs/my_card.hwg+`
3. Edit `config.py`:

```python
CARD_TYPE_MAP = {
    "A005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
    "B005": {"name": "CEPAS", "hwg": "cepas.hwg+"},
    "MY01": {"name": "My Card", "hwg": "my_card.hwg+"},  # Add this
}
```

---

## Performance Tips

1. **Pre-record positions** — Use position recorder to save optimal test positions
2. **Batch tests** — Run multiple cards in succession for efficiency
3. **Monitor temperatures** — Check robot arm temp if running many tests
4. **Calibrate regularly** — Re-record positions periodically for accuracy

---

## Data Output

### Test Results File

Location: `logs/test_results.txt`

Format:
```
=====================================
TEST RESULTS
=====================================
Date: 2025-06-09 11:30:45
Card ID: A005
Card Type: CEPAS
Test Condition: TC1 — Inline 0°
Barcode: A005_CEPAS

Height (mm) | Status
============|=======
50          | NO READ
40          | NO READ
30          | NO READ
20          | READ
15          | READ
10          | READ
5           | READ
0           | ERROR

Summary:
  Read height range: 5-20mm
  Success rate: 75%
  ✅ Test completed successfully
```

### Position Data File

Location: `data/position_data/card_positions.txt`

Format:
```
Position #1: [0.0, 30.0, 45.0, 45.0, 0.0, 0.0]
Position #2: [0.0, 35.0, 40.0, 40.0, 0.0, 0.0]
Position #3: [0.0, 40.0, 35.0, 35.0, 0.0, 0.0]
...
```

---

## Logs

### Error Logs

Location: `logs/rrm_tool.log`

Contains RRMTool_CLI output and reader errors.

### Position Logs

Location: `logs/positions.txt`

Contains robot position tracking data.

---

## Keyboard Shortcuts

| Key | Function |
|-----|----------|
| Esc | Emergency stop |
| Q | Quit application |
| P | Toggle pump |
| H | Home position |
| Space | Save position |
| V | View positions |

---

**Version**: 1.0  
**Last Updated**: 2025
