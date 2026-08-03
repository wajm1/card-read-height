#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""
ReaderConfig.py — Scan a barcode, look up the card, configure the reader.

Role
    Standalone loop with no robot and no GUI: each scanned barcode is looked up
    in ``files/AllCards.csv`` and the matching HWG under ``files/hwg/`` is
    loaded via RRMTool CLI.

Inputs / side effects
    USB barcode wedge; RRMTool_CLI configure. Ctrl+C to quit.

Run from Automation/::

    python reader/ReaderConfig.py
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from barcode.scanner import BarcodeListener, lookup_card
from reader.cli import configure_reader_for_card, check_reader


def _log(msg, tag="info"):
    print(msg)


def on_barcode(barcode):
    print(f"\n>> Barcode: {barcode}")
    card = lookup_card(barcode)
    if not card:
        print("   Unknown barcode — not in AllCards.csv. Skipping.")
        print(">> Ready — scan the next card (Ctrl+C to quit).")
        return

    print(f"   Card: {card.get('name', '?')}")
    print("   Configuring reader...")
    ok = configure_reader_for_card(card, log_fn=_log)
    print("   Reader configured." if ok else "   Reader configuration FAILED.")
    print(">> Ready — scan the next card (Ctrl+C to quit).")


def main():
    print(">> RRMTool: {}".format(config.RRM_CLI))
    if not config.RRM_CLI_FOUND:
        print(">> ERROR: RRMTool_CLI.exe is not installed (or not findable).")
        print(config.RRM_CLI_HELP)
        print(
            ">> Note: the rfIDEAS Configuration Utility GUI is NOT a substitute — "
            "ReaderConfig needs RRMTool_CLI.exe to load .hwg+ files."
        )
        sys.exit(2)

    ok, msg = check_reader()
    print(">> {}".format(msg))
    if not ok:
        print(">> Plug in the WAVE ID reader USB, then re-run ReaderConfig.")
        sys.exit(3)

    listener = BarcodeListener(on_barcode, block_barcode_prefix=False)
    listener.start()
    print(">> Ready — scan a card barcode (Ctrl+C to quit).")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\n>> Quitting.")
    finally:
        listener.stop()


if __name__ == "__main__":
    main()
