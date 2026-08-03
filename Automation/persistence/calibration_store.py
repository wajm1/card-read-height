"""Persistent reader-calibration store for the Credential Read Height rig.

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Save and reload the reader calibration captured by CALIBRATE READER ->
    MARK READER TOP so the card tap location survives closing and reopening the
    GUI. Before this module the calibration lived only in memory and was lost on
    exit, forcing a re-calibration every session.

    One calibration is stored per reader model (the GUI dropdown value, e.g.
    "HIP2_SP"), because a calibration only makes sense for the reader it was
    marked on. Re-marking the same reader overwrites its saved entry; that is the
    intended way to change a remembered tap location.

Stored fields (all relative to the table surface, mm / degrees):
    reader_height_mm             card-face height at the reader top (table -> top)
    reader_floor_above_table_mm  descent floor the arm must not go below
    staging_pose_deg             6 joint angles of the approach/staging pose
    table_z_mm                   TABLE_Z at capture time (used to warn on drift)
    marked_at                    ISO timestamp of the capture

Role in the system:
    Pure I/O helper. No robot, GUI, or reader hardware calls. Imported by
    gui/app.py (calibration save on MARK, load on startup / reader change).
    Reads/writes a single JSON file under the workspace ``files/`` directory.

Storage file:
    ``files/calibration.json`` (resolved via ``config.PATHS['files']``).
"""

from __future__ import annotations

import os
import json
from datetime import datetime

import config

# Bump if the on-disk schema ever changes in an incompatible way.
CALIB_VERSION = 1


def calibration_path() -> str:
    """Absolute path to the calibration JSON under the workspace ``files/`` dir."""
    return os.path.join(config.PATHS["files"], "calibration.json")


def _reader_key(reader_model) -> str:
    """Normalize a reader-model label to a stable dict key (upper, trimmed)."""
    return (reader_model or "").strip().upper()


def _empty_store() -> dict:
    return {"version": CALIB_VERSION, "readers": {}}


def _load_all() -> dict:
    """Read the whole calibration file, tolerating absent/corrupt files.

    A missing file or unreadable/legacy content yields an empty store rather
    than raising, so the GUI never fails to launch because of this file.
    """
    path = calibration_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("readers"), dict):
            data.setdefault("version", CALIB_VERSION)
            return data
    except (FileNotFoundError, ValueError, OSError):
        pass
    return _empty_store()


def _coerce_pose(pose):
    """Return a clean 6-float joint pose, or None if the value is unusable."""
    if pose is None:
        return None
    try:
        clean = [float(a) for a in pose][:6]
    except (TypeError, ValueError):
        return None
    return clean if len(clean) == 6 else None


def load_calibration(reader_model) -> dict | None:
    """Return the saved calibration for ``reader_model``, or None if none/invalid.

    Returned dict keys: reader_height_mm, reader_floor_above_table_mm,
    staging_pose_deg (list[6] or None), table_z_mm, marked_at. Height and floor
    are required; a record missing either is treated as absent.
    """
    key = _reader_key(reader_model)
    if not key:
        return None
    entry = _load_all().get("readers", {}).get(key)
    if not isinstance(entry, dict):
        return None
    try:
        height = entry.get("reader_height_mm")
        floor = entry.get("reader_floor_above_table_mm")
        if height is None or floor is None:
            return None
        return {
            "reader_height_mm": float(height),
            "reader_floor_above_table_mm": float(floor),
            "staging_pose_deg": _coerce_pose(entry.get("staging_pose_deg")),
            "table_z_mm": entry.get("table_z_mm"),
            "marked_at": entry.get("marked_at"),
        }
    except (TypeError, ValueError):
        return None


def table_z_drifted(saved: dict, tolerance_mm: float = 0.5) -> bool:
    """True when a saved record's TABLE_Z differs from the current config value.

    Heights are stored relative to the table, so a changed TABLE_Z means the
    remembered floor/height no longer point at the same physical spot. The GUI
    can warn the operator to re-calibrate.
    """
    if not saved:
        return False
    saved_z = saved.get("table_z_mm")
    if saved_z is None:
        return False
    try:
        return abs(float(saved_z) - float(config.TABLE_Z_MM)) > float(tolerance_mm)
    except (TypeError, ValueError):
        return False


def save_calibration(
    reader_model,
    *,
    reader_height_mm,
    reader_floor_above_table_mm,
    staging_pose_deg,
    table_z_mm=None,
) -> bool:
    """Persist one reader's calibration, overwriting any previous entry.

    Returns True on success. Writes atomically (temp file + ``os.replace``) so a
    crash mid-write can never corrupt an existing good calibration.
    """
    key = _reader_key(reader_model)
    if not key:
        return False
    try:
        record = {
            "reader_height_mm": round(float(reader_height_mm), 3),
            "reader_floor_above_table_mm": round(float(reader_floor_above_table_mm), 3),
            "staging_pose_deg": (
                [round(float(a), 3) for a in staging_pose_deg]
                if staging_pose_deg else None
            ),
            "table_z_mm": round(
                float(table_z_mm if table_z_mm is not None else config.TABLE_Z_MM), 3
            ),
            "marked_at": datetime.now().isoformat(timespec="seconds"),
        }
    except (TypeError, ValueError):
        return False
    data = _load_all()
    data.setdefault("readers", {})[key] = record
    return _atomic_write(data)


def clear_calibration(reader_model) -> bool:
    """Forget the saved calibration for one reader model. True if one was removed."""
    key = _reader_key(reader_model)
    data = _load_all()
    if key in data.get("readers", {}):
        del data["readers"][key]
        return _atomic_write(data)
    return False


def _atomic_write(data: dict) -> bool:
    """Write the store atomically; never leave a half-written file on disk."""
    path = calibration_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as e:
        print(">> Calibration save failed ({}): {}".format(path, e))
        return False
