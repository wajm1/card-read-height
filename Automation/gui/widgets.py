"""Tk widget helpers shared by the read-height GUI (buttons, labels, steppers)."""

import os
import sys

import tkinter as tk

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

from constants import BRAND, FONT_H2, FONT_BTN, FONT_BODY
from barcode.scanner import register_tk_text_input


def flat_button(parent, text, command, fg, bg, hover, font=FONT_BTN, pady=10, state=tk.NORMAL):
    b = tk.Button(parent, text=text, command=command, font=font, fg=fg, bg=bg,
                  activeforeground=fg, activebackground=hover, relief=tk.FLAT, bd=0,
                  padx=12, pady=pady, cursor="hand2", highlightthickness=0, state=state)
    b.bind("<Enter>", lambda e: b.config(bg=hover) if b['state'] != tk.DISABLED else None)
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def section_label(parent, text, bg=None):
    return tk.Label(parent, text=text.upper(), font=FONT_H2,
                    fg=BRAND['purple'], bg=bg or BRAND['card'])


def dot(parent, color, size=12, bg=None):
    c = tk.Canvas(parent, width=size, height=size, bg=bg or BRAND['card'], highlightthickness=0)
    cid = c.create_oval(2, 2, size - 1, size - 1, fill=color, outline="")
    c._id = cid
    return c


def number_stepper(parent, var, tk_root, *, minimum, maximum, step=1, width=4, is_float=False):
    """Entry with +/- buttons — reliable on Windows (tk.Spinbox is not)."""
    bg = parent["bg"]
    frame = tk.Frame(parent, bg=bg)

    def set_value(value):
        value = max(minimum, min(maximum, value))
        if is_float:
            var.set("{:g}".format(value))
        else:
            var.set(str(int(value)))

    def parse():
        raw = str(var.get()).strip()
        return float(raw) if is_float else int(raw)

    def bump(delta):
        try:
            set_value(parse() + delta)
        except (ValueError, tk.TclError):
            set_value(minimum)

    tk.Button(
        frame, text="−", font=FONT_BODY, width=2, relief=tk.FLAT,
        bg=BRAND["light"], fg=BRAND["text"], activebackground=BRAND["divider"],
        command=lambda: bump(-step),
    ).pack(side=tk.LEFT)
    entry = tk.Entry(
        frame, textvariable=var, width=width, font=FONT_BODY, justify="center",
        relief=tk.SOLID, bd=1, highlightthickness=1, highlightbackground=BRAND["divider"],
    )
    entry.pack(side=tk.LEFT, padx=4)
    tk.Button(
        frame, text="+", font=FONT_BODY, width=2, relief=tk.FLAT,
        bg=BRAND["light"], fg=BRAND["text"], activebackground=BRAND["divider"],
        command=lambda: bump(step),
    ).pack(side=tk.LEFT)
    register_tk_text_input(tk_root, entry)
    return frame
