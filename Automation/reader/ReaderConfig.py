#!/usr/bin/env python3
"""
config_on_scan.py — Scan a barcode, look up the card, configure the reader.

No robot, no GUI. Loops: scan a card -> reader gets configured -> scan the next.
Press Ctrl+C to quit.

Place anywhere in the Automation project (root or a subfolder) and run with:
    python config_on_scan.py
"""

import os
import sys
import threading

# Make the project importable whether this file sits in the root or a subfolder.
_here = os.path.dirname(os.path.abspath(__file__))
for p in (_here, os.path.dirname(_here)):
    if p not in sys.path:
        sys.path.insert(0, p)

from barcode.scanner import BarcodeListener, lookup_card
from reader.cli import configure_reader_for_card


def on_barcode(barcode):
    print("\n>> Barcode: {}".format(barcode))
    card = lookup_card(barcode)
    if not card:
        print("   Unknown barcode — not in the card map. Skipping.")
        print(">> Ready — scan the next card (Ctrl+C to quit).")
        return

    print("   Card: {}".format(card.get("name", "?")))
    print("   Configuring reader...")
    try:
        ok = configure_reader_for_card(card, log_fn=print)
    except TypeError:
        ok = configure_reader_for_card(card)
    print("   Reader configured." if ok else "   Reader configuration FAILED.")
    print(">> Ready — scan the next card (Ctrl+C to quit).")


def main():
    listener = BarcodeListener(on_barcode)
    listener.start()
    print(">> Ready — scan a card barcode (Ctrl+C to quit).")
    try:
        threading.Event().wait()      # idle until Ctrl+C; scans handled in callback
    except KeyboardInterrupt:
        print("\n>> Quitting.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()