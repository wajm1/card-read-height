# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""CLI-tunable descent parameters for ``cardreadheight.py`` only.

Role
    ``TestSettings`` holds start height, step, min height, dwell/settle, and
    descent/approach speeds for the CLI runner. Initialized from ``config``
    defaults.

Note
    The Tk GUI does **not** import this module — GUI descent uses presets on
    ``GuiRobot`` / ``constants.DESCENT_PRESETS``. Docs that said "GUI sliders
    update these" were stale.
"""

from __future__ import annotations

import config


class TestSettings:
    """Thread-safe enough for GUI writes + robot thread reads (single writer)."""

    def __init__(self) -> None:
        self.start_height_mm = config.DEFAULT_START_HEIGHT_MM
        self.step_mm = config.DEFAULT_STEP_SIZE_MM
        self.min_height_mm = config.READ_HEIGHT_MIN_MM
        self.dwell_s = config.READ_HEIGHT_DWELL_S
        self.settle_s = config.READ_HEIGHT_SETTLE_S
        self.descent_speed = config.READ_HEIGHT_DESCENT_SPEED
        self.descent_acc = config.READ_HEIGHT_DESCENT_ACC
        self.approach_speed = config.READER_APPROACH_SPEED
        self.approach_acc = config.READER_APPROACH_ACC
