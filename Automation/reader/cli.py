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
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

RRM_CLI = config.RRM_CLI

# Continuous keyboard-wedge output while a credential stays in the field.
# bSndOnRx MUST remain 0: the HWG documentation says setting it to 1 bypasses
# iIDLockOutTm, which produces only an immediate send instead of periodic sends.
# A 100 ms lockout gives several wedge reports inside each 400 ms listen window.
CONTINUOUS_LOCKOUT_MS = 100
CONTINUOUS_HOLD_MS = 1000


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


def _rewrite_hwg_int(text: str, key: str, value: int) -> str:
    """Replace ``key = N`` assignments (keeps trailing comments)."""
    pat = re.compile(
        rf"^(\s*{re.escape(key)}\s*=\s*)\d+(\s*.*)$",
        re.MULTILINE,
    )
    return pat.sub(rf"\g<1>{int(value)}\2", text)


def make_continuous_hwg(
    src_path: str,
    dest_path: str | None = None,
    *,
    lockout_ms: int = CONTINUOUS_LOCKOUT_MS,
    hold_ms: int = CONTINUOUS_HOLD_MS,
) -> str:
    """Write a temp HWG+ with periodic keyboard-wedge output.

    Returns the path written. Does not load the reader — caller loads via
    ``configure_reader_for_card(..., continuous=True)`` or ``-loadhwg``.
    """
    with open(src_path, encoding="utf-8", errors="ignore") as f:
        text = f.read()
    text = _rewrite_hwg_int(text, "iIDLockOutTm", lockout_ms)
    text = _rewrite_hwg_int(text, "iIDHoldTO", hold_ms)
    # Keep repetitive reports governed by iIDLockOutTm. bSndOnRx=1 explicitly
    # disables that timer in the HWG format and is not continuous output.
    text = _rewrite_hwg_int(text, "bSndOnRx", 0)
    if dest_path is None:
        base = os.path.splitext(os.path.basename(src_path))[0]
        fd, dest_path = tempfile.mkstemp(
            prefix=f"{base}_cont_", suffix=".hwg+", text=True,
        )
        os.close(fd)
    with open(dest_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return dest_path


def configure_reader_for_card(
    card_info: dict,
    log_fn=None,
    *,
    verify: bool = True,
    continuous: bool = False,
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

    load_path = hwg_file
    temp_cont = None
    if continuous:
        try:
            temp_cont = make_continuous_hwg(hwg_file)
            load_path = temp_cont
            log(
                f"Continuous mode: lockout={CONTINUOUS_LOCKOUT_MS}ms, "
                f"hold={CONTINUOUS_HOLD_MS}ms (temp HWG)",
                "info",
            )
        except OSError as e:
            log(f"Could not build continuous HWG: {e}", "error")
            return False

    log(f"Loading: {load_path}", "info")
    try:
        try:
            result = subprocess.run(
                [RRM_CLI, "-s", "-loadhwg", "-f", _hwg_file_arg(load_path)],
                capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            log("RRMTool_CLI timed out while loading HWG", "error")
            return False
        except OSError as e:
            log(f"Could not run RRMTool_CLI: {e}", "error")
            return False
    finally:
        if temp_cont:
            try:
                os.remove(temp_cont)
            except OSError:
                pass

    output = result.stdout + result.stderr
    if "successfully" not in output.lower():
        log(f"OUTPUT: {output.strip()}", "error")
        return False

    if verify:
        # Verify against the original HWG CardType (continuous patch keeps it).
        ok, msg = verify_reader_config_fast(hwg_file)
        log(f"Verify: {msg}", "info" if ok else "error")
        if not ok:
            return False

    log(
        "Reader configured successfully"
        + (" (continuous read)" if continuous else ""),
        "info",
    )
    return True
