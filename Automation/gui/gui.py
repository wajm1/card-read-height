# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""Primary Tk GUI entry point for credential read-height / tap-and-go testing.

Role
    Thin launcher that builds the Tk root and hands control to ``app.App``.
    All UI, orchestration, and motion live in sibling modules
    (``app``, ``gui_robot``, ``constants``, ``widgets``, ``arm_gl``, ``robot_viewer``).

Inputs / side effects
    - Requires cwd / ``sys.path`` rooted at ``Automation/`` (this file adds that).
    - Talks to the Lite 6 arm, USB barcode wedge, and RRMTool CLI via App/GuiRobot.
    - Writes results CSVs under workspace ``results/``; may update ``files/AllCards.csv``.

Run from Automation/::

    python gui/gui.py

Also reachable via ``python robot/cardreadheight.py --gui`` → ``from gui.gui import main``.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

# Ensure gui/ is importable for `import app` / sibling modules when run as script
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from app import App
import tkinter as tk


def main():
    """Create the Tk root, attach ``App``, and enter the event loop."""
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
