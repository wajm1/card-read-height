#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ReaderConfigSDK.py
Author: Alfredo Romero Perez
Direct USB HID reader configuration using rf IDEAS SDK.
No RRMTool_CLI required.

Usage:
  python ReaderConfigSDK.py read
  python ReaderConfigSDK.py set-cepas
  python ReaderConfigSDK.py set-card <card_type_name>
  python ReaderConfigSDK.py about
  python ReaderConfigSDK.py beep [count]

Requires: pip install hid
Place in same folder as readerUsb.py, readerConfig.py, defaultConfig.py
"""

import sys
import os
import struct
import io

# Fix encoding for Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Import from centralized config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CARD_TYPES, VENDOR_ID, PRODUCT_ID

# ============================================================
# USB HID READER CLASS (inline from readerUsb.py)
# ============================================================
try:
    import hid
    HID_AVAILABLE = True
except ImportError:
    HID_AVAILABLE = False
    print("⚠️  'hid' library not installed. Run: pip install hid")

class Reader:
    def __init__(self):
        self.device = None

    def open(self):
        if not HID_AVAILABLE:
            return False
        try:
            self.device = hid.device()
            self.device.open(VENDOR_ID, PRODUCT_ID)
            print(f"✅ Reader opened: {hex(VENDOR_ID)}:{hex(PRODUCT_ID)}")
            return True
        except Exception as e:
            print(f"❌ Could not open reader: {e}")
            return False

    def close(self):
        if self.device:
            self.device.close()

    def _set_report(self, report):
        try:
            self.device.send_feature_report(report)
            return True
        except Exception as e:
            print(f"❌ send_feature_report error: {e}")
            return False

    def _get_report(self):
        try:
            return self.device.get_feature_report(0x00, 9)
        except Exception as e:
            print(f"❌ get_feature_report error: {e}")
            return None

    def get_block(self, command):
        """Read one 8-byte config block. command = 0x80..0x84"""
        report = bytearray([0x00, command, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        data = self._get_report()
        if data:
            return bytearray(data[1:9])
        return None

    def set_block(self, command, block):
        """Write one 8-byte config block."""
        report = bytearray([0x00, command, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        setData = bytearray(9)
        setData[0] = 0x00
        for i in range(8):
            setData[i+1] = block[i]
        self._set_report(setData)

    def read_all(self):
        """Read all 5 blocks (40 bytes) of config."""
        result = bytearray(40)
        for i in range(5):
            block = self.get_block(0x80 + i)
            if block is None:
                print(f"❌ Failed to read block {i+1}")
                return None
            result[i*8:(i+1)*8] = block
        return result

    def write_all(self, data):
        """Write all 5 blocks (40 bytes) of config."""
        if len(data) != 40:
            print("❌ Config must be 40 bytes")
            return False
        for i in range(5):
            self.set_block(0x80 + i, data[i*8:(i+1)*8])
        return True

    def write_flash(self):
        """Persist config to flash memory."""
        report = bytearray([0x00, 0x90, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        print("💾 Written to flash")

    def beep(self, count=1, long_beep=False):
        if long_beep:
            count = min(count, 2) | 0x80
        else:
            count = min(count, 5)
        report = bytearray([0x00, 0x8C, 0x03, count, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        self._get_report()

    def get_luid(self):
        report = bytearray([0x00, 0x8A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        data = self._get_report()
        if data:
            luid = data[1] | (data[2] << 8)
            fw   = f"{data[3]}.{data[4]}.{data[5]}.{data[6]}"
            return luid, fw
        return None, None

    def get_config_number(self):
        report = bytearray([0x00, 0x89, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self._set_report(report)
        data = self._get_report()
        if data:
            active = data[3]
            total  = data[4]
            ct     = data[6] | (data[7] << 8)
            prio   = data[8]
            return active, total, ct, prio
        return None, None, None, None

# ============================================================
# CONFIG BUILDER
# ============================================================

def build_cepas_config():
    """Build 40-byte CEPAS default config from defaultConfig.py values."""
    data = bytearray(40)
    # Block 1
    data[0]  = 0x03   # fac digits
    data[1]  = 0x05   # id digits
    data[2]  = 0x00   # strip parity
    data[3]  = 0x40   # id field bit count (64)
    data[4]  = 0x40   # only read bit count (64)
    data[5]  = 0xB3   # fac id delimiter char
    data[6]  = 0x28   # termination char (Enter)
    data[7]  = 0x10   # send ID off, send FAC off, split format on
    # Block 2
    data[8]  = 0x00
    data[9]  = 0x14   # wiegand timeout (20ms)
    data[10] = 0x14   # hold time (20ms)
    data[11] = 0x18   # lockout time (24 * 50ms = 1200ms)
    data[12] = 0x05   # key press time (20ms)
    data[13] = 0x05   # key release time (20ms)
    data[14] = 0x42   # ID extended precision math ON + extended FAC/ID hex capable
    data[15] = 0xE0
    # Block 3
    data[16] = 0x00
    data[17] = 0x98   # invert wiegand bits ON, beeper ON
    data[18] = 0x00
    data[19] = 0x00
    data[20] = 0x00
    data[21] = 0x00
    data[22] = 0x00
    data[23] = 0x00
    # Block 4
    data[24] = 0x00
    data[25] = 0x00
    data[26] = 0x00
    data[27] = 0x00
    data[28] = 0x00
    data[29] = 0x00
    data[30] = 0x00
    data[31] = 0x00
    # Block 5 — card type CEPAS = 0x7A01
    data[32] = 0x00   # card disable = off
    struct.pack_into('<H', data, 33, 0x7A01)  # card type = CEPAS
    data[35] = 0x00   # card priority = low
    data[36] = 0x00
    data[37] = 0x00
    data[38] = 0x00
    data[39] = 0x00
    return data

def build_config_for_card(card_type_hex):
    """Build generic 40-byte config for any card type."""
    data = bytearray(40)
    data[0]  = 0x03
    data[1]  = 0x05
    data[2]  = 0x00
    data[3]  = 0x40
    data[4]  = 0x40
    data[5]  = 0xB3
    data[6]  = 0x28
    data[7]  = 0x10
    data[8]  = 0x00
    data[9]  = 0x14
    data[10] = 0x14
    data[11] = 0x18
    data[12] = 0x05
    data[13] = 0x05
    data[14] = 0x42
    data[15] = 0xE0
    data[16] = 0x00
    data[17] = 0x98
    data[18:32] = bytes(14)
    data[32] = 0x00
    struct.pack_into('<H', data, 33, card_type_hex)
    data[35] = 0x00
    data[36:40] = bytes(4)
    return data

# ============================================================
# DISPLAY HELPERS
# ============================================================

def card_type_name(ct):
    for name, val in CARD_TYPES.items():
        if val == ct:
            return name
    return f"Unknown (0x{ct:04X})"

def print_config(data):
    """Pretty-print 40-byte config."""
    ct   = struct.unpack_from('<H', data, 33)[0]
    prio = data[35]

    print(f"\n  Card Type        : 0x{ct:04X} ({card_type_name(ct)})")
    print(f"  Card Priority    : {prio}")
    print(f"  ID field bits    : {data[3]}")
    print(f"  Read bits        : {data[4]}")
    print(f"  Parity strip     : {data[2]}")
    print(f"  Termination char : 0x{data[6]:02X} ({'Enter' if data[6]==0x28 else data[6]})")
    print(f"  Hold time        : {data[10] * 50}ms")
    print(f"  Lockout time     : {data[11] * 50}ms")
    print(f"  Key press time   : {data[12] * 4}ms")
    print(f"  Key release time : {data[13] * 4}ms")
    # Block 2 byte 6 flags
    b2b6 = data[14]
    print(f"  ID ext precision : {'ON' if b2b6 & 0x02 else 'OFF'}")
    print(f"  Output hex       : {'ON' if b2b6 & 0x10 else 'OFF'}")
    # Block 3 byte 1 flags
    b3b1 = data[17]
    print(f"  Invert Wiegand   : {'ON' if b3b1 & 0x08 else 'OFF'}")
    print(f"  Beeper           : {'ON' if b3b1 & 0x10 else 'OFF'}")
    print(f"  Block 1 byte 7   : 0x{data[7]:02X}")
    send_id  = (data[7] >> 2) & 1
    send_fac = (data[7] >> 3) & 1
    print(f"  Send ID          : {'ON' if send_id else 'OFF'}")
    print(f"  Send FAC         : {'ON' if send_fac else 'OFF'}")
    print()
    print(f"  Raw bytes: {' '.join(f'{b:02X}' for b in data)}")

# ============================================================
# COMMANDS
# ============================================================

def cmd_about(reader):
    luid, fw = reader.get_luid()
    active, total, ct, prio = reader.get_config_number()
    print("="*50)
    print("READER INFO")
    print("="*50)
    print(f"  VID:PID          : {hex(VENDOR_ID)}:{hex(PRODUCT_ID)}")
    if luid is not None:
        print(f"  LUID             : {luid} / 0x{luid:04X}")
        print(f"  Firmware         : {fw}")
    if active is not None:
        print(f"  Active config    : {active+1} of {total}")
        print(f"  Active card type : 0x{ct:04X} ({card_type_name(ct)})")
        print(f"  Card priority    : {prio}")

def cmd_read(reader):
    print("="*50)
    print("CURRENT READER CONFIGURATION")
    print("="*50)
    data = reader.read_all()
    if data:
        print_config(data)
    else:
        print("❌ Could not read config")

def cmd_set_cepas(reader):
    print("⚙️  Applying CEPAS configuration...")
    config = build_cepas_config()
    print("  Config to write:")
    print_config(config)
    confirm = input("Write this config to reader? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled")
        return
    if reader.write_all(config):
        reader.write_flash()
        reader.beep(2, False)
        print("✅ CEPAS config applied and saved")
    else:
        print("❌ Failed to write config")

def cmd_set_card(reader, card_name):
    card_name = card_name.upper()
    if card_name not in CARD_TYPES:
        print(f"❌ Unknown card type: {card_name}")
        print(f"   Available: {', '.join(CARD_TYPES.keys())}")
        return
    ct = CARD_TYPES[card_name]
    print(f"⚙️  Applying {card_name} (0x{ct:04X}) configuration...")
    config = build_config_for_card(ct)
    print_config(config)
    confirm = input("Write this config to reader? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Cancelled")
        return
    if reader.write_all(config):
        reader.write_flash()
        reader.beep(2, False)
        print(f"✅ {card_name} config applied and saved")
    else:
        print("❌ Failed to write config")

def cmd_beep(reader, count=2):
    reader.beep(count, False)
    print(f"🔔 Beeped {count}x")

def print_usage():
    print("""
