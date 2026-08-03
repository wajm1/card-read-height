"""Characterization tests for the CSV result-row math (all three test modes).

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    The exported CSV is the product of this rig. These tests pin the per-card
    statistics (averages, min/max, scan counts, read-time ms, deadzone height
    lists) and the error/partial annotations so a refactor can never silently
    change what lands in a results file. Uses the FakeArm-backed GuiRobot.
"""

from constants import _csv_row, _parse_saved_avg, CSV_WIDTH


def _capture(gui_robot):
    rows = []
    gui_robot._on_result = rows.append
    return rows


# ---- Read Height ----------------------------------------------------------
def test_read_height_row_statistics(gui_robot):
    rows = _capture(gui_robot)
    gui_robot.cfg_angles = [0, 90, 180, 270]
    heights = {0: [10.0, 12.0], 90: [20.0], 180: [], 270: []}
    gui_robot._emit_result(1, ("Keri UID", "a005"), heights, "")
    r = rows[-1]
    assert r["kind"] == "read_height"
    assert r["card_code"] == "A005"                 # barcode upper-cased
    assert (r["a0_avg"], r["a0_min"], r["a0_max"], r["a0_scans"]) == (11.0, 10.0, 12.0, 2)
    assert (r["a90_avg"], r["a90_scans"]) == (20.0, 1)
    assert (r["a180_avg"], r["a180_scans"]) == ("", "")   # empty angle -> blanks
    assert r["card_max"] == 20.0
    assert "NO READ" in r["error_skip"] and "180" in r["error_skip"] and "270" in r["error_skip"]


def test_read_height_hard_error_row(gui_robot):
    rows = _capture(gui_robot)
    gui_robot._emit_result(2, None, {}, "PICK FAIL")
    r = rows[-1]
    assert r["error_skip"] == "PICK FAIL"
    assert r["card_title"] == "" and r["card_code"] == "" and r["card_max"] == ""


# ---- Tap and Go -----------------------------------------------------------
def test_tapgo_row_statistics(gui_robot):
    rows = _capture(gui_robot)
    gui_robot._emit_tapgo_result(1, ("Keri UID", "a005"), [100.0, 200.0, None], "A", 90, "")
    r = rows[-1]
    assert r["kind"] == "tap_and_go" and r["angle"] == "90°"
    assert (r["taps"], r["reads"], r["misses"]) == (3, 2, 1)
    assert (r["avg_ms"], r["min_ms"], r["max_ms"]) == (150.0, 100.0, 200.0)
    assert r["times_ms"] == "100.0, 200.0, miss"


def test_tapgo_all_misses_flagged(gui_robot):
    rows = _capture(gui_robot)
    gui_robot._emit_tapgo_result(1, ("Keri UID", "a005"), [None, None], "", 0, "")
    r = rows[-1]
    assert r["reads"] == 0 and r["avg_ms"] == ""
    assert r["error_skip"] == "NO READ (all taps)"


# ---- Deadzone -------------------------------------------------------------
def test_deadzone_found_row(gui_robot):
    rows = _capture(gui_robot)
    res = {"deadzones": [12.5, 30.0], "exit_height_mm": 45.0}
    gui_robot._emit_deadzone_result(1, ("Keri UID", "a005"), 0, res, "")
    r = rows[-1]
    assert r["kind"] == "deadzone" and r["deadzone_found"] == "Y"
    assert r["deadzone_heights_mm"] == "12.50, 30.00"
    assert r["exit_height_mm"] == 45.0


def test_deadzone_none_found_row(gui_robot):
    rows = _capture(gui_robot)
    gui_robot._emit_deadzone_result(1, ("Keri UID", "a005"), 90,
                                    {"deadzones": [], "exit_height_mm": 50.0}, "")
    r = rows[-1]
    assert r["deadzone_found"] == "N" and r["deadzone_heights_mm"] == ""


# ---- CSV helpers ----------------------------------------------------------
def test_csv_row_pads_and_truncates_to_fixed_width():
    assert len(_csv_row([1, 2, 3])) == CSV_WIDTH
    assert len(_csv_row(list(range(CSV_WIDTH + 5)))) == CSV_WIDTH


def test_parse_saved_avg_rejects_blank_negative_and_bad_band():
    assert _parse_saved_avg("") is None
    assert _parse_saved_avg(None) is None
    assert _parse_saved_avg("-3") is None
    assert _parse_saved_avg("70") is None      # 60-80 "bogus in-zone" band
    assert _parse_saved_avg("25.4") == 25.4
