"""Tests for the persistent reader-calibration store (feature + safety net).

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Verify the calibration that MARK READER TOP captures is saved and reloaded
    correctly so the card tap location survives a GUI restart, that re-marking
    overwrites it, that reader models are isolated, and that a missing/corrupt
    file can never crash the GUI. Storage is redirected to a temp file so the
    real files/calibration.json is untouched.
"""

import config
from persistence import calibration_store as cs


def test_round_trip_and_key_normalization(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "calibration_path", lambda: str(tmp_path / "calibration.json"))
    assert cs.load_calibration("HIP2_SP") is None
    cs.save_calibration(
        "HIP2_SP", reader_height_mm=44.0, reader_floor_above_table_mm=40.0,
        staging_pose_deg=[0.5, 13.6, 36.9, 0.1, 20.0, -270.8], table_z_mm=59.81)
    c = cs.load_calibration("  hip2_sp ")          # case / space insensitive
    assert c["reader_height_mm"] == 44.0
    assert c["reader_floor_above_table_mm"] == 40.0
    assert c["staging_pose_deg"][5] == -270.8


def test_overwrite_then_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "calibration_path", lambda: str(tmp_path / "c.json"))
    cs.save_calibration("PICO", reader_height_mm=25.0,
                        reader_floor_above_table_mm=23.0, staging_pose_deg=None)
    cs.save_calibration("PICO", reader_height_mm=26.0,
                        reader_floor_above_table_mm=24.0, staging_pose_deg=None)
    assert cs.load_calibration("PICO")["reader_height_mm"] == 26.0   # re-mark wins
    assert cs.clear_calibration("PICO") is True
    assert cs.load_calibration("PICO") is None


def test_reader_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "calibration_path", lambda: str(tmp_path / "c.json"))
    cs.save_calibration("HIP2_SP", reader_height_mm=44.0,
                        reader_floor_above_table_mm=40.0, staging_pose_deg=None)
    assert cs.load_calibration("PICO") is None       # different reader unaffected


def test_corrupt_file_is_tolerated(tmp_path, monkeypatch):
    p = tmp_path / "c.json"
    p.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(cs, "calibration_path", lambda: str(p))
    assert cs.load_calibration("HIP2_SP") is None    # no exception


def test_table_z_drift_detection(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "calibration_path", lambda: str(tmp_path / "c.json"))
    cs.save_calibration("MICRO", reader_height_mm=18.0,
                        reader_floor_above_table_mm=16.0, staging_pose_deg=None,
                        table_z_mm=config.TABLE_Z_MM)
    saved = cs.load_calibration("MICRO")
    assert cs.table_z_drifted(saved) is False
    assert cs.table_z_drifted({**saved, "table_z_mm": config.TABLE_Z_MM + 5}) is True