rf IDEAS Reader Config (SDK direct)
=====================================
  python ReaderConfigSDK.py about
  python ReaderConfigSDK.py read
  python ReaderConfigSDK.py set-cepas
  python ReaderConfigSDK.py set-card <card_type>
  python ReaderConfigSDK.py beep [count]

Card types: """ + ", ".join(CARD_TYPES.keys()))

# ============================================================
# MAIN
# ============================================================

if not HID_AVAILABLE:
    print("Install hid library first: pip install hid")
    sys.exit(1)

args = sys.argv[1:]
if not args:
    print_usage()
    sys.exit(0)

reader = Reader()
if not reader.open():
    print("❌ Could not connect to reader — check USB connection")
    sys.exit(1)

try:
    cmd = args[0].lower()
    if   cmd == 'about':    cmd_about(reader)
    elif cmd == 'read':     cmd_read(reader)
    elif cmd == 'set-cepas':cmd_set_cepas(reader)
    elif cmd == 'set-card':
        if len(args) < 2:
            print("❌ Usage: set-card <card_type>")
        else:
            cmd_set_card(reader, args[1])
    elif cmd == 'beep':
        count = int(args[1]) if len(args) > 1 else 2
        cmd_beep(reader, count)
    else:
        print(f"❌ Unknown command: {cmd}")
        print_usage()
finally:
    reader.close()
