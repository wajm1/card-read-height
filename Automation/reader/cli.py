"""RRMTool CLI helpers for WAVE ID reader detection and HWG configuration.

Role
    Thin wrappers around ``RRMTool_CLI.exe`` used by the GUI, CLI runner, and
    ``ReaderConfig``. Does not move the robot.

Inputs
    ``config.RRM_CLI`` path; HWG+ files under ``files/hwg/``; card dicts from
    barcode lookup.

Outputs / side effects
    Subprocess calls to RRMTool (about / load config). Returns stdout text or
    (ok, message) tuples — never raises on missing CLI (returns error strings).
"""

from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

RRM_CLI = config.RRM_CLI


def run_cli(*args, timeout: int = 30) -> str:
    """Run RRMTool_CLI with ``args``; return combined stdout/stderr (or ERROR:…)."""
    if not os.path.isfile(RRM_CLI):
        return f"ERROR: RRMTool_CLI not found at {RRM_CLI}"
    cmd = [RRM_CLI, *[str(a) for a in args]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return f"ERROR: RRMTool_CLI timed out after {timeout}s"
    except OSError as e:
        return f"ERROR: could not launch RRMTool_CLI: {e}"


def check_reader() -> tuple[bool, str]:
    """Return (True, message) if RRMTool sees a reader; else (False, reason)."""
    if not os.path.isfile(RRM_CLI):
        return False, f"RRMTool_CLI not found — set RRM_CLI env var ({RRM_CLI})"
    out = run_cli("-about")
    if "Part-Number" in out:
        for line in out.splitlines():
            if line.strip().startswith("Part-Number"):
                model = line.split(":-")[-1].strip()
                return True, f"Reader detected: {model} (RRMTool: {RRM_CLI})"
        return True, f"Reader detected (RRMTool: {RRM_CLI})"
    return False, f"No reader response — check USB and RRMTool path ({RRM_CLI})"


def get_reader_info() -> dict:
    out = run_cli("-about")
    info = {"RRMTool": RRM_CLI}
    for line in out.splitlines():
        for key in ("Part-Number", "USB-Firmware", "Firmware Filename", "ESN", "LUID"):
            if line.strip().startswith(key):
                info[key] = line.split(":-")[-1].strip()
    return info


def _hwg_file_arg(hwg_path: str) -> str:
    return f"[{os.path.abspath(hwg_path)}]"


def parse_hwg_primary_card_type(hwg_path: str) -> int | None:
    try:
        with open(hwg_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("CardType:"):
                    continue
                val = line.split(":", 1)[1].split("/")[0].strip()
                if val.isdigit():
                    code = int(val)
                    if code != 0:
                        return code
    except OSError:
        pass
    return None


def get_reader_active_card_types(timeout: int = 5) -> list[int]:
    out = run_cli("-s", "-displayhwg", timeout=timeout)
    types: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("CardType:"):
            continue
        val = line.split(":", 1)[1].split("/")[0].strip()
        if val.isdigit():
            code = int(val)
            if code != 0:
                types.append(code)
    return types


def verify_reader_config_fast(hwg_path: str) -> tuple[bool, str]:
    expected = parse_hwg_primary_card_type(hwg_path)
    if expected is None:
        return True, "No CardType in HWG — skipped verify"

    active = get_reader_active_card_types(timeout=5)
    if not active:
        return False, "Reader did not report CardType after load"

    if expected in active:
        return True, f"CardType {expected} verified"
    return False, f"Expected CardType {expected}, reader has {active}"


def _resolve_hwg_path(hwg_file: str) -> str:
    if os.path.isabs(hwg_file):
        return hwg_file
    return os.path.join(config.PATHS["hwg"], os.path.basename(hwg_file))


def configure_reader_for_card(
    card_info: dict,
    log_fn=None,
    *,
    verify: bool = True,
) -> bool:
    def log(msg, tag="info"):
        print(msg)
        if log_fn:
            log_fn(msg, tag)

    hwg_file = card_info.get("hwg")
    if not hwg_file:
        log("No hwg file specified for this card type", "warn")
        return False

    hwg_file = _resolve_hwg_path(hwg_file)
    if not os.path.isfile(hwg_file):
        log(f"HWG file not found: {hwg_file}", "error")
        return False

    if not os.path.isfile(RRM_CLI):
        log(f"RRMTool_CLI not found: {RRM_CLI}", "error")
        return False

    log(f"Loading: {hwg_file}", "info")
    try:
        result = subprocess.run(
            [RRM_CLI, "-s", "-loadhwg", "-f", _hwg_file_arg(hwg_file)],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        log("RRMTool_CLI timed out while loading HWG", "error")
        return False
    except OSError as e:
        log(f"Could not run RRMTool_CLI: {e}", "error")
        return False

    output = result.stdout + result.stderr
    if "successfully" not in output.lower():
        log(f"OUTPUT: {output.strip()}", "error")
        return False

    if verify:
        ok, msg = verify_reader_config_fast(hwg_file)
        log(f"Verify: {msg}", "info" if ok else "error")
        if not ok:
            return False

    log("Reader configured successfully", "info")
    return True
