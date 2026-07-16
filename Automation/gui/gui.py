# gui.py — entry point for the credential read-height Tk GUI.
# Run: python gui/gui.py  (from Automation/)
"""Thin launcher. App and GuiRobot live in sibling modules."""

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
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
