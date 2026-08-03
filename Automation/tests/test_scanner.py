"""Characterization + regression tests for barcode capture and card lookup.

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Lock the barcode-wedge state machine (burst detection, A/B prefix blocking,
    and — critically — passing keys THROUGH when the operator is typing in a GUI
    field) and the AllCards.csv lookup (name -> HWG filename rule, trailing-space
    trimming). Includes the regression test for the Comment-field "can't type"
    fix: a focus swap must never strand the allow-flag False.
"""

import types

from barcode import scanner
from barcode.scanner import (
    BarcodeListener, lookup_card, _normalize_code, _format_avg,
    is_bad_reference_height, register_tk_text_input, _typing_in_tk_entry,
)


def ev(name, event_type="down"):
    return types.SimpleNamespace(name=name, event_type=event_type)


# ---- small helpers ----
def _feed(monkeypatch, listener, chars, gap=0.01, enter=True):
    clock = [0.0]
    monkeypatch.setattr(scanner.time, "monotonic", lambda: clock[0])
    allow = []
    for ch in chars:
        clock[0] += gap
        allow.append(listener._on_key(ev(ch)))
    if enter:
        clock[0] += gap
        allow.append(listener._on_key(ev("enter")))
    return allow


# ---- pure helpers ----
def test_normalize_code_strips_spaces_and_lowercases():
    assert _normalize_code("  A 005 ") == "a005"
    assert _normalize_code("A005") == "a005"


def test_is_bad_reference_height_band_60_to_80():
    assert is_bad_reference_height(70) is True
    assert is_bad_reference_height(59) is False
    assert is_bad_reference_height(81) is False
    assert is_bad_reference_height("") is False


def test_format_avg_two_decimals_or_int():
    assert _format_avg("") == ""
    assert _format_avg(25) == "25"
    assert _format_avg(25.4) == "25.40"


# ---- AllCards.csv lookup (real file) ----
def test_lookup_card_from_real_allcards():
    card = lookup_card("a005")
    assert card is not None
    assert card["name"] == "Keri UID"
    assert card["side"] == "A"
    assert card["hwg"].replace("\\", "/").endswith("files/hwg/Keri UID.hwg+")


def test_lookup_trims_trailing_space_in_name_for_hwg():
    # Row A017 is "CEPAS " (trailing space) — the HWG file is "CEPAS.hwg+".
    card = lookup_card("a017")
    assert card is not None
    assert card["name"] == "CEPAS"
    assert card["hwg"].replace("\\", "/").endswith("files/hwg/CEPAS.hwg+")


def test_lookup_unknown_barcode_returns_none():
    assert lookup_card("zzz999") is None


# ---- BarcodeListener state machine ----
def test_wedge_burst_is_captured_and_suppressed(monkeypatch):
    got = []
    bl = BarcodeListener(got.append)          # tk_root None -> not "typing"
    bl.active = True
    allow = _feed(monkeypatch, bl, "a005")
    assert got == ["a005"]
    assert all(a is False for a in allow)      # never leaks to the OS/focused app


def test_typing_passes_through_when_field_focused(monkeypatch):
    class Root:
        _pass_keys_to_gui = True
    got = []
    bl = BarcodeListener(got.append, tk_root=Root())
    bl.active = True
    allow = _feed(monkeypatch, bl, "hello", gap=0.2, enter=False)
    assert all(a is True for a in allow)       # every key reaches the field
    assert got == []                           # nothing mistaken for a barcode


def test_force_capture_grabs_scan_even_with_field_focused(monkeypatch):
    # During a run the listener uses force_capture=True so a focused Comment/Cards
    # field cannot silently swallow a real card scan.
    class Root:
        _pass_keys_to_gui = True
    got = []
    bl = BarcodeListener(got.append, tk_root=Root(), force_capture=True)
    bl.active = True
    _feed(monkeypatch, bl, "b012")
    assert got == ["b012"]


# ---- Comment-field "can't type" regression (focus-swap race) ----
class _FakeRoot:
    def focus_get(self):
        raise RuntimeError("cross-thread: not in main loop")


class _FakeWidget:
    def __init__(self):
        self.master = None
        self._b = {}

    def winfo_class(self):
        return "Entry"

    def bind(self, seq, fn, add=None):
        self._b[seq] = fn

    def fire(self, seq):
        if seq in self._b:
            self._b[seq](None)


def test_focus_swap_race_keeps_allow_flag_true():
    root = _FakeRoot()
    ip, comment = _FakeWidget(), _FakeWidget()
    register_tk_text_input(root, ip)
    register_tk_text_input(root, comment)
    # Comment gains focus, THEN a stale FocusOut from the previous field fires.
    comment.fire("<FocusIn>")
    ip.fire("<FocusOut>")
    assert root._pass_keys_to_gui is True
    assert _typing_in_tk_entry(root) is True     # even though focus_get() raises


def test_click_sets_allow_flag_and_blur_clears_it():
    root = _FakeRoot()
    comment = _FakeWidget()
    register_tk_text_input(root, comment)
    comment.fire("<Button-1>")
    assert _typing_in_tk_entry(root) is True
    comment.fire("<FocusOut>")
    assert _typing_in_tk_entry(root) is False
