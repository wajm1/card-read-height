# gui.py
# rf IDEAS — Automated Credential Read Height Testing (GUI)
# ---------------------------------------------------------------------------
# Subclasses RobotMain (robot/move.py) to add:
#   • a barcode-scanner "wave" (wrist turn + shoulder nudge — joint-space only)
#   • configurable cycles / remeasures / zone taps
#   • FOUR read-angle measurement (0°, 90°, 180°, 270°) with progressive
#     zone-in honing (each descent slower than the last) and read-height capture
#
# Flow:  device checklist  ->  test panel  ->  run  ->  CSV export
#
# Motion primitives (smart_pick, _descend_until_read, the descent/zone-in
# helpers) are the working, inherited/base ones. Fast, smooth transit
# everywhere EXCEPT the final recorded descent, which runs as slow as the
# configuration allows for the most accurate read height.
#
# NOTE ON DEPENDENCIES: this module relies on config.py, barcode/scanner.py and
# reader/cli.py. All values used from config.* are passed through unchanged.
# The four read angles are produced by rotating the *validated* inline staging
# pose about the wrist (J6); 90° reproduces the previously validated orthogonal
# pose (inline with J6 − 90). This keeps the card at one position for every
# angle — only the wrist turns.

import os
import sys
import csv
import json
import queue
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

import config
from xarm.wrapper import XArmAPI
from robot.move import RobotMain
try:
    from robot.move import CardReadListener
except Exception:      # pragma: no cover
    CardReadListener = None
from barcode.scanner import (
    BarcodeListener, lookup_card, register_tk_text_input, update_all_cards_averages,
    _normalize_avg_above_reader, is_bad_reference_height, scrub_poisoned_card_baselines,
)
from reader.cli import check_reader, configure_reader_for_card, get_reader_info

# Optional browser-based mesh viewer (three.js). Pure-stdlib server; no deps.
try:
    import robot_viewer
except Exception:            # pragma: no cover
    robot_viewer = None

# Optional EMBEDDED OpenGL mesh viewer (in-window live sim). Needs pyopengltk+PyOpenGL.
try:
    import arm_gl
except Exception:            # pragma: no cover
    arm_gl = None

from constants import (
    TELEMETRY_UDP_HOST, TELEMETRY_UDP_PORT, DEFAULT_IP, TABLE_Z,
    READ_ANGLES, LITE6_JOINT_LIMITS, JOINT_LIMIT_MARGIN_DEG,
    nearest_j6_in_range, joint_limit_issues,
    DEFAULT_READER_MODEL, FINAL_TAP_STEP_MM, DESCENT_PRESETS, DEFAULT_PRESET,
    FIXED_ZONE_TAPS, FIXED_REMEASURES,
    ZONE_REFINE_EXTRA_LIFT_MM, REFINE_CLEARANCE_MM,
    FAST_TAP_SPEED_MM_S, FAST_TAP_STEP_MM, FAST_TAP_DWELL_S,
    DROP_ANGLE, DROP_CLEARANCE_MM, DROP_HOVER_ANGLE,
    READER_STAGING_0_ANGLE, PICK_ANGLE,
    FLIP_SET_DOWN_PATH, FLIP_RETRACT_LIFT_MM, FLIP_REGRAB_POSE, FLIP_GRAB_STROKE_MM,
    FLIP_JOINT_SPEED, FLIP_JOINT_ACC, FLIP_TCP_SPEED, FLIP_TCP_ACC,
    FLIP_GRAB_TCP_SPEED, FLIP_GRAB_TCP_ACC, FLIP_RELEASE_DWELL_S, FLIP_SETTLE_S,
    CALIB_STEP_PRESETS, CALIB_DEFAULT_STEP, CALIB_JOG_TCP_SPEED, CALIB_JOG_TCP_ACC,
    CALIB_STAGING_LIFT_MM, CALIB_MIN_ABOVE_TABLE_MM,
    TAPGO_DESCENT_SPEED_MM_S, TAPGO_DESCENT_ACC, TAPGO_APPROACH_ABOVE_READER_MM,
    TAPGO_RESET_DWELL_S, TAPGO_READ_TIMEOUT_S, TAPGO_STOP_ABOVE_FLOOR_MM,
    TAPGO_CSV_HEADER, CSV_DATA_HEADER, CSV_WIDTH,
    _csv_row, _parse_saved_avg,
    WIGGLE_DEG, WIGGLE_LIFT_DEG, WIGGLE_SPEED, WIGGLE_ACC, WIGGLE_PAUSE_S,
    BRAND, FONT_H1, FONT_H2, FONT_BODY, FONT_SMALL, FONT_BTN, FONT_MONO,
    READER_HEIGHTS_PATH, SAFETY_MARGIN_MM,
    load_reader_library, READER_LIBRARY, READER_HEIGHTS, READER_TYPES,
    _reader_height_for, _default_reader_model,
)
from widgets import flat_button, section_label, dot, number_stepper
from gui_robot import GuiRobot



class _TelemetryUDP:
    """Fire-and-forget JSON/UDP sender for the optional ROS2 bridge. No ROS
    dependency, no blocking: if nothing is listening the packets are dropped."""

    def __init__(self, host=TELEMETRY_UDP_HOST, port=TELEMETRY_UDP_PORT):
        import socket
        self._addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_joints(self, joints):
        self._send({"t": "joints", "j": [round(float(a), 3) for a in joints[:6]]})

    def send_result(self, row):
        self._send({"t": "result", "row": row})

    def _send(self, obj):
        try:
            self._sock.sendto((json.dumps(obj) + "\n").encode("utf-8"), self._addr)
        except Exception:
            pass

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass

