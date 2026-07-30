"""Barcode scanner capture and AllCards.csv card lookup / baseline helpers.

Role
    Keyboard-wedge barcode listening (``BarcodeListener``), card lookup against
    workspace ``files/AllCards.csv``, and helpers to update / scrub saved
    average read-height baselines. Used by robot motion, CLI, GUI, and
    ``ReaderConfig``.

Inputs
    USB keyboard-wedge scans; ``files/AllCards.csv``; optional results CSVs
    when importing/scrubbing baselines.

Outputs / side effects
    May rewrite ``files/AllCards.csv`` when updating averages. Hooks global
    keyboard events (Windows may need admin). Resolves HWG names to
    ``files/hwg/*.hwg+`` via ``config.get_hwg_path``.
"""

from __future__ import annotations

import os
import sys
import time

import keyboard

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCAN_MAX_KEY_GAP_S = 0.10
# Scanner keys arrive faster than human typing; second key confirms a burst.
WEDGE_BURST_GAP_S = 0.05

SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?", "`": "~",
}

_ENTRY_CLASSES = frozenset({"Entry", "TEntry", "Spinbox", "TSpinbox"})


def _open_csv_text(path: str, mode: str = "r"):
    """Open a results/AllCards CSV with encoding fallback.

    Newer GUI exports are UTF-8. Some Keep/ legacy files were saved with a
    broken Windows dash (``\\x80\\x94`` instead of UTF-8 ``—``), which makes
    strict ``utf-8`` fail mid end-of-run scrub. Prefer utf-8-sig, then
    cp1252 / latin-1 so baseline sync never aborts a finished test.
    """
    last_err = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return open(path, mode, newline="", encoding=enc)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise last_err  # type: ignore[misc]


def register_tk_text_input(tk_root, widget) -> None:
    """Mark GUI text fields so global wedge hooks never swallow typed keys."""
    if tk_root is None:
        return
    if not hasattr(tk_root, "_pass_keys_to_gui"):
        tk_root._pass_keys_to_gui = False

    def on_focus_in(_event):
        tk_root._pass_keys_to_gui = True

    def on_focus_out(_event):
        tk_root._pass_keys_to_gui = False

    try:
        widget.bind("<FocusIn>", on_focus_in, add="+")
        widget.bind("<FocusOut>", on_focus_out, add="+")
    except Exception:
        pass


def _typing_in_tk_entry(tk_root) -> bool:
    """True when the user is typing in a GUI field — never swallow those keys."""
    if tk_root is None:
        return False
    if getattr(tk_root, "_pass_keys_to_gui", False):
        return True
    try:
        w = tk_root.focus_get()
        while w is not None:
            if w.winfo_class() in _ENTRY_CLASSES:
                return True
            w = w.master
    except Exception:
        pass
    return False


class BarcodeListener:
    """Captures barcode scanner keystrokes via global keyboard hook."""

    def __init__(
        self,
        callback,
        *,
        suppress_wedge=True,
        block_barcode_prefix=True,
        tk_root=None,
        force_capture=False,
    ):
        self.callback = callback
        self.suppress_wedge = suppress_wedge
        self.block_barcode_prefix = block_barcode_prefix
        self._tk_root = tk_root
        # When True, capture wedge keys even if a Tk Entry still has focus.
        # Required during pick/wave scans — always-on-top GUI often leaves
        # Comment/Cards focused, which otherwise silently drops every scan.
        self.force_capture = bool(force_capture)
        self.buf = ""
        self.active = False
        self._hook = None
        self._unhook = None
        self._shift = False
        self._last_time = 0.0
        self._block_burst = False
        self._warned_focus_block = False

    def start(self):
        if self.active:
            return
        self.buf = ""
        self._shift = False
        self._last_time = 0.0
        self._block_burst = False
        self._warned_focus_block = False
        self.active = True
        if self.suppress_wedge:
            self._unhook = keyboard.hook(self._on_key, suppress=True)
        else:
            self._hook = keyboard.hook(self._on_key)

    def stop(self):
        self.active = False
        try:
            if self._unhook is not None:
                self._unhook()
            elif self._hook is not None:
                keyboard.unhook(self._hook)
        finally:
            self._hook = None
            self._unhook = None
            self._block_burst = False

    def _allow_key(self) -> bool:
        """True = pass key to Windows, False = swallow (suppress hook only)."""
        if not self.suppress_wedge:
            return True
        return not self._block_burst

    def _reset_burst_if_idle(self, gap: float) -> None:
        if self.buf and gap > SCAN_MAX_KEY_GAP_S:
            self.buf = ""
            self._block_burst = False
            self._shift = False

    def _note_burst(self, *, starting: bool, gap: float, ch: str) -> None:
        if not starting and gap < WEDGE_BURST_GAP_S:
            self._block_burst = True
        elif starting and self.block_barcode_prefix and ch.upper() in "AB":
            self._block_burst = True

    def _on_key(self, event):
        if not self.active:
            return self._allow_key()

        if not self.force_capture and _typing_in_tk_entry(self._tk_root):
            if not self._warned_focus_block:
                self._warned_focus_block = True
                try:
                    print(">> Barcode ignored — a GUI text field has focus. "
                          "Click the window background (not Comment/Cards) or "
                          "restart the run.")
                except Exception:
                    pass
            return True

        if event.event_type != "down":
            return self._allow_key()

        now = time.monotonic()
        gap = now - self._last_time if self._last_time else float("inf")

        if event.name in ("shift", "left shift", "right shift"):
            self._shift = True
            return self._allow_key()

        self._reset_burst_if_idle(gap)
        self._last_time = now

        if event.name == "enter":
            val = self.buf.strip()
            allow = self._allow_key()
            self.buf = ""
            self._block_burst = False
            self._shift = False
            if val:
                self.callback(val)
            return allow

        if event.name == "space":
            ch = " "
        elif len(event.name) == 1:
            ch = event.name
            if self._shift:
                ch = SHIFT_MAP.get(ch, ch.upper())
            self._shift = False
        else:
            return self._allow_key()

        starting = not self.buf
        self._note_burst(starting=starting, gap=gap, ch=ch)
        self.buf += ch
        return self._allow_key()


def check_barcode_scanner() -> tuple[bool, str]:
    try:
        import keyboard as _kb  # noqa: F401
        return True, "Barcode scanner hook available"
    except ImportError:
        return False, "keyboard module not installed — pip install keyboard"


def _normalize_code(value: str) -> str:
    return value.strip().lower().replace(" ", "")


ALL_CARDS_INLINE_AVG_COL = "Inline Avg (mm above reader)"
ALL_CARDS_ORTH_AVG_COL = "Orthogonal Avg (mm above reader)"
ALL_CARDS_AVG_COLUMNS = (ALL_CARDS_INLINE_AVG_COL, ALL_CARDS_ORTH_AVG_COL)
# Legacy header from earlier builds
_ALL_CARDS_AVG_ALIASES = {
    "Inline Avg (mm)": ALL_CARDS_INLINE_AVG_COL,
    "Orthogonal Avg (mm)": ALL_CARDS_ORTH_AVG_COL,
}


def _parse_optional_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_avg(value) -> str:
    if value is None or value == "":
        return ""
    v = float(value)
    return "{:.2f}".format(v) if round(v, 2) != int(v) else str(int(v))


def is_bad_reference_height(value) -> bool:
    """True when a stored baseline is a bogus in-zone read (~70 mm above reader)."""
    v = _parse_optional_float(value)
    if v is None:
        return False
    return (
        config.READER_BAD_REFERENCE_BAND_LOW_MM
        <= v
        <= config.READER_BAD_REFERENCE_BAND_HIGH_MM
    )


def measurement_is_poisoned(
    raw_value,
    *,
    reader_height_mm: float | None,
    values_are_above_reader: bool,
) -> bool:
    """True when a results CSV measurement came from an in-zone stuck read."""
    v = _parse_optional_float(raw_value)
    if v is None:
        return False
    if values_are_above_reader:
        return is_bad_reference_height(v)
    if reader_height_mm is None:
        return False
    low = reader_height_mm + config.READER_INZONE_STUCK_LOW_ABOVE_READER_MM
    high = reader_height_mm + config.READER_INZONE_STUCK_HIGH_ABOVE_READER_MM
    return low <= v <= high


def collect_poisoned_part_numbers_from_results(
    results_dir: str | None = None,
) -> set[str]:
    """Part numbers with any poisoned measurement in saved results CSVs."""
    import csv as _csv
    import glob

    if results_dir is None:
        results_dir = config.PATHS["results"]
    if not os.path.isdir(results_dir):
        results_dir = os.path.join(os.path.dirname(config.ALL_CARDS_CSV), "..", "results")

    code_to_part: dict[str, str] = {}
    path, fieldnames, rows = _read_all_cards_table()
    if path:
        fields = {name.strip().lower(): name for name in fieldnames}
        barcode_key = _field_key(fields, "barcode", "bar code", "card barcode", "id", "code")
        part_key = _field_key(fields, "part number", "part", "part-number")
        if barcode_key and part_key:
            for row in rows:
                code = _normalize_code(row.get(barcode_key) or "")
                part = (row.get(part_key) or "").strip()
                if code and part:
                    code_to_part[code] = part

    poisoned: set[str] = set()
    pattern = os.path.join(results_dir, "**", "*_read_heights.csv")
    for results_path in glob.glob(pattern, recursive=True):
        try:
            reader_h = _reader_height_from_results_header(results_path)
            with _open_csv_text(results_path) as f:
                reader = _csv.reader(f)
                header_row = None
                for row in reader:
                    if not row:
                        continue
                    if row[0].strip().lower() == "run" and len(row) > 5:
                        header_row = [c.strip() for c in row]
                        break
                if not header_row:
                    continue
                fields = {name.lower(): idx for idx, name in enumerate(header_row)}
                code_idx = _results_column_index(fields, "card code")
                if code_idx is None:
                    continue
                inline_hdr = ""
                inline_idx = _results_column_index(
                    fields, "inline avg (mm above reader)", "inline avg (mm)",
                )
                if inline_idx is not None and inline_idx < len(header_row):
                    inline_hdr = header_row[inline_idx].lower()
                values_are_above_reader = "above reader" in inline_hdr
                measure_cols = []
                for key in (
                    "inline avg (mm above reader)", "inline avg (mm)",
                    "orthogonal avg (mm above reader)", "orthogonal avg (mm)",
                    "inline min", "inline max", "orthogonal min", "orthogonal max",
                    "card max (mm)", "card max",
                ):
                    idx = _results_column_index(fields, key)
                    if idx is not None:
                        measure_cols.append(idx)
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    code = row[code_idx].strip() if code_idx < len(row) else ""
                    part = code_to_part.get(_normalize_code(code), "")
                    if not part:
                        continue
                    for idx in measure_cols:
                        if idx >= len(row):
                            continue
                        if measurement_is_poisoned(
                            row[idx],
                            reader_height_mm=reader_h,
                            values_are_above_reader=values_are_above_reader,
                        ):
                            poisoned.add(part)
                            break
        except (OSError, UnicodeError, _csv.Error) as e:
            print(">> Skipping results file {} ({})".format(results_path, e))
            continue
    return poisoned


def scrub_poisoned_card_baselines(results_dir: str | None = None) -> int:
    """Blank baselines for parts with poisoned history; re-unify A/B rows."""
    path, fieldnames, rows = _read_all_cards_table()
    if not path:
        return 0

    fields = {name.strip().lower(): name for name in fieldnames}
    part_key = _field_key(fields, "part number", "part", "part-number")
    inline_key = _field_key(
        fields,
        "inline avg (mm above reader)", "inline avg (mm)", "inline_avg",
    )
    orth_key = _field_key(
        fields,
        "orthogonal avg (mm above reader)", "orthogonal avg (mm)", "orthogonal_avg",
    )
    if not part_key or not inline_key or not orth_key:
        return 0

    poisoned = collect_poisoned_part_numbers_from_results(results_dir)

    for row in rows:
        if is_bad_reference_height(row.get(inline_key)):
            row[inline_key] = ""
        if is_bad_reference_height(row.get(orth_key)):
            row[orth_key] = ""

    for row in rows:
        part = (row.get(part_key) or "").strip()
        if part in poisoned:
            row[inline_key] = ""
            row[orth_key] = ""

    merged = _part_baselines_from_rows(
        rows, inline_key=inline_key, orth_key=orth_key, part_key=part_key,
    )
    updated = 0
    for row in rows:
        part = (row.get(part_key) or "").strip()
        if not part or part not in merged:
            continue
        inline, orth = merged[part]
        row[inline_key] = _format_avg(inline) if inline is not None else ""
        row[orth_key] = _format_avg(orth) if orth is not None else ""
        updated += 1

    import csv as _csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return updated


def good_reference_height(value) -> float | None:
    """Return value only if it is a usable baseline (not blank, not bogus band)."""
    v = _parse_optional_float(value)
    if v is None or is_bad_reference_height(v):
        return None
    return v


def _part_baselines_from_rows(rows, *, inline_key, orth_key, part_key) -> dict[str, tuple[float | None, float | None]]:
    """Max inline/orthogonal baseline per part number across all matching rows."""
    by_part: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        part = (row.get(part_key) or "").strip()
        if not part:
            continue
        bucket = by_part.setdefault(part, {"inline": [], "orth": []})
        inline = good_reference_height(row.get(inline_key) if inline_key else None)
        orth = good_reference_height(row.get(orth_key) if orth_key else None)
        if inline is not None:
            bucket["inline"].append(inline)
        if orth is not None:
            bucket["orth"].append(orth)
    out: dict[str, tuple[float | None, float | None]] = {}
    for part, vals in by_part.items():
        out[part] = (
            max(vals["inline"]) if vals["inline"] else None,
            max(vals["orth"]) if vals["orth"] else None,
        )
    return out


def _ingest_results_baselines(results_path: str) -> dict[str, tuple[float | None, float | None]]:
    """Max inline/orthogonal per part number from a GUI results CSV."""
    import csv as _csv

    if not os.path.isfile(results_path):
        return {}

    code_to_part: dict[str, str] = {}
    path, fieldnames, rows = _read_all_cards_table()
    if path:
        fields = {name.strip().lower(): name for name in fieldnames}
        barcode_key = _field_key(fields, "barcode", "bar code", "card barcode", "id", "code")
        part_key = _field_key(fields, "part number", "part", "part-number")
        if barcode_key and part_key:
            for row in rows:
                code = _normalize_code(row.get(barcode_key) or "")
                part = (row.get(part_key) or "").strip()
                if code and part:
                    code_to_part[code] = part

    by_part: dict[str, dict[str, list[float]]] = {}
    with _open_csv_text(results_path) as f:
        reader = _csv.reader(f)
        header_row = None
        for row in reader:
            if not row:
                continue
            if row[0].strip().lower() == "run" and len(row) > 5:
                header_row = [c.strip() for c in row]
                break
        if not header_row:
            return {}
        fields = {name.lower(): idx for idx, name in enumerate(header_row)}
        code_idx = _results_column_index(fields, "card code")
        inline_avg_idx = _results_column_index(
            fields, "inline avg (mm above reader)", "inline avg (mm)",
        )
        orth_avg_idx = _results_column_index(
            fields, "orthogonal avg (mm above reader)", "orthogonal avg (mm)",
        )
        inline_max_idx = _results_column_index(fields, "inline max")
        orth_max_idx = _results_column_index(fields, "orthogonal max")
        if code_idx is None:
            return {}

        inline_hdr = (
            header_row[inline_avg_idx].lower()
            if inline_avg_idx is not None and inline_avg_idx < len(header_row)
            else ""
        )
        normalize = "above reader" not in inline_hdr
        reader_h = _reader_height_from_results_header(results_path) if normalize else None

        def add(part: str, kind: str, raw):
            v = _parse_optional_float(raw)
            if v is None:
                return
            if normalize and reader_h is not None:
                v = _normalize_avg_above_reader(v, reader_h)
            if v is None or is_bad_reference_height(v):
                return
            by_part.setdefault(part, {"inline": [], "orth": []})[kind].append(v)

        for row in reader:
            if not row or not row[0].strip():
                continue
            code = row[code_idx].strip() if code_idx < len(row) else ""
            part = code_to_part.get(_normalize_code(code), "")
            if not part:
                continue
            if inline_avg_idx is not None and inline_avg_idx < len(row):
                add(part, "inline", row[inline_avg_idx])
            if orth_avg_idx is not None and orth_avg_idx < len(row):
                add(part, "orth", row[orth_avg_idx])
            if inline_max_idx is not None and inline_max_idx < len(row):
                add(part, "inline", row[inline_max_idx])
            if orth_max_idx is not None and orth_max_idx < len(row):
                add(part, "orth", row[orth_max_idx])

    out: dict[str, tuple[float | None, float | None]] = {}
    for part, vals in by_part.items():
        out[part] = (
            max(vals["inline"]) if vals["inline"] else None,
            max(vals["orth"]) if vals["orth"] else None,
        )
    return out


def rebuild_all_cards_unified_baselines(
    results_path: str | None = None,
    *,
    merge_results: bool = False,
) -> int:
    """Clear bogus baselines (60–80 mm), optionally merge results CSV, unify A/B by part."""
    import csv as _csv

    path, fieldnames, rows = _read_all_cards_table()
    if not path:
        return 0

    fields = {name.strip().lower(): name for name in fieldnames}
    part_key = _field_key(fields, "part number", "part", "part-number")
    inline_key = _field_key(
        fields,
        "inline avg (mm above reader)", "inline avg (mm)", "inline_avg",
    )
    orth_key = _field_key(
        fields,
        "orthogonal avg (mm above reader)", "orthogonal avg (mm)", "orthogonal_avg",
    )
    if not part_key or not inline_key or not orth_key:
        return 0

    for row in rows:
        if is_bad_reference_height(row.get(inline_key)):
            row[inline_key] = ""
        if is_bad_reference_height(row.get(orth_key)):
            row[orth_key] = ""

    results_by_part = (
        _ingest_results_baselines(results_path)
        if merge_results and results_path
        else {}
    )
    table_by_part = _part_baselines_from_rows(
        rows, inline_key=inline_key, orth_key=orth_key, part_key=part_key,
    )

    merged: dict[str, tuple[float | None, float | None]] = {}
    all_parts = set(table_by_part) | set(results_by_part)
    for part in all_parts:
        ti, to = table_by_part.get(part, (None, None))
        ri, ro = results_by_part.get(part, (None, None))
        inline_vals = [v for v in (ti, ri) if v is not None]
        orth_vals = [v for v in (to, ro) if v is not None]
        merged[part] = (
            max(inline_vals) if inline_vals else None,
            max(orth_vals) if orth_vals else None,
        )

    updated = 0
    for row in rows:
        part = (row.get(part_key) or "").strip()
        if not part or part not in merged:
            continue
        inline, orth = merged[part]
        if inline is not None:
            row[inline_key] = _format_avg(inline)
        else:
            row[inline_key] = ""
        if orth is not None:
            row[orth_key] = _format_avg(orth)
        else:
            row[orth_key] = ""
        updated += 1

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return updated


def _read_all_cards_table():
    import csv as _csv

    path = _resolve_cards_csv_path()
    if not path:
        return None, [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    for col in ALL_CARDS_AVG_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)
    # Migrate legacy column names in-place
    for row in rows:
        for old, new in _ALL_CARDS_AVG_ALIASES.items():
            if old in row and row.get(old) and not row.get(new):
                row[new] = row[old]
            if old in row and old != new:
                row.pop(old, None)
        for old in _ALL_CARDS_AVG_ALIASES:
            if old in fieldnames and old not in ALL_CARDS_AVG_COLUMNS:
                fieldnames = [new if c == old else c for c in fieldnames]
                fieldnames = [c for c in fieldnames if c not in _ALL_CARDS_AVG_ALIASES or c in ALL_CARDS_AVG_COLUMNS]
    return path, fieldnames, rows


def _field_key(fields: dict, *candidates: str):
    return next((fields[k] for k in fields if k in candidates), None)


def migrate_all_cards_avg_columns() -> bool:
    """Rename legacy average columns; returns True if file was rewritten."""
    path, fieldnames, rows = _read_all_cards_table()
    if not path:
        return False
    import csv as _csv

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return True


def update_all_cards_averages(updates: list[dict]) -> int:
    """Legacy: write inline/orthogonal averages into AllCards.csv by barcode.

    Current AllCards.csv has no height columns (barcode → name/HWG only).
    Returns 0 without modifying the file when those columns are absent.
    """
    import csv as _csv

    if not updates:
        return 0
    path = _resolve_cards_csv_path()
    if not path or not os.path.isfile(path):
        return 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []
        if not fieldnames:
            with open(path, newline="", encoding="utf-8-sig") as f2:
                fieldnames = list(_csv.DictReader(f2).fieldnames or [])

    # Do not re-introduce baseline columns into a slim AllCards.csv.
    has_inline = any(
        (c or "").strip().lower() in (
            "inline avg (mm above reader)", "inline avg (mm)", "inline_avg",
        )
        for c in fieldnames
    )
    has_orth = any(
        (c or "").strip().lower() in (
            "orthogonal avg (mm above reader)", "orthogonal avg (mm)", "orthogonal_avg",
        )
        for c in fieldnames
    )
    if not (has_inline and has_orth):
        return 0

    # ... legacy path kept below for older CSVs that still have avg columns
    fieldnames, _ = _ensure_avg_columns(fieldnames)
    by_code = {}
    for item in updates:
        code = _normalize_code(item.get("card_code") or item.get("barcode") or "")
        if code:
            by_code[code] = item

    changed = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = _csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or fieldnames)

    fieldnames, _ = _ensure_avg_columns(fieldnames)
    for row in rows:
        code = _normalize_code(row.get("Barcode") or row.get("barcode") or "")
        item = by_code.get(code)
        if not item:
            continue
        before = (row.get(ALL_CARDS_INLINE_AVG_COL), row.get(ALL_CARDS_ORTH_AVG_COL))
        if item.get("inline_avg") not in ("", None) and not is_bad_reference_height(item["inline_avg"]):
            row[ALL_CARDS_INLINE_AVG_COL] = _format_avg(item["inline_avg"])
        if item.get("orthogonal_avg") not in ("", None) and not is_bad_reference_height(item["orthogonal_avg"]):
            row[ALL_CARDS_ORTH_AVG_COL] = _format_avg(item["orthogonal_avg"])
        after = (row.get(ALL_CARDS_INLINE_AVG_COL), row.get(ALL_CARDS_ORTH_AVG_COL))
        if after != before:
            changed += 1

    if changed:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return changed


def _normalize_avg_above_reader(value: float | None, reader_height_mm: float | None) -> float | None:
    """Convert a results CSV average to mm above reader top.

    GUI exports should already be above-reader, but some rows may still be
    above-table (value > reader height). Values already below reader height
    are left unchanged.
    """
    if value is None or reader_height_mm is None:
        return value
    if value > reader_height_mm:
        return max(0.0, value - reader_height_mm)
    return value


def _results_column_index(fields: dict, *candidates: str):
    for name in candidates:
        idx = fields.get(name.lower())
        if idx is not None:
            return idx
    return None


def _reader_height_from_results_header(results_path: str) -> float | None:
    """Read Reader Type from results header; look up height if card_readers.json exists."""
    import csv as _csv
    import json

    try:
        with _open_csv_text(results_path) as f:
            for row in _csv.reader(f):
                if len(row) >= 2 and row[0].strip().lower() == "reader type":
                    reader_id = row[1].strip()
                    break
            else:
                return None
        lib_path = os.path.join(config.PATHS["files"], "card_readers.json")
        if not os.path.isfile(lib_path):
            return None
        with open(lib_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("card_readers", []):
            eid = (entry.get("id") or entry.get("model") or "").strip()
            if eid.lower() == reader_id.lower():
                h = entry.get("height_mm")
                return float(h) if isinstance(h, (int, float)) else None
    except Exception:
        return None
    return None


def import_results_csv_to_all_cards(
    results_path: str,
    *,
    reader_height_mm: float | None = None,
    values_are_above_table: bool = False,
    auto_normalize: bool = True,
) -> int:
    """Import inline/orthogonal averages from a GUI results CSV into AllCards.csv."""
    import csv as _csv

    if not os.path.isfile(results_path):
        return 0

    if reader_height_mm is None:
        reader_height_mm = _reader_height_from_results_header(results_path)

    updates = []
    with _open_csv_text(results_path) as f:
        reader = _csv.reader(f)
        header_row = None
        for row in reader:
            if not row:
                continue
            if row[0].strip().lower() == "run" and len(row) > 5:
                header_row = [c.strip() for c in row]
                break
        if not header_row:
            return 0
        fields = {name.lower(): idx for idx, name in enumerate(header_row)}
        code_idx = _results_column_index(fields, "card code")
        inline_idx = _results_column_index(
            fields,
            "inline avg (mm above reader)",
            "inline avg (mm)",
        )
        orth_idx = _results_column_index(
            fields,
            "orthogonal avg (mm above reader)",
            "orthogonal avg (mm)",
        )
        if code_idx is None:
            return 0

        inline_hdr = (
            header_row[inline_idx].lower()
            if inline_idx is not None and inline_idx < len(header_row)
            else ""
        )
        values_already_above_reader = "above reader" in inline_hdr
        if values_already_above_reader:
            auto_normalize = False
        elif not values_are_above_table and auto_normalize and reader_height_mm is None:
            auto_normalize = False

        for row in reader:
            if not row or not row[0].strip():
                continue
            code = row[code_idx].strip() if code_idx < len(row) else ""
            if not code:
                continue
            inline = _parse_optional_float(row[inline_idx] if inline_idx is not None and inline_idx < len(row) else None)
            orth = _parse_optional_float(row[orth_idx] if orth_idx is not None and orth_idx < len(row) else None)
            if values_are_above_table and reader_height_mm is not None:
                if inline is not None:
                    inline = max(0.0, inline - reader_height_mm)
                if orth is not None:
                    orth = max(0.0, orth - reader_height_mm)
            elif auto_normalize and reader_height_mm is not None:
                inline = _normalize_avg_above_reader(inline, reader_height_mm)
                orth = _normalize_avg_above_reader(orth, reader_height_mm)
            if inline is not None and is_bad_reference_height(inline):
                inline = None
            if orth is not None and is_bad_reference_height(orth):
                orth = None
            if inline is None and orth is None:
                continue
            updates.append({
                "card_code": code,
                "inline_avg": inline,
                "orthogonal_avg": orth,
            })
    return update_all_cards_averages(updates)


def _resolve_cards_csv_path(csv_path: str | None = None) -> str | None:
    if csv_path and os.path.isfile(csv_path):
        return csv_path
    if os.path.isfile(config.ALL_CARDS_CSV):
        return config.ALL_CARDS_CSV
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
        inline_key = _field_key(
            fields,
            "inline avg (mm above reader)",
            "inline avg (mm)", "inline_avg (mm)", "inline avg", "inline_avg",
        )
        orth_key = _field_key(
            fields,
            "orthogonal avg (mm above reader)",
            "orthogonal avg (mm)", "orthogonal_avg (mm)", "orthogonal avg", "orthogonal_avg",
        )

        rows = list(reader)
        part_baselines = _part_baselines_from_rows(
            rows, inline_key=inline_key, orth_key=orth_key, part_key=part_key,
        ) if part_key and inline_key and orth_key else {}

        for row in rows:
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
            # Height baselines are optional (removed from current AllCards.csv).
            inline_avg = orth_avg = None
            if inline_key or orth_key:
                if part_number and part_number in part_baselines:
                    inline_avg, orth_avg = part_baselines[part_number]
                else:
                    inline_avg = good_reference_height(row.get(inline_key) if inline_key else None)
                    orth_avg = good_reference_height(row.get(orth_key) if orth_key else None)

            hwg_file = f"{card_name}.hwg+"
            return {
                "name": card_name,
                "title": card_name,
                "hwg": _resolve_hwg({"hwg": hwg_file}),
                "barcode": barcode.strip(),
                "side": side,
                "part_number": part_number,
                "inline_avg": inline_avg,
                "orthogonal_avg": orth_avg,
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
