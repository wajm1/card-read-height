# barcode/scanner.py
# Barcode scanner input and card lookup from scanned codes

from __future__ import annotations

import os
import sys
import time

import keyboard

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCAN_MAX_KEY_GAP_S = 0.10

SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?", "`": "~",
}


class BarcodeListener:
    """Captures barcode scanner keystrokes via global keyboard hook."""

    def __init__(self, callback):
        self.callback = callback
        self.buf = ""
        self.active = False
        self._hook = None
        self._shift = False
        self._last_time = 0.0

    def start(self):
        if self.active:
            return
        self.buf = ""
        self._shift = False
        self._last_time = 0.0
        self.active = True
        self._hook = keyboard.hook(self._on_key)

    def stop(self):
        self.active = False
        if self._hook:
            keyboard.unhook(self._hook)
            self._hook = None

    def _on_key(self, event):
        if not self.active:
            return
        if event.name in ("shift", "left shift", "right shift"):
            self._shift = event.event_type == "down"
            return
        if event.event_type != "down":
            return

        now = time.monotonic()
        if self.buf and (now - self._last_time) > SCAN_MAX_KEY_GAP_S:
            self.buf = ""
        self._last_time = now

        if event.name == "enter":
            val = self.buf.strip()
            self.buf = ""
            if val:
                self.callback(val)
        elif event.name == "space":
            self.buf += " "
        elif len(event.name) == 1:
            ch = event.name
            if self._shift:
                ch = SHIFT_MAP.get(ch, ch.upper())
            self.buf += ch


def check_barcode_scanner() -> tuple[bool, str]:
    try:
        import keyboard as _kb  # noqa: F401
        return True, "Barcode scanner hook available"
    except ImportError:
        return False, "keyboard module not installed — pip install keyboard"


def _normalize_code(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def _resolve_cards_csv_path(csv_path: str | None = None) -> str | None:
    if csv_path and os.path.isfile(csv_path):
        return csv_path
    for candidate in (
        config.LOW_BAND_CARDS_CSV,
        os.path.join(config.WORKSPACE_ROOT, "files", "AllCards.csv"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def lookup_card_from_csv(barcode: str, csv_path: str | None = None) -> dict | None:
    """Look up a card by barcode in Files/AllCards.csv."""
    import csv as _csv

    path = _resolve_cards_csv_path(csv_path)
    if not path:
        return None

    target = _normalize_code(barcode)
    if not target:
        return None

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        if not reader.fieldnames:
            return None
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        barcode_key = next(
            (fields[k] for k in fields if k in (
                "barcode", "bar code", "card barcode", "id", "code", "card id",
            )),
            None,
        )
        name_key = next(
            (fields[k] for k in fields if k in (
                "name", "card name", "card", "title", "type", "card type",
            )),
            None,
        )
        side_key = next(
            (fields[k] for k in fields if k in ("side", "orientation")),
            None,
        )
        part_key = next(
            (fields[k] for k in fields if k in (
                "part number", "part", "hwg id", "id", "part-number",
            )),
            None,
        )

        for row in reader:
            if barcode_key:
                row_barcode = _normalize_code(row.get(barcode_key) or "")
                if row_barcode != target:
                    continue
            else:
                cells = {
                    key: (row.get(key) or "").strip()
                    for key in row
                    if row.get(key) and str(row.get(key)).strip()
                }
                if not any(_normalize_code(val) == target for val in cells.values()):
                    continue

            card_name = (row.get(name_key) or "").strip() if name_key else ""
            if not card_name:
                continue

            side = (row.get(side_key) or "").strip().upper() if side_key else ""
            if not side and target:
                side = target[0].upper() if target[0] in ("a", "b") else ""

            part_number = (row.get(part_key) or "").strip() if part_key else ""

            hwg_file = f"{card_name}.hwg+"
            return {
                "name": card_name,
                "title": card_name,
                "hwg": _resolve_hwg({"hwg": hwg_file}),
                "barcode": barcode.strip(),
                "side": side,
                "part_number": part_number,
            }
    return None


def lookup_card(barcode: str) -> dict | None:
    card = lookup_card_from_csv(barcode)
    if card:
        return card

    b = _normalize_code(barcode)
    for key, info in config.CARD_TYPE_MAP.items():
        if _normalize_code(key) == b:
            return {**info, "hwg": _resolve_hwg(info)}
    return None


def _resolve_hwg(info: dict) -> str:
    hwg = info.get("hwg", "")
    if hwg and not os.path.isabs(hwg):
        return os.path.join(config.PATHS["hwg"], hwg)
    return hwg