# ===========================================================================
# MAIN APP
# ===========================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("rf IDEAS — Credential Read Height Test")
        self.root.configure(bg=BRAND['bg'])
        self.root.geometry("1060x820")
        self.root.minsize(900, 600)
        self.root._pass_keys_to_gui = False
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass

        self._q = queue.Queue()
        self.worker = None
        self.robot = None
        self.arm = None
        self._last_robot = None
        self._run_id = 0                # increments each START
        self._live_csv_path = None      # alias to the first autosave file (status text)
        self._live_csv_paths = {}       # {kind: autosave path} for the current run
        # ── reader calibration (manual jog) state ──
        self._calib_arm = None
        self._calib_active = False
        self._calib_q = None
        self._calib_worker = None
        self._calib_staging_pose = None     # (reserved) captured 0° staging pose
        self._calib_reader_height = None    # captured reader height (mm, table-to-top)
        self._calib_reader_floor_above_table = None  # captured floor (mm above table)
        self._calib_busy = False
        self._calib_capturing = False       # True while MARK is capturing (blocks jogs)
        # ── live 3D view + optional ROS2 telemetry ──
        self._arm3d = None                  # ArmGLViewer (embedded Live arm; name kept for compatibility)
        self.selected_tests = ["read_height"]  # subset of ["read_height", "tap_and_go"]
        self._viewer = None                 # RobotViewerServer (browser mesh view)
        self._telem_udp = None              # _TelemetryUDP when streaming
        self._last_joints = None

        # checklist state
        self.chk = {"robot": False, "reader": False, "barcode": False}
        self._scanner = None

        # config vars
        self.ip_var = tk.StringVar(value=DEFAULT_IP)
        self.reader_type = tk.StringVar(value=_default_reader_model())
        self.reader_other = tk.StringVar(value="")
        self.cards_var = tk.StringVar(value="5")
        self.scans_var = tk.StringVar(value="1")   # recorded taps averaged per angle
        self.comment_var = tk.StringVar(value="")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.calib_step_var = tk.StringVar(value=CALIB_DEFAULT_STEP)
        self.telem_var = tk.BooleanVar(value=False)   # stream telemetry to ROS2 (UDP)
        self.reader_info = {}

        # read-angle toggles (0°, 90°, 180°, 270°) — all on by default
        self.angle_vars = {a: tk.BooleanVar(value=True) for a in READ_ANGLES}
        self.flip_var = tk.BooleanVar(value=False)

        self._style()
        self._build_header()
        self.container = tk.Frame(self.root, bg=BRAND['bg'])
        self.container.pack(fill=tk.BOTH, expand=True)
        self._build_footer()

        self.show_checklist()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)

    # ---- style ----
    def _style(self):
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure("Brand.TCombobox", fieldbackground=BRAND['white'],
                     background=BRAND['white'], foreground=BRAND['text'], padding=6)
        st.configure("Brand.Horizontal.TProgressbar", troughcolor=BRAND['light'],
                     background=BRAND['red'], thickness=16)
        st.configure("Brand.Treeview", background=BRAND['white'],
                     fieldbackground=BRAND['white'], foreground=BRAND['text'],
                     rowheight=22, font=FONT_SMALL, borderwidth=0)
        st.configure("Brand.Treeview.Heading", background=BRAND['light'],
                     foreground=BRAND['purple'], font=FONT_H2, relief=tk.FLAT)
        st.map("Brand.Treeview", background=[("selected", BRAND['light'])],
               foreground=[("selected", BRAND['dark'])])

    # ---- header / footer ----
    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BRAND['dark'], height=64)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        box = tk.Frame(hdr, bg=BRAND['dark'])
        box.pack(side=tk.LEFT, padx=20)
        tk.Label(box, text="rf", font=("Verdana", 18, "bold"), fg=BRAND['white'], bg=BRAND['dark']).pack(side=tk.LEFT, pady=13)
        tk.Label(box, text="IDEAS", font=("Verdana", 18, "bold"), fg=BRAND['red'], bg=BRAND['dark']).pack(side=tk.LEFT, pady=13)
        tk.Frame(hdr, bg=BRAND['red'], width=2, height=26).pack(side=tk.LEFT, padx=14, pady=19)
        tk.Label(hdr, text="Automated Credential Read Height Test", font=("Verdana", 11),
                 fg="#CFCFD2", bg=BRAND['dark']).pack(side=tk.LEFT, pady=18)

        pill = tk.Frame(hdr, bg="#2A2A2E")
        pill.pack(side=tk.RIGHT, padx=20, pady=16)
        self.reader_dot = dot(pill, BRAND['amber'], 10, bg="#2A2A2E")
        self.reader_dot.pack(side=tk.LEFT, padx=(10, 6), pady=7)
        self.reader_pill = tk.Label(pill, text="Reader: unknown", font=FONT_SMALL, fg="#CFCFD2", bg="#2A2A2E")
        self.reader_pill.pack(side=tk.LEFT, padx=(0, 12), pady=4)

    def _set_reader_pill(self, text, color):
        self.reader_pill.config(text=text)
        self.reader_dot.itemconfig(self.reader_dot._id, fill=color)

    def _build_footer(self):
        bar = tk.Frame(self.root, bg=BRAND['white'], height=32, highlightthickness=1,
                       highlightbackground=BRAND['divider'])
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)
        self.status_var = tk.StringVar(value="Complete the device checklist to begin")
        tk.Label(bar, textvariable=self.status_var, font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['white']).pack(side=tk.LEFT, padx=14)
        self.time_var = tk.StringVar()
        tk.Label(bar, textvariable=self.time_var, font=FONT_SMALL, fg=BRAND['border'],
                 bg=BRAND['white']).pack(side=tk.RIGHT, padx=14)
        tk.Label(bar, text="Proprietary and Confidential", font=FONT_SMALL,
                 fg=BRAND['border'], bg=BRAND['white']).pack(side=tk.RIGHT, padx=14)
        self._clock()

    def _clock(self):
        self.time_var.set(datetime.now().strftime("%b-%d-%Y  %H:%M:%S"))
        self.root.after(1000, self._clock)

    def set_status(self, msg):
        self.status_var.set(msg)

    def _clear_container(self):
        for w in self.container.winfo_children():
            w.destroy()

    # =====================================================================
    # CHECKLIST SCREEN
    # =====================================================================
    def show_checklist(self):
        self._clear_container()
        wrap = tk.Frame(self.container, bg=BRAND['bg'])
        wrap.pack(expand=True)

        card = tk.Frame(wrap, bg=BRAND['card'], highlightthickness=1,
                        highlightbackground=BRAND['divider'])
        card.pack(padx=20, pady=24, ipadx=10, ipady=10)
        pad = tk.Frame(card, bg=BRAND['card'])
        pad.pack(padx=34, pady=26)

        tk.Label(pad, text="Pre-Run Device Check", font=FONT_H1, fg=BRAND['text'],
                 bg=BRAND['card']).pack(anchor=tk.W)
        tk.Label(pad, text="All checks must pass before the test panel unlocks.",
                 font=FONT_SMALL, fg=BRAND['purple'], bg=BRAND['card']).pack(anchor=tk.W, pady=(2, 16))

        iprow = tk.Frame(pad, bg=BRAND['card'])
        iprow.pack(anchor=tk.W, pady=(0, 14))
        tk.Label(iprow, text="Robot IP", font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card']).pack(side=tk.LEFT)
        ip_entry = tk.Entry(iprow, textvariable=self.ip_var, font=FONT_BODY, width=16)
        ip_entry.pack(side=tk.LEFT, padx=10)
        register_tk_text_input(self.root, ip_entry)

        self.chk_rows = {}
        for key, label in [("robot", "Robot arm connected & ready"),
                           ("reader", "Card reader connected (USB)"),
                           ("barcode", "Barcode scanner — scan to confirm")]:
            self.chk_rows[key] = self._check_row(pad, key, label)

        tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=16)

        self.continue_btn = flat_button(pad, "CONTINUE TO TEST  →", self.show_test_select,
                                        fg=BRAND['white'], bg=BRAND['border'],
                                        hover=BRAND['border'], state=tk.DISABLED)
        self.continue_btn.pack(fill=tk.X, pady=(0, 4))

        # Subtle skip — bypasses the checks when you already know the rig is good.
        skip_row = tk.Frame(pad, bg=BRAND['card'])
        skip_row.pack(fill=tk.X, pady=(6, 0))
        skip = tk.Label(skip_row, text="Skip checks →", font=FONT_SMALL,
                        fg=BRAND['subtle'], bg=BRAND['card'], cursor="hand2")
        skip.pack(side=tk.RIGHT)
        skip.bind("<Button-1>", lambda _e: self.show_test_select())
        skip.bind("<Enter>", lambda _e: skip.config(fg=BRAND['red']))
        skip.bind("<Leave>", lambda _e: skip.config(fg=BRAND['subtle']))

    def _check_row(self, parent, key, label, test_text="TEST"):
        row = tk.Frame(parent, bg=BRAND['card'])
        row.pack(fill=tk.X, pady=5)
        d = dot(row, BRAND['border'], 14)
        d.pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(row, text=label, font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card'],
                 width=34, anchor=tk.W).pack(side=tk.LEFT)
        state_lbl = tk.Label(row, text="pending", font=FONT_SMALL, fg=BRAND['border'],
                             bg=BRAND['card'], width=10, anchor=tk.W)
        state_lbl.pack(side=tk.LEFT, padx=8)
        btn = flat_button(row, test_text, lambda k=key: self._run_check(k),
                          fg=BRAND['white'], bg=BRAND['red'], hover=BRAND['red_hover'], pady=6)
        btn.pack(side=tk.RIGHT)
        return {"dot": d, "state": state_lbl, "btn": btn}

    def _set_check(self, key, ok, msg):
        self.chk[key] = ok
        r = self.chk_rows[key]
        color = BRAND['green'] if ok else BRAND['red']
        r["dot"].itemconfig(r["dot"]._id, fill=color)
        r["state"].config(text="pass ✓" if ok else "fail ✗", fg=color)
        if msg:
            self.set_status(msg)
        if all(self.chk[k] for k in ("robot", "reader", "barcode")):
            self._enable_continue()

    def _enable_continue(self):
        self.continue_btn.config(state=tk.NORMAL, bg=BRAND['green'])
        self.continue_btn.bind("<Enter>", lambda e: self.continue_btn.config(bg=BRAND['green']))
        self.continue_btn.bind("<Leave>", lambda e: self.continue_btn.config(bg=BRAND['green']))

    def _run_check(self, key):
        if key == "robot":
            self.set_status("Checking robot connection...")
            threading.Thread(target=self._check_robot, daemon=True).start()
        elif key == "reader":
            self.set_status("Checking card reader...")
            threading.Thread(target=self._check_reader_dev, daemon=True).start()
        elif key == "barcode":
            self._check_barcode()

    def _check_robot(self):
        try:
            arm = XArmAPI(self.ip_var.get().strip(), baud_checkset=False)
            time.sleep(0.5)
            ok = bool(arm.connected)
            try:
                arm.disconnect()
            except Exception:
                pass
            self.root.after(0, self._set_check, "robot", ok,
                            "Robot OK" if ok else "Robot not reachable — check IP/cable")
        except Exception as e:
            self.root.after(0, self._set_check, "robot", False, "Robot error: {}".format(e))

    def _check_reader_dev(self):
        try:
            ok, _ = check_reader()
            info = get_reader_info()
            if info:
                ok = True
                self.reader_info = info
                model = info.get("Part-Number", "Unknown")
                fw = info.get("USB-Firmware", "?")
                self.root.after(0, self._set_reader_pill, "Reader: {}  FW {}".format(model, fw), BRAND['green'])
            self.root.after(0, self._set_check, "reader", ok,
                            "Reader OK" if ok else "No reader detected over USB")
        except Exception as e:
            self.root.after(0, self._set_check, "reader", False, "Reader error: {}".format(e))

    def _check_barcode(self):
        self.set_status("Scan any barcode now to confirm the scanner (15s)...")
        self.chk_rows["barcode"]["state"].config(text="scan…", fg=BRAND['amber'])
        done = {"v": False}

        def on_bc(_bc):
            if done["v"]:
                return
            done["v"] = True
            try:
                self._scanner.stop()
            except Exception:
                pass
            self.root.after(0, self._set_check, "barcode", True, "Barcode scanner OK")

        self._scanner = BarcodeListener(on_bc, tk_root=self.root)
        self._scanner.start()

        def timeout():
            time.sleep(15)
            if not done["v"]:
                try:
                    self._scanner.stop()
                except Exception:
                    pass
                self.root.after(0, self._set_check, "barcode", False,
                                "No scan detected — check scanner USB")
        threading.Thread(target=timeout, daemon=True).start()

    # =====================================================================
    # MAIN TEST SCREEN
    # =====================================================================
    def _has_read_height(self):
        return "read_height" in self.selected_tests

    def _has_tapgo(self):
        return "tap_and_go" in self.selected_tests

    def _tests_label(self):
        names = []
        if self._has_read_height():
            names.append("Read Height")
        if self._has_tapgo():
            names.append("Tap and Go")
        return " + ".join(names) if names else "Read Height"

    def show_test_select(self):
        """Pick which test(s) to run after the device checks pass. Tests can be
        combined — tick both to run Read Height and Tap-and-Go on each card."""
        self._clear_container()
        wrap = tk.Frame(self.container, bg=BRAND['bg'])
        wrap.pack(expand=True)
        card = tk.Frame(wrap, bg=BRAND['card'], highlightthickness=1,
                        highlightbackground=BRAND['divider'])
        card.pack(padx=20, pady=24, ipadx=10, ipady=10)
        pad = tk.Frame(card, bg=BRAND['card'])
        pad.pack(padx=40, pady=32)

        tk.Label(pad, text="Choose test(s)", font=FONT_H1, fg=BRAND['text'],
                 bg=BRAND['card']).pack(anchor=tk.W)
        tk.Label(pad, text="Tick one or both. Every test scans the barcode and "
                           "configures the reader first. Selecting both runs Read "
                           "Height then Tap-and-Go on each card.",
                 font=FONT_SMALL, fg=BRAND['purple'], bg=BRAND['card'],
                 justify="left", wraplength=460).pack(anchor=tk.W, pady=(2, 20))

        # selection state (persist previous choice)
        self._sel_vars = {
            "read_height": tk.BooleanVar(value=self._has_read_height()),
            "tap_and_go": tk.BooleanVar(value=self._has_tapgo()),
        }

        def _refresh_card_styles():
            for kind, fr in self._sel_cards.items():
                on = self._sel_vars[kind].get()
                fr.config(highlightbackground=BRAND['red'] if on else BRAND['divider'],
                          highlightthickness=2 if on else 1)
            # Continue enabled only if at least one is ticked
            any_on = any(v.get() for v in self._sel_vars.values())
            self._continue_btn.config(state=tk.NORMAL if any_on else tk.DISABLED)

        self._sel_cards = {}

        def test_card(title, desc, kind):
            b = tk.Frame(pad, bg=BRAND['light'], highlightthickness=1,
                         highlightbackground=BRAND['divider'], cursor="hand2")
            b.pack(fill=tk.X, pady=(0, 12), ipadx=6, ipady=6)
            self._sel_cards[kind] = b
            head = tk.Frame(b, bg=BRAND['light'])
            head.pack(fill=tk.X, padx=16, pady=(10, 2))
            cbx = tk.Checkbutton(
                head, variable=self._sel_vars[kind], bg=BRAND['light'],
                activebackground=BRAND['light'], selectcolor=BRAND['white'],
                highlightthickness=0, bd=0, command=_refresh_card_styles,
            )
            cbx.pack(side=tk.LEFT)
            tk.Label(head, text=title, font=FONT_H2, fg=BRAND['text'],
                     bg=BRAND['light']).pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(b, text=desc, font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['light'],
                     justify="left", wraplength=440).pack(anchor=tk.W, padx=16, pady=(0, 10))

            def _toggle(_e=None):
                self._sel_vars[kind].set(not self._sel_vars[kind].get())
                _refresh_card_styles()
            # clicking the row toggles (but let the checkbox handle its own click)
            for w in (b,) + tuple(head.winfo_children()) + tuple(b.winfo_children()):
                if w is cbx:
                    continue
                w.bind("<Button-1>", _toggle)

        test_card(
            "Read Height",
            "Lower the card slowly at 0°/90°/180°/270° until the reader reads, "
            "recording the height above the reader top. The full characterization test.",
            "read_height")
        test_card(
            "Tap and Go",
            "Plunge the card from ~100 mm above the reader at max speed to the "
            "reference point, then time how long the reader takes to read (ms). "
            "Repeats per card, optional flip, then drop.",
            "tap_and_go")

        def _continue():
            chosen = [k for k in ("read_height", "tap_and_go") if self._sel_vars[k].get()]
            if not chosen:
                return
            self.selected_tests = chosen
            self.show_main()

        self._continue_btn = flat_button(
            pad, "CONTINUE", _continue,
            fg=BRAND['white'], bg=BRAND['red'], hover=BRAND['red_hover'])
        self._continue_btn.pack(fill=tk.X, pady=(4, 0))

        back = tk.Label(pad, text="← Back to checks", font=FONT_SMALL,
                        fg=BRAND['subtle'], bg=BRAND['card'], cursor="hand2")
        back.pack(anchor=tk.W, pady=(10, 0))
        back.bind("<Button-1>", lambda _e: self.show_checklist())
        _refresh_card_styles()

    def show_main(self):
        try:
            if self._scanner:
                self._scanner.stop()
                self._scanner = None
        except Exception:
            pass
        self._clear_container()
        main = tk.Frame(self.container, bg=BRAND['bg'])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        # ---- left: setup (scrollable so it fits any screen height) ----
        left = tk.Frame(main, bg=BRAND['card'], width=392, highlightthickness=1,
                        highlightbackground=BRAND['divider'])
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        setup_canvas = tk.Canvas(left, bg=BRAND['card'], highlightthickness=0, bd=0)
        setup_scroll = ttk.Scrollbar(left, orient="vertical", command=setup_canvas.yview)
        setup_canvas.configure(yscrollcommand=setup_scroll.set)
        setup_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        setup_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        pad = tk.Frame(setup_canvas, bg=BRAND['card'])
        pad_window = setup_canvas.create_window((0, 0), window=pad, anchor="nw")

        def _sync_scrollregion(_e=None):
            setup_canvas.configure(scrollregion=setup_canvas.bbox("all"))

        def _sync_pad_width(e):
            # make the inner frame track the canvas width (minus a little padding)
            setup_canvas.itemconfigure(pad_window, width=e.width)

        pad.bind("<Configure>", _sync_scrollregion)
        setup_canvas.bind("<Configure>", _sync_pad_width)

        # mouse wheel — only while the pointer is over the setup panel, so it
        # doesn't fight the results/log scrolling elsewhere
        def _wheel(e):
            setup_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _wheel_linux(e):
            setup_canvas.yview_scroll(-1 if e.num == 4 else 1, "units")

        def _bind_wheel(_e=None):
            setup_canvas.bind_all("<MouseWheel>", _wheel)
            setup_canvas.bind_all("<Button-4>", _wheel_linux)
            setup_canvas.bind_all("<Button-5>", _wheel_linux)

        def _unbind_wheel(_e=None):
            setup_canvas.unbind_all("<MouseWheel>")
            setup_canvas.unbind_all("<Button-4>")
            setup_canvas.unbind_all("<Button-5>")

        setup_canvas.bind("<Enter>", _bind_wheel)
        setup_canvas.bind("<Leave>", _unbind_wheel)

        inner = tk.Frame(pad, bg=BRAND['card'])
        inner.pack(fill=tk.BOTH, expand=True, padx=22, pady=18)
        pad = inner   # everything below packs into the padded inner frame

        section_label(pad, "Test setup").pack(anchor=tk.W)

        self._field(pad, "Reader type")
        rt = ttk.Combobox(pad, textvariable=self.reader_type, values=READER_TYPES,
                          state="readonly", style="Brand.TCombobox", font=FONT_BODY)
        rt.pack(fill=tk.X)
        rt.bind("<<ComboboxSelected>>", self._on_reader_selected)
        self.other_entry = tk.Entry(pad, textvariable=self.reader_other, font=FONT_BODY)
        register_tk_text_input(self.root, self.other_entry)
        self._toggle_other()        # show OTHER field only when needed

        self._field(pad, "Comment (file header)")
        comment_entry = tk.Entry(pad, textvariable=self.comment_var, font=FONT_BODY)
        comment_entry.pack(fill=tk.X)
        register_tk_text_input(self.root, comment_entry)

        # numeric parameters — Cards
        grid = tk.Frame(pad, bg=BRAND['card'])
        grid.pack(fill=tk.X, pady=(12, 0))
        tk.Label(grid, text="Cards", font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['card']).grid(row=0, column=0, sticky="w", padx=(0, 14))
        number_stepper(
            grid, self.cards_var, self.root, minimum=1, maximum=200, step=1, width=4,
        ).grid(row=1, column=0, sticky="w", padx=(0, 14), pady=(2, 0))
        has_rh = self._has_read_height()
        has_tg = self._has_tapgo()
        if has_rh and has_tg:
            _taps_hint = "(read-height averages + tap-and-go timings, per angle)"
        elif has_tg:
            _taps_hint = "(fast taps timed per angle, per side)"
        else:
            _taps_hint = "(recorded measurements averaged per angle)"
        tk.Label(grid, text="Taps per angle", font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['card']).grid(row=0, column=1, sticky="w", padx=(0, 14))
        number_stepper(
            grid, self.scans_var, self.root, minimum=1, maximum=50, step=1, width=4,
        ).grid(row=1, column=1, sticky="w", pady=(2, 0))
        tk.Label(grid, text=_taps_hint,
                 font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card']).grid(
                     row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        # Read-height uses a descent-speed preset (controls the recorded taps).
        if has_rh:
            self._field(pad, "Test speed (read height)")
            speed_combo = ttk.Combobox(
                pad, textvariable=self.preset_var, values=list(DESCENT_PRESETS.keys()),
                state="readonly", style="Brand.TCombobox", font=FONT_BODY,
            )
            speed_combo.pack(fill=tk.X)
            self.preset_hint = tk.Label(
                pad, text=self._preset_hint(self.preset_var.get()),
                font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'],
                anchor="w", justify="left", wraplength=320,
            )
            self.preset_hint.pack(anchor=tk.W, pady=(4, 0))
            speed_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Tap-and-Go plunges at max speed to the calibrated reference point.
        if has_tg:
            tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=14)
            section_label(pad, "Tap and Go").pack(anchor=tk.W)
            tk.Label(pad, text=("Plunges from ~{:.0f} mm above the reader at "
                                "{:.0f} mm/s (Lite 6 max) to the reader top, then "
                                "times the read (ms). Lifts and waits {:.1f}s between "
                                "taps so the reader resets. Calibrate the reader first.".format(
                                    TAPGO_APPROACH_ABOVE_READER_MM, TAPGO_DESCENT_SPEED_MM_S,
                                    TAPGO_RESET_DWELL_S)),
                     font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'],
                     justify="left", wraplength=320).pack(anchor=tk.W, pady=(1, 0))

        # read-angle toggles (both tests present the card at each ticked angle)
        tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=14)
        section_label(pad, "Read angles").pack(anchor=tk.W)
        tk.Label(pad, text="Card rotation about its face — tick the angles to test.",
                 font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card']).pack(anchor=tk.W, pady=(1, 6))
        ang_row = tk.Frame(pad, bg=BRAND['card'])
        ang_row.pack(fill=tk.X)
        for a in READ_ANGLES:
            cb = tk.Checkbutton(
                ang_row, text="{}°".format(a), variable=self.angle_vars[a],
                font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card'],
                activebackground=BRAND['card'], activeforeground=BRAND['red'],
                selectcolor=BRAND['white'], highlightthickness=0, bd=0,
                anchor="w", padx=2,
            )
            cb.pack(side=tk.LEFT, padx=(0, 14))

        # flip toggle (test both sides)
        tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=14)
        section_label(pad, "Both sides").pack(anchor=tk.W)
        tk.Checkbutton(
            pad, text="Flip test — after side A, flip the card and test side B",
            variable=self.flip_var,
            font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card'],
            activebackground=BRAND['card'], activeforeground=BRAND['red'],
            selectcolor=BRAND['white'], highlightthickness=0, bd=0,
            anchor="w", padx=2, wraplength=300, justify="left",
        ).pack(anchor=tk.W, pady=(1, 0))
        tk.Label(pad, text="Uses the flip fixture, then re-scans + tests the back "
                           "before dropping.",
                 font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'],
                 wraplength=300, justify="left").pack(anchor=tk.W, pady=(2, 0))

        # gap before the action buttons
        tk.Frame(pad, bg=BRAND['card'], height=18).pack(fill=tk.X)

        self.start_btn = flat_button(pad, "START TEST", self._on_start,
                                     fg=BRAND['white'], bg=BRAND['red'], hover=BRAND['red_hover'])
        self.start_btn.pack(fill=tk.X, pady=(0, 6))
        self.stop_btn = flat_button(pad, "STOP / ABORT", self._on_stop,
                                    fg=BRAND['red'], bg=BRAND['card'], hover="#FBEAEA",
                                    state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=(0, 6))
        self.calib_btn = flat_button(pad, "CALIBRATE READER", self.show_calibrator,
                                     fg=BRAND['purple'], bg=BRAND['card'], hover=BRAND['light'],
                                     font=FONT_SMALL, pady=6)
        self.calib_btn.pack(fill=tk.X, pady=(0, 6))
        self.mesh_btn = flat_button(pad, "OPEN 3D MESH VIEW (browser)", self._open_mesh_viewer,
                                    fg=BRAND['purple'], bg=BRAND['card'], hover=BRAND['light'],
                                    font=FONT_SMALL, pady=6)
        self.mesh_btn.pack(fill=tk.X, pady=(0, 6))
        self.export_btn = flat_button(pad, "EXPORT CSV", self._on_export,
                                      fg=BRAND['text'], bg=BRAND['light'], hover=BRAND['divider'],
                                      font=FONT_SMALL, pady=6)
        self.export_btn.pack(fill=tk.X, pady=(0, 6))
        tk.Checkbutton(
            pad, text="Stream telemetry to ROS2 (UDP :{})".format(TELEMETRY_UDP_PORT),
            variable=self.telem_var, command=self._on_telem_toggle,
            font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'],
            activebackground=BRAND['card'], selectcolor=BRAND['white'],
            highlightthickness=0, bd=0, anchor="w",
        ).pack(fill=tk.X)

        # ---- right: progress + log ----
        right = tk.Frame(main, bg=BRAND['card'], highlightthickness=1,
                         highlightbackground=BRAND['divider'])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        rp = tk.Frame(right, bg=BRAND['card'])
        rp.pack(fill=tk.BOTH, expand=True, padx=18, pady=16)

        # ── embedded live 3D mesh view (OpenGL) ──
        section_label(rp, "Live arm").pack(anchor=tk.W)
        arm_holder = tk.Frame(rp, bg=BRAND['card'], height=240)
        arm_holder.pack(fill=tk.X, pady=(4, 10))
        arm_holder.pack_propagate(False)
        self._arm3d = None
        _Viewer = getattr(arm_gl, "ArmGLViewer", None) if arm_gl is not None else None
        if _Viewer is not None:
            try:
                mesh_dir = os.path.join(self._viewer_dir(), "meshes", "visual")
                self._arm3d = _Viewer(arm_holder, mesh_dir,
                                      brand={"bg3d": "#1b1d23"})
                self._arm3d.frame.pack(fill=tk.BOTH, expand=True)
                if self._last_joints:
                    self._arm3d.update(self._last_joints, force=True)
            except Exception as e:
                self._arm3d = None
                tk.Label(arm_holder, text="3D view failed to start:\n{}".format(e),
                         fg=BRAND['subtle'], bg=BRAND['card'], justify="center").pack(expand=True)
        else:
            tk.Label(
                arm_holder,
                text=("Embedded 3D needs pyopengltk + PyOpenGL.\n"
                      "Install:  py -3.14 -m pip install pyopengltk PyOpenGL\n"
                      "(meshes must be in viewer\\meshes\\visual\\)"),
                fg=BRAND['subtle'], bg=BRAND['card'], justify="center").pack(expand=True)

        topr = tk.Frame(rp, bg=BRAND['card'])
        topr.pack(fill=tk.X)
        section_label(topr, "Progress").pack(side=tk.LEFT)
        self.passfail_dot = dot(topr, BRAND['border'], 16)
        self.passfail_dot.pack(side=tk.RIGHT)
        self.passfail_lbl = tk.Label(topr, text="—", font=FONT_BTN, fg=BRAND['border'], bg=BRAND['card'])
        self.passfail_lbl.pack(side=tk.RIGHT, padx=8)

        self.progress_lbl = tk.Label(rp, text="Idle", font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card'], anchor=tk.W)
        self.progress_lbl.pack(fill=tk.X, pady=(8, 4))
        self.pbar = ttk.Progressbar(rp, style="Brand.Horizontal.TProgressbar", maximum=100)
        self.pbar.pack(fill=tk.X)

        # ── live results + activity log (tabbed, so it stays organized and
        #    fits — one results table per selected test, plus the log) ──
        section_label(rp, "Results & log").pack(anchor=tk.W, pady=(12, 4))
        nb = ttk.Notebook(rp)
        nb.pack(fill=tk.BOTH, expand=True)

        RH_COLS = ("card", "code", "side", "a0", "a90", "a180", "a270", "note")
        RH_HEAD = {"card": "#", "code": "Barcode", "side": "Side",
                   "a0": "0°", "a90": "90°", "a180": "180°", "a270": "270°", "note": "Note"}
        RH_W = {"card": 34, "code": 64, "side": 36, "a0": 52, "a90": 52,
                "a180": 52, "a270": 52, "note": 120}
        TG_COLS = ("card", "code", "side", "ang", "reads", "avg", "min", "max", "note")
        TG_HEAD = {"card": "#", "code": "Barcode", "side": "Side", "ang": "Angle",
                   "reads": "Reads", "avg": "Avg ms", "min": "Min ms",
                   "max": "Max ms", "note": "Note"}
        TG_W = {"card": 30, "code": 58, "side": 34, "ang": 44, "reads": 44,
                "avg": 52, "min": 48, "max": 48, "note": 96}

        def _make_tree(cols, headers, widths):
            tab = tk.Frame(nb, bg=BRAND['card'])
            tw = tk.Frame(tab, bg=BRAND['card'])
            tw.pack(fill=tk.BOTH, expand=True)
            tree = ttk.Treeview(tw, columns=cols, show="headings", height=6,
                                 style="Brand.Treeview")
            for c in cols:
                tree.heading(c, text=headers[c])
                tree.column(c, width=widths[c], minwidth=28,
                            anchor=("w" if c in ("code", "note") else "center"),
                            stretch=(c == "note"))
            sb = ttk.Scrollbar(tw, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=sb.set)
            tree.tag_configure("err", foreground=BRAND['amber'])
            tree.tag_configure("ok", foreground=BRAND['text'])
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            return tab, tree

        self.results_trees = {}
        if self._has_read_height():
            tab, tree = _make_tree(RH_COLS, RH_HEAD, RH_W)
            nb.add(tab, text="Read Height")
            self.results_trees["read_height"] = tree
        if self._has_tapgo():
            tab, tree = _make_tree(TG_COLS, TG_HEAD, TG_W)
            nb.add(tab, text="Tap and Go")
            self.results_trees["tap_and_go"] = tree
        # default alias for any legacy reference to a single tree
        self.results_tree = next(iter(self.results_trees.values()), None)

        # Activity log — its own tab to save vertical space
        log_tab = tk.Frame(nb, bg=BRAND['card'])
        self.log = scrolledtext.ScrolledText(log_tab, font=FONT_MONO, bg=BRAND['log_bg'],
                                             fg="#9FE8B8", insertbackground="white",
                                             relief=tk.FLAT, padx=10, pady=8, height=6,
                                             state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)
        nb.add(log_tab, text="Activity log")

        self.set_status("Ready — set parameters and press START")

    def _field(self, parent, text):
        tk.Label(parent, text=text, font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['card']).pack(anchor=tk.W, pady=(10, 2))

    def _toggle_other(self, _e=None):
        if self.reader_type.get() == "OTHER":
            self.other_entry.pack(fill=tk.X, pady=(4, 0))
        else:
            self.other_entry.pack_forget()

    def _on_reader_selected(self, _e=None):
        self._toggle_other(_e)
        # A calibration belongs to the reader it was marked on — clear it when
        # switching readers so stale values can't carry over.
        self._calib_reader_floor_above_table = None
        self._calib_staging_pose = None
        self._calib_reader_height = None

    def _effective_reader_height(self):
        """Reader height (mm, table-to-top): the value captured by MARK READER
        TOP if this reader was calibrated this session, otherwise the nominal
        height from card_readers.json for the selected type."""
        if self._calib_reader_height is not None:
            return self._calib_reader_height
        return _reader_height_for(self.reader_type.get())

    def _selected_angles(self):
        """Angles ticked in the GUI (falls back to 0° if none selected)."""
        angles = [a for a in READ_ANGLES if self.angle_vars[a].get()]
        return angles or [0]

    @staticmethod
    def _preset_hint(name):
        """One-line description of what the selected preset does."""
        p = DESCENT_PRESETS.get(name, DESCENT_PRESETS[DEFAULT_PRESET])
        return "Final tap: {:g}mm step @ {:g} mm/s".format(
            p["final_step_mm"], p["final_speed_mm_s"]
        )

    def _on_preset_selected(self, _e=None):
        """Update the hint line under the dropdown when the preset changes."""
        if hasattr(self, "preset_hint"):
            self.preset_hint.config(text=self._preset_hint(self.preset_var.get()))

    def _log(self, msg):
        self._q.put(("log", msg))

    def _append_log(self, msg):
        # The log widget only exists on the main test screen. On other screens
        # (e.g. the calibrator) it's been destroyed, so fall back to the status
        # bar instead of writing to a dead widget.
        log = getattr(self, "log", None)
        try:
            alive = log is not None and int(log.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            self.set_status(msg[-90:])
            return
        try:
            log.configure(state=tk.NORMAL)
            log.insert(tk.END, msg + "\n")
            # Keep the log bounded so long runs stay responsive — drop the
            # oldest lines once we exceed the cap.
            line_count = int(log.index('end-1c').split('.')[0])
            if line_count > 2000:
                log.delete('1.0', '{}.0'.format(line_count - 1500))
            log.see(tk.END)
            log.configure(state=tk.DISABLED)
        except (ValueError, tk.TclError):
            self.set_status(msg[-90:])

    def _poll(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "telemetry":
                    self._feed_telemetry(payload)
                elif kind == "progress":
                    cycle, total, phase = payload
                    if hasattr(self, "progress_lbl"):
                        self.progress_lbl.config(text="Card {} of {} — {}".format(cycle, total, phase))
                    if hasattr(self, "pbar"):
                        self.pbar['value'] = (cycle - 1) / max(total, 1) * 100
                    self.root.title("rf IDEAS — Running ({}/{})".format(cycle, total))
                elif kind == "result":
                    # Autosave first — durability before UI. Create the file(s)
                    # on the first result (robot config is ready by now).
                    if not self._live_csv_paths and self.robot is not None:
                        try:
                            self._open_live_csv(self.robot)
                        except Exception as e:
                            self._log("Autosave open failed: {}".format(e))
                    self._append_live_row(payload)
                    if self._telem_udp is not None:
                        self._telem_udp.send_result(payload)
                    if hasattr(self, "passfail_lbl"):
                        self._handle_result(payload)
                    self._add_result_row(payload)
                elif kind == "done":
                    self._on_run_finished(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _add_result_row(self, row):
        """Insert one card's result into the matching live results table."""
        trees = getattr(self, "results_trees", None)
        if not trees:
            return

        def cell(v):
            return "{:.2f}".format(v) if isinstance(v, (int, float)) else (v if v not in (None, "") else "—")

        note = row.get("error_skip") or ""
        kind = row.get("kind", "read_height")
        tree = trees.get(kind)
        if tree is None:
            return
        if kind == "tap_and_go":
            values = (
                row.get("card_num", ""),
                row.get("card_code", ""),
                row.get("side", ""),
                row.get("angle", ""),
                "{}/{}".format(row.get("reads", 0), row.get("taps", 0)),
                cell(row.get("avg_ms")),
                cell(row.get("min_ms")),
                cell(row.get("max_ms")),
                note,
            )
        else:
            values = (
                row.get("card_num", ""),
                row.get("card_code", ""),
                row.get("side", ""),
                cell(row.get("a0_avg")),
                cell(row.get("a90_avg")),
                cell(row.get("a180_avg")),
                cell(row.get("a270_avg")),
                note,
            )
        tag = "err" if note else "ok"
        tree.insert("", "end", values=values, tags=(tag,))
        children = tree.get_children()
        if children:
            tree.see(children[-1])

    def _handle_result(self, row):
        if row.get("kind") == "tap_and_go":
            avg = row.get("avg_ms")
            if avg == "" or avg is None:
                self.passfail_lbl.config(text="NO READ", fg=BRAND['amber'])
                self.passfail_dot.itemconfig(self.passfail_dot._id, fill=BRAND['amber'])
            else:
                self.passfail_lbl.config(text="{:.1f} ms".format(float(avg)), fg=BRAND['green'])
                self.passfail_dot.itemconfig(self.passfail_dot._id, fill=BRAND['green'])
            return
        mx = row.get("card_max")
        if mx == "" or mx is None:
            self.passfail_lbl.config(text="NO READ", fg=BRAND['amber'])
            self.passfail_dot.itemconfig(self.passfail_dot._id, fill=BRAND['amber'])
        else:
            self.passfail_lbl.config(
                text="{:.2f} mm".format(float(mx)), fg=BRAND['green'],
            )
            self.passfail_dot.itemconfig(self.passfail_dot._id, fill=BRAND['green'])

    def _spin_int(self, var, default, minimum=1):
        try:
            return max(minimum, int(str(var.get()).strip()))
        except (ValueError, tk.TclError):
            return default

    def _on_start(self):
        if self.worker and self.worker.is_alive():
            return
        if self._calib_active:
            messagebox.showinfo("Calibrating", "Finish reader calibration (Back) before starting a test.")
            return
        self._start_run(cycles=self._spin_int(self.cards_var, 5), verify=False)

    def _start_run(self, cycles, verify):
        # New run: bump the run id, start a fresh autosave file, clear the
        # live results table.
        self._run_id += 1
        self._live_csv_path = None
        self._live_csv_paths = {}
        if getattr(self, "results_trees", None):
            for _tree in self.results_trees.values():
                for item in _tree.get_children():
                    _tree.delete(item)
        if hasattr(self, "start_btn"):
            self.start_btn.config(state=tk.DISABLED)
        if hasattr(self, "stop_btn"):
            self.stop_btn.config(state=tk.NORMAL)
        if hasattr(self, "pbar"):
            self.pbar['value'] = 0
        self.root.title("rf IDEAS — Running (0/{})".format(cycles))
        self.set_status("Verification run (1 card)..." if verify else "Test running...")
        self.worker = threading.Thread(target=self._run_worker, args=(cycles, verify), daemon=True)
        self.worker.start()

    def _run_worker(self, cycles, verify):
        old_stdout = sys.stdout
        try:
            sys.stdout = _StdoutToQueue(self._q)
            self._log("Connecting to {} ...".format(self.ip_var.get().strip()))
            arm = XArmAPI(self.ip_var.get().strip(), baud_checkset=False)
            time.sleep(0.5)

            # ── Verify the arm is actually connected and not stuck in a fault ──
            if not arm.connected:
                self._q.put(("log", "ERROR: Robot not connected — check IP/cable. Run aborted."))
                return
            robot = GuiRobot(arm)          # __init__ clears warn/error + enables motion
            robot.init_gui()
            # After init the arm should be clear. If it's still faulted (a
            # latched state=4 or a live error code from a previous crash), do
            # NOT plow through the whole card stack doing nothing — stop now
            # and tell the operator to clear it in UFACTORY Studio.
            time.sleep(0.2)
            if arm.error_code != 0:
                self._q.put((
                    "log",
                    "ERROR: Arm reports error code {} after reset. Clear the error "
                    "on the arm (UFACTORY Studio) and try again. Run aborted.".format(arm.error_code),
                ))
                return
            if arm.state is not None and arm.state >= 4:
                self._q.put((
                    "log",
                    "ERROR: Arm is in a stopped/fault state ({}) and won't move. Clear "
                    "it in UFACTORY Studio, then retry. Run aborted.".format(arm.state),
                ))
                return
            # ── Pre-flight: refuse to start if a joint sits at/past a limit.
            # This is the usual cause of the C23 fault loop: the arm enables,
            # motion starts, and ~seconds later the limit re-trips (state=4).
            ret = arm.get_servo_angle()
            if ret[0] == 0 and ret[1]:
                issues = joint_limit_issues(list(ret[1])[:6])
                if issues:
                    self._q.put(("log", "ERROR: joint at/past its limit — this re-triggers C23 as soon as motion starts:"))
                    for msg in issues:
                        self._q.put(("log", "   " + msg))
                    self._q.put((
                        "log",
                        "   FIX: UFACTORY Studio → Manual Mode → drag the joint(s) back toward "
                        "mid-range → Clear Error → Enable. Then start the run again. Run aborted.",
                    ))
                    return

            robot.tk_root = self.root
            robot.cfg_tests = list(self.selected_tests)
            # legacy single-string field kept for any older reference
            robot.cfg_test = ("tap_and_go" if self.selected_tests == ["tap_and_go"]
                              else "read_height")
            robot.cfg_cycles = cycles
            robot.cfg_run_id = self._run_id            # per-run id (see _on_start)
            robot.cfg_scans = max(1, self._spin_int(self.scans_var, 1))  # taps averaged per angle
            robot.cfg_taps = FIXED_ZONE_TAPS           # hard-coded to 3
            robot.cfg_angles = self._selected_angles()
            robot.cfg_flip = bool(self.flip_var.get())
            # If a reader was calibrated this session, use its captured staging
            # pose (position/orientation over the reader) and descent floor.
            if self._calib_staging_pose is not None:
                robot.cfg_staging_0 = list(self._calib_staging_pose)
            robot.apply_preset(self.preset_var.get())  # sets descent speeds/steps
            robot.cfg_reader_height = self._effective_reader_height()
            # If MARK READER TOP was used, cap the descent at that reader top.
            robot.cfg_reader_floor_above_table = self._calib_reader_floor_above_table
            if robot.cfg_reader_height is None:
                self._q.put((
                    "log",
                    "WARNING: Reader height not set — calibrate the reader with "
                    "CALIBRATE READER → MARK READER TOP first.",
                ))
            robot._on_progress = lambda c, t, p: self._q.put(("progress", (c, t, p)))
            robot._on_result = lambda row: self._q.put(("result", row))
            self.robot = robot
            self._last_robot = robot
            # Live joint stream for the 3D view / ROS2 (read-only, cached reads).
            robot.start_telemetry(lambda j: self._q.put(("telemetry", j)))
            if self._has_read_height() and self._has_tapgo():
                robot.run_combined()
            elif self._has_tapgo():
                robot.run_tap_and_go()
            else:
                robot.run()
            if not verify:
                self._auto_export(robot)
        except Exception as e:
            self._q.put(("log", "ERROR: {}".format(e)))
        finally:
            try:
                robot.stop_telemetry()
            except Exception:
                pass
            sys.stdout = old_stdout
            self._q.put(("done", verify))

    def _on_run_finished(self, verify):
        if hasattr(self, "start_btn"):
            self.start_btn.config(state=tk.NORMAL)
        if hasattr(self, "stop_btn"):
            self.stop_btn.config(state=tk.DISABLED)
        if hasattr(self, "pbar"):
            self.pbar['value'] = 100
        self.root.title("rf IDEAS — Credential Read Height Test")
        if self._live_csv_path:
            self.set_status("Run finished — saved to {}".format(os.path.basename(self._live_csv_path)))
        else:
            self.set_status("Run finished")
        self.robot = None

    def _on_stop(self):
        if self.robot:
            self._log(">> ABORT pressed.")
            try:
                self.robot.request_abort()
            except Exception as e:
                self._log("Abort error: {}".format(e))

    # ---- CSV export ----
    def _results_dir(self):
        config.ensure_paths_exist()
        return config.PATHS["results"]

    def _reader_model_label(self):
        """Best available reader label for filenames/metadata.

        Prefers the detected part number; falls back to the dropdown selection
        (or the OTHER text) so a skipped reader check still names files sensibly.
        """
        model = self.reader_info.get("Part-Number")
        if model:
            return model
        if self.reader_type.get() == "OTHER":
            return self.reader_other.get().strip()[:40] or "reader"
        return self.reader_type.get() or "reader"

    def _robot_test_kinds(self, robot):
        """Ordered list of test kinds for this run (falls back to the legacy
        single-string field for older callers)."""
        kinds = list(getattr(robot, "cfg_tests", []) or [])
        if not kinds:
            kinds = [getattr(robot, "cfg_test", "read_height")]
        return kinds

    def _results_path_for(self, robot, kind):
        rdir = self._results_dir()
        os.makedirs(rdir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        suffix = "tap_and_go" if kind == "tap_and_go" else "read_heights"
        return os.path.join(rdir, "{}_{}_{}.csv".format(ts, self._reader_model_label(), suffix))

    def _tapgo_metadata_rows(self, robot):
        """Header/metadata block for a Tap-and-Go results file."""
        generated = datetime.now().strftime("%b-%d-%Y %H:%M:%S")
        model = self._reader_model_label()
        rtype = (self.reader_other.get().strip()[:40]
                 if self.reader_type.get() == "OTHER" else self.reader_type.get())
        fw = (self.reader_info.get("Firmware Filename")
              or self.reader_info.get("USB-Firmware", ""))
        return [
            ["rf IDEAS — Tap-and-Go Read-Time Test"],
            ["Reader Type", rtype, "Reader Model", model],
            ["Firmware", fw],
            ["Descent speed", "{:g} mm/s".format(TAPGO_DESCENT_SPEED_MM_S),
             "Read timeout", "{:g} s".format(TAPGO_READ_TIMEOUT_S)],
            ["Taps per card", getattr(robot, "cfg_scans", "")],
            ["Comment", self.comment_var.get()],
            ["Generated", generated],
            [],
            list(TAPGO_CSV_HEADER),
        ]

    @staticmethod
    def _tapgo_data_cells(row):
        """One tap-and-go row → flat cell list matching TAPGO_CSV_HEADER."""
        return [
            row.get("run", 1), row.get("card_num", ""), row.get("side", ""),
            row.get("angle", ""), row.get("card_title", ""), row.get("card_code", ""),
            row.get("taps", ""), row.get("reads", ""), row.get("misses", ""),
            row.get("avg_ms", ""), row.get("min_ms", ""), row.get("max_ms", ""),
            row.get("times_ms", ""), row.get("error_skip", ""),
        ]

    def _metadata_rows(self, robot):
        """The header/metadata block written once at the top of a results file."""
        generated = datetime.now().strftime("%b-%d-%Y %H:%M:%S")
        model = self._reader_model_label()
        rtype = (
            self.reader_other.get().strip()[:40]
            if self.reader_type.get() == "OTHER"
            else self.reader_type.get()
        )
        fw = (
            self.reader_info.get("Firmware Filename")
            or self.reader_info.get("USB-Firmware", "")
        )
        angles_disp = ", ".join("{}°".format(a) for a in robot.cfg_angles)
        return [
            ["rf IDEAS — Credential Read Height Test"],
            ["Reader Type", rtype, "Reader Model", model],
            ["Firmware", fw],
            ["Test speed", robot.cfg_preset, "Final tap",
             "{:g}mm @ {:g} mm/s".format(robot.cfg_final_step_mm, robot.cfg_descent_speed)],
            ["Read angles", angles_disp],
            ["Comment", self.comment_var.get()],
            ["Generated", generated],
            [],
            list(CSV_DATA_HEADER),
        ]

    @staticmethod
    def _data_cells(row):
        """One results row → the flat cell list matching CSV_DATA_HEADER."""
        return [
            row.get("run", 1),
            row.get("card_num", ""),
            row.get("side", ""),
            row.get("card_title", ""),
            row.get("card_code", ""),
            row.get("a0_avg", ""), row.get("a90_avg", ""),
            row.get("a180_avg", ""), row.get("a270_avg", ""),
            row.get("a0_min", ""), row.get("a0_max", ""),
            row.get("a90_min", ""), row.get("a90_max", ""),
            row.get("a180_min", ""), row.get("a180_max", ""),
            row.get("a270_min", ""), row.get("a270_max", ""),
            row.get("a0_scans", ""), row.get("a90_scans", ""),
            row.get("a180_scans", ""), row.get("a270_scans", ""),
            row.get("card_max", ""),
            row.get("error_skip", ""),
        ]

    def _open_live_csv(self, robot):
        """Create an autosave file per selected test and write its metadata +
        header. Populates self._live_csv_paths {kind: path}."""
        self._live_csv_paths = {}
        for kind in self._robot_test_kinds(robot):
            path = self._results_path_for(robot, kind)
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if kind == "tap_and_go":
                    for r in self._tapgo_metadata_rows(robot):
                        w.writerow(r)
                else:
                    for r in self._metadata_rows(robot):
                        w.writerow(_csv_row(r))
            self._live_csv_paths[kind] = path
        # alias used by the status bar / simple messages
        self._live_csv_path = next(iter(self._live_csv_paths.values()), None)
        return self._live_csv_path

    def _append_live_row(self, row):
        """Append one row to the autosave file for its test kind and flush.

        Opening/closing per row is deliberate — it guarantees each card is on
        disk the instant it finishes, so a crash mid-run never loses prior
        cards.
        """
        kind = "tap_and_go" if row.get("kind") == "tap_and_go" else "read_height"
        path = self._live_csv_paths.get(kind)
        if not path:
            return
        try:
            with open(path, "a", newline="", encoding="utf-8") as f:
                if kind == "tap_and_go":
                    csv.writer(f).writerow(self._tapgo_data_cells(row))
                else:
                    csv.writer(f).writerow(_csv_row(self._data_cells(row)))
        except Exception as e:
            self._log("Autosave write failed: {}".format(e))

    def _sync_all_cards_from_results(self, robot):
        """Push result averages into AllCards.csv (values are mm above reader top).

        AllCards.csv currently stores two baseline columns (Inline / Orthogonal).
        We map 0° -> Inline and 90° -> Orthogonal so the existing baseline
        loader keeps working. 180°/270° are recorded in the results CSV.
        """
        updates = []
        for row in robot.results:
            if row.get("kind") == "tap_and_go":
                continue   # timing rows carry no height baseline
            if not row.get("card_code"):
                continue
            skip = (row.get("error_skip") or "").strip().upper()
            if skip == "BARCODE FAIL":
                continue
            inline = row.get("a0_avg")     # 0°  -> Inline baseline
            orth = row.get("a90_avg")      # 90° -> Orthogonal baseline
            if is_bad_reference_height(inline):
                inline = None
            if is_bad_reference_height(orth):
                orth = None
            if inline in ("", None) and orth in ("", None):
                continue
            updates.append({
                "card_code": row.get("card_code"),
                "inline_avg": inline,
                "orthogonal_avg": orth,
            })
        n = update_all_cards_averages(updates)
        scrub_poisoned_card_baselines()
        return n

    def _auto_export(self, robot):
        """End-of-run: rows are already on disk via autosave — just log the
        path(s) and (when Read Height ran) push baselines into AllCards.csv."""
        for kind, path in self._live_csv_paths.items():
            self._q.put(("log", ">> {} results saved -> {}".format(
                "Tap-and-Go" if kind == "tap_and_go" else "Read-height", path)))
        if "read_height" not in self._robot_test_kinds(robot):
            return   # timing-only run — no AllCards baseline sync
        if robot and robot.results:
            n = self._sync_all_cards_from_results(robot)
            if n:
                self._q.put((
                    "log",
                    ">> AllCards.csv updated — {} card(s), 0°/90° baselines (mm above reader top)".format(n),
                ))

    def _on_export(self):
        robot = self.robot or self._last_robot
        if robot is None or not getattr(robot, "results", None):
            messagebox.showinfo("Export", "No results yet — run a test first.")
            return
        # Autosave already wrote every row live. If for some reason there are no
        # live files (e.g. results loaded another way), write them now.
        if not self._live_csv_paths or not all(
                os.path.exists(p) for p in self._live_csv_paths.values()):
            self._open_live_csv(robot)
            for row in robot.results:
                self._append_live_row(row)
        saved = "\n".join(self._live_csv_paths.values())
        msg = "Saved:\n{}".format(saved)
        if "read_height" in self._robot_test_kinds(robot):
            n = self._sync_all_cards_from_results(robot)
            if n:
                msg += "\n\nAllCards.csv updated ({} card(s), mm above reader top)".format(n)
        messagebox.showinfo("Export", msg)

    # =====================================================================
    # READER CALIBRATION (manual arrow-key jog)
    # =====================================================================
    def show_calibrator(self):
        """Manual jog screen: keep the tool facing down and drive the arm over
        the reader with the arrow keys / on-screen pad, then capture the reader's
        staging pose and height."""
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Test running", "Stop the test before calibrating.")
            return
        # Stop any barcode listener so arrow keys aren't swallowed.
        try:
            if self._scanner:
                self._scanner.stop()
                self._scanner = None
        except Exception:
            pass

        self._clear_container()
        wrap = tk.Frame(self.container, bg=BRAND['bg'])
        wrap.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        # ---- left: live readout + capture ----
        left = tk.Frame(wrap, bg=BRAND['card'], width=372, highlightthickness=1,
                        highlightbackground=BRAND['divider'])
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        lp = tk.Frame(left, bg=BRAND['card'])
        lp.pack(fill=tk.BOTH, expand=True, padx=22, pady=18)

        section_label(lp, "Reader calibration").pack(anchor=tk.W)
        tk.Label(lp, text="Tool stays facing down. Jog over the reader, lower until\n"
                          "the card just touches the top, then MARK READER TOP —\n"
                          "captures the approach angle (position) AND the height/floor.",
                 font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'],
                 justify="left").pack(anchor=tk.W, pady=(2, 12))

        self.calib_status = tk.Label(lp, text="Connecting to arm…", font=FONT_BODY,
                                     fg=BRAND['amber'], bg=BRAND['card'], anchor="w")
        self.calib_status.pack(fill=tk.X, pady=(0, 10))

        # live readout grid
        read = tk.Frame(lp, bg=BRAND['light'])
        read.pack(fill=tk.X, pady=(0, 12), ipady=6, ipadx=6)
        self.calib_readout = {}
        for i, key in enumerate(["Pos X/Y/Z (mm)", "Joints (°)",
                                 "Height above table (mm)", "Est. reader height (mm)"]):
            tk.Label(read, text=key, font=FONT_SMALL, fg=BRAND['subtle'],
                     bg=BRAND['light'], anchor="w").grid(row=i, column=0, sticky="w", padx=6, pady=1)
            val = tk.Label(read, text="—", font=FONT_MONO, fg=BRAND['text'],
                           bg=BRAND['light'], anchor="w")
            val.grid(row=i, column=1, sticky="w", padx=6, pady=1)
            self.calib_readout[key] = val
        read.grid_columnconfigure(1, weight=1)

        # step size
        step_row = tk.Frame(lp, bg=BRAND['card'])
        step_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(step_row, text="Step", font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['card']).pack(side=tk.LEFT, padx=(0, 8))
        for name in CALIB_STEP_PRESETS:
            tk.Radiobutton(
                step_row, text="{} ({:g})".format(name, CALIB_STEP_PRESETS[name]),
                variable=self.calib_step_var, value=name, font=FONT_SMALL,
                fg=BRAND['text'], bg=BRAND['card'], activebackground=BRAND['card'],
                selectcolor=BRAND['white'], highlightthickness=0, bd=0,
            ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Frame(lp, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=8)

        # capture (angle + height, one button)
        self.calib_height_lbl = tk.Label(lp, text="Reader: (not captured)",
                                         font=FONT_SMALL, fg=BRAND['text'], bg=BRAND['card'],
                                         anchor="w", justify="left", wraplength=320)
        self.calib_height_lbl.pack(fill=tk.X, pady=(0, 4))
        flat_button(lp, "MARK READER TOP  (angle + height)", self._calib_mark_reader,
                    fg=BRAND['white'], bg=BRAND['red'], hover=BRAND['red_hover'],
                    font=FONT_SMALL, pady=8).pack(fill=tk.X, pady=(0, 8))

        tk.Frame(lp, bg=BRAND['card']).pack(expand=True, fill=tk.BOTH)
        flat_button(lp, "← BACK (park & disconnect)", self._calib_exit,
                    fg=BRAND['text'], bg=BRAND['light'], hover=BRAND['divider'],
                    font=FONT_SMALL, pady=7).pack(fill=tk.X)

        # ---- right: jog pad ----
        right = tk.Frame(wrap, bg=BRAND['card'], highlightthickness=1,
                         highlightbackground=BRAND['divider'])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        rp = tk.Frame(right, bg=BRAND['card'])
        rp.pack(expand=True)

        section_label(rp, "Jog  (arrow keys · W / S for height)").pack(pady=(20, 4))
        tk.Label(rp, text="Buttons are labelled by robot axis — use whichever moves\n"
                          "toward the reader. Tool orientation stays fixed (facing down).\n"
                          "Jog down (S) until the card just touches the reader top,\n"
                          "then MARK READER TOP.",
                 font=FONT_SMALL, fg=BRAND['subtle'], bg=BRAND['card'], justify="center").pack(pady=(0, 16))

        pad4 = tk.Frame(rp, bg=BRAND['card'])
        pad4.pack()

        def jbtn(parent, text, dx=0.0, dy=0.0, dz=0.0, r=0, c=0):
            b = flat_button(parent, text, lambda: self._calib_jog(dx, dy, dz),
                            fg=BRAND['white'], bg=BRAND['purple'], hover="#3A3B6E",
                            font=FONT_BTN, pady=12)
            b.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            return b

        # XY pad (labelled by axis)
        jbtn(pad4, "▲  +X", dx=1, r=0, c=1)
        jbtn(pad4, "◀  −Y", dy=-1, r=1, c=0)
        jbtn(pad4, "▼  −X", dx=-1, r=1, c=1)
        jbtn(pad4, "▶  +Y", dy=1, r=1, c=2)
        for i in range(3):
            pad4.grid_columnconfigure(i, minsize=90)

        zrow = tk.Frame(rp, bg=BRAND['card'])
        zrow.pack(pady=(18, 6))
        jbtn(zrow, "W  ↑ up", dz=1, r=0, c=0)
        jbtn(zrow, "S  ↓ down", dz=-1, r=0, c=1)

        # key bindings (Cartesian arrows + W/S height + step select)
        self.root.bind("<Up>", lambda e: self._calib_jog(dx=1))
        self.root.bind("<Down>", lambda e: self._calib_jog(dx=-1))
        self.root.bind("<Left>", lambda e: self._calib_jog(dy=-1))
        self.root.bind("<Right>", lambda e: self._calib_jog(dy=1))
        self.root.bind("<KeyPress-w>", lambda e: self._calib_jog(dz=1))
        self.root.bind("<KeyPress-s>", lambda e: self._calib_jog(dz=-1))
        self.root.bind("<KeyPress-1>", lambda e: self.calib_step_var.set("Coarse"))
        self.root.bind("<KeyPress-2>", lambda e: self.calib_step_var.set("Medium"))
        self.root.bind("<KeyPress-3>", lambda e: self.calib_step_var.set("Fine"))
        self.root.focus_set()

        self.set_status("Reader calibration — connecting to arm…")
        # connect + move to the tool-down start pose in a worker
        threading.Thread(target=self._calib_connect, daemon=True).start()

    def _calib_unbind_keys(self):
        for seq in ("<Up>", "<Down>", "<Left>", "<Right>",
                    "<KeyPress-w>", "<KeyPress-s>",
                    "<KeyPress-1>", "<KeyPress-2>", "<KeyPress-3>"):
            try:
                self.root.unbind(seq)
            except Exception:
                pass

    def _calib_connect(self):
        try:
            arm = XArmAPI(self.ip_var.get().strip(), baud_checkset=False)
            time.sleep(0.5)
            if not arm.connected:
                self.root.after(0, lambda: self._calib_set_status("Arm not connected — check IP/cable.", BRAND['red']))
                return
            arm.clean_warn(); arm.clean_error()
            arm.motion_enable(True); arm.set_mode(0); arm.set_state(0)
            time.sleep(0.3)
            if arm.error_code != 0:
                self.root.after(0, lambda: self._calib_set_status(
                    "Arm error {} — clear it in Studio.".format(arm.error_code), BRAND['red']))
                return
            # Move to the tool-down 0° staging start pose.
            start = list(READER_STAGING_0_ANGLE)
            arm.set_servo_angle(angle=start, speed=config.MOTION_JOINT_SPEED,
                                mvacc=config.MOTION_JOINT_ACC, wait=True, radius=0.0)
            self._calib_arm = arm
            self._calib_active = True
            self._calib_q = queue.Queue()
            self._calib_worker = threading.Thread(target=self._calib_jog_worker, daemon=True)
            self._calib_worker.start()
            self.root.after(0, lambda: self._calib_set_status(
                "Ready — jog the arm over the reader.", BRAND['green']))
            self.root.after(200, self._calib_poll)
        except Exception as e:
            self.root.after(0, lambda e=e: self._calib_set_status("Connect error: {}".format(e), BRAND['red']))

    def _calib_set_status(self, text, color=None):
        if hasattr(self, "calib_status") and self.calib_status.winfo_exists():
            self.calib_status.config(text=text, fg=color or BRAND['text'])

    def _calib_jog(self, dx=0.0, dy=0.0, dz=0.0):
        """Enqueue one jog step scaled by the current step size."""
        if not self._calib_active or self._calib_q is None or self._calib_capturing:
            return
        # Drop input if the worker is backed up, so held keys don't run away.
        if self._calib_q.qsize() >= 2:
            return
        step = CALIB_STEP_PRESETS.get(self.calib_step_var.get(), 1.0)
        self._calib_q.put((dx * step, dy * step, dz * step))

    def _calib_jog_worker(self):
        while self._calib_active:
            try:
                cmd = self._calib_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if cmd is None:
                break
            dx, dy, dz = cmd
            arm = self._calib_arm
            if arm is None or self._calib_capturing:
                continue
            try:
                # Table floor guard for downward moves.
                if dz < 0:
                    pos = arm.get_position()
                    if pos[0] == 0:
                        above = pos[1][2] - TABLE_Z
                        if above + dz < CALIB_MIN_ABOVE_TABLE_MM:
                            dz = min(0.0, CALIB_MIN_ABOVE_TABLE_MM - above)
                if dx or dy or dz:
                    arm.set_position(x=dx, y=dy, z=dz, roll=0, pitch=0, yaw=0,
                                     relative=True, speed=CALIB_JOG_TCP_SPEED,
                                     mvacc=CALIB_JOG_TCP_ACC, wait=True)
                if arm.error_code != 0:
                    code = arm.error_code
                    try:
                        arm.clean_error(); arm.clean_warn(); arm.set_state(0)
                    except Exception:
                        pass
                    self.root.after(0, lambda c=code: self._calib_set_status(
                        "Jog hit limit (err {}) — cleared. Try another direction.".format(c), BRAND['amber']))
            except Exception as e:
                self.root.after(0, lambda err=e: self._calib_set_status("Jog error: {}".format(err), BRAND['amber']))

    def _calib_poll(self):
        if not self._calib_active:
            return
        arm = self._calib_arm
        if arm is not None:
            try:
                pos = arm.get_position()
                ang = arm.get_servo_angle()
                if pos[0] == 0:
                    x, y, z = pos[1][0], pos[1][1], pos[1][2]
                    above = z - TABLE_Z
                    reader_h = config.card_face_above_table_from_tcp(above)
                    self.calib_readout["Pos X/Y/Z (mm)"].config(
                        text="{:.1f}  {:.1f}  {:.1f}".format(x, y, z))
                    self.calib_readout["Height above table (mm)"].config(text="{:.1f}".format(above))
                    self.calib_readout["Est. reader height (mm)"].config(text="{:.1f}".format(reader_h))
                if ang[0] == 0:
                    self.calib_readout["Joints (°)"].config(
                        text="[{}]".format(", ".join("{:.1f}".format(a) for a in ang[1])))
                    self._feed_telemetry(list(ang[1])[:6])
            except Exception:
                pass
        self.root.after(200, self._calib_poll)

    def _calib_mark_reader(self):
        """One button: record the reader top (height + descent floor) AND the
        approach staging pose (position/orientation over the reader).

        Records the current point as the reader top, then lifts straight up to
        a staging height and captures the joint pose there as the new 0° staging
        angle (90/180/270 derive from it by wrist rotation). Runs off-thread so
        the GUI stays responsive; jogs are blocked while it runs."""
        arm = self._calib_arm
        if arm is None or self._calib_capturing:
            return
        self._calib_capturing = True
        # drop any queued jogs so nothing moves the arm mid-capture
        try:
            while True:
                self._calib_q.get_nowait()
        except Exception:
            pass
        self._calib_set_status("Marking reader — capturing height, then lifting to staging…",
                               BRAND['amber'])
        threading.Thread(target=self._calib_do_mark, daemon=True).start()

    def _calib_do_mark(self):
        arm = self._calib_arm
        try:
            time.sleep(0.15)  # let any in-flight jog settle
            pos = arm.get_position()
            if pos[0] != 0:
                self.root.after(0, lambda: self._calib_set_status("Could not read position.", BRAND['red']))
                return
            above = pos[1][2] - TABLE_Z
            reader_h = round(config.card_face_above_table_from_tcp(above), 1)
            floor = round(above, 2)
            # Lift straight up to a staging height (hold orientation), then read
            # the joint pose there = the approach staging pose for this reader.
            arm.set_position(z=CALIB_STAGING_LIFT_MM, roll=0, pitch=0, yaw=0,
                             relative=True, speed=CALIB_JOG_TCP_SPEED,
                             mvacc=CALIB_JOG_TCP_ACC, wait=True)
            ret = arm.get_servo_angle()
            pose = [round(a, 1) for a in ret[1]] if ret[0] == 0 else None
            self.root.after(0, lambda: self._calib_finish_mark(pose, reader_h, floor))
        except Exception as e:
            self.root.after(0, lambda err=e: self._calib_set_status("Mark failed: {}".format(err), BRAND['amber']))
        finally:
            self._calib_capturing = False

    def _calib_finish_mark(self, pose, reader_h, floor):
        self._calib_reader_height = reader_h
        self._calib_reader_floor_above_table = floor
        if pose is not None:
            self._calib_staging_pose = pose
        self.calib_height_lbl.config(
            text="Captured — height {:.1f} mm, floor set here, approach angle "
                 "updated.\nStaging pose: {}".format(reader_h, pose),
            fg=BRAND['green'])
        self._calib_set_status(
            "Reader captured: position + height (active this session).", BRAND['green'])

    def _calib_exit(self):
        """Stop jogging, lift to a safe height, disconnect, return to the test panel."""
        self._calib_active = False
        self._calib_unbind_keys()
        arm = self._calib_arm

        def teardown():
            if arm is not None:
                try:
                    # lift clear, then park home
                    arm.set_position(z=40, roll=0, pitch=0, yaw=0, relative=True,
                                     speed=CALIB_JOG_TCP_SPEED, mvacc=CALIB_JOG_TCP_ACC, wait=True)
                except Exception:
                    pass
                try:
                    arm.set_servo_angle(angle=config.HOME_ANGLE,
                                        speed=config.MOTION_PARK_JOINT_SPEED,
                                        mvacc=config.MOTION_PARK_JOINT_ACC, wait=True, radius=0.0)
                except Exception:
                    pass
                try:
                    arm.disconnect()
                except Exception:
                    pass
            self._calib_arm = None
            self.root.after(0, self.show_main)

        threading.Thread(target=teardown, daemon=True).start()
        self._calib_set_status("Parking arm…", BRAND['amber'])

    # =====================================================================
    # ROS2 TELEMETRY  +  LIVE 3D VIEW feed (both read-only, optional)
    # =====================================================================
    def _viewer_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewer")

    def _open_mesh_viewer(self):
        """Start the local three.js mesh viewer and open it in the browser."""
        if robot_viewer is None:
            messagebox.showinfo("Mesh viewer unavailable",
                                "robot_viewer.py is missing — place it beside gui.py.")
            return
        vdir = self._viewer_dir()
        if self._viewer is None:
            self._viewer = robot_viewer.RobotViewerServer(vdir)
        if not self._viewer.files_present():
            messagebox.showwarning(
                "Viewer files missing",
                "Put the viewer assets in this folder:\n\n{}\n\n"
                "Needed:\n"
                "  lite6_viewer.html\n"
                "  lite6.urdf\n"
                "  meshes\\visual\\link_base.stl, link1.stl … link6.stl".format(vdir))
            return
        try:
            url = self._viewer.start()
            if self._last_joints:
                self._viewer.set_joints(self._last_joints)
            self._viewer.open_in_browser()
            self.set_status("3D mesh view opened in browser: {}".format(url))
        except Exception as e:
            messagebox.showerror("Mesh viewer error", str(e))

    def _on_telem_toggle(self):
        if self.telem_var.get():
            if self._telem_udp is None:
                self._telem_udp = _TelemetryUDP()
            self.set_status("Streaming telemetry to ROS2 bridge on UDP :{}.".format(TELEMETRY_UDP_PORT))
        else:
            if self._telem_udp is not None:
                self._telem_udp.close()
                self._telem_udp = None
            self.set_status("ROS2 telemetry stopped.")

    def _feed_telemetry(self, joints):
        """Route a fresh joint-angle sample to the 3D view and/or ROS2 bridge."""
        if not joints:
            return
        self._last_joints = joints
        if self._arm3d is not None and self._arm3d.alive():
            self._arm3d.update(joints)
        if self._viewer is not None:
            self._viewer.set_joints(joints)
        if self._telem_udp is not None:
            self._telem_udp.send_joints(joints)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Test running", "A test is running. Abort and exit?"):
                return
            if self.robot:
                try:
                    self.robot.request_abort()
                except Exception:
                    pass
        # tear down calibration connection if active
        self._calib_active = False
        if self._calib_arm is not None:
            try:
                self._calib_arm.disconnect()
            except Exception:
                pass
            self._calib_arm = None
        # close the 3D view and telemetry stream
        if self._arm3d is not None:
            try:
                self._arm3d.close()
            except Exception:
                pass
            self._arm3d = None
        if self._telem_udp is not None:
            try:
                self._telem_udp.close()
            except Exception:
                pass
            self._telem_udp = None
        if self._viewer is not None:
            try:
                self._viewer.stop()
            except Exception:
                pass
            self._viewer = None
        try:
            if self._scanner:
                self._scanner.stop()
        except Exception:
            pass
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        self.root.destroy()


class _StdoutToQueue:
    """Redirects print() to the GUI log queue, line-buffered."""
    def __init__(self, q):
        self._q = q
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._q.put(("log", line))

    def flush(self):
        if self._buf.strip():
            self._q.put(("log", self._buf))
        self._buf = ""


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
