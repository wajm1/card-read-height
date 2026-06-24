# gui.py
# rf IDEAS — Automated Credential Read Height Testing (GUI)
#
# Wraps the working robot routine in robot/move.py WITHOUT modifying it:
#   - imports RobotMain unchanged
#   - subclasses it (GuiRobot) only to (a) add a wiggle in front of the
#     barcode scanner and (b) make card-count / scans / descent-speed
#     configurable and record read heights. All motion primitives
#     (smart_pick, _descend_until_read, poses) are the inherited ones.
#
# Flow: Device checklist (gate) -> Test panel -> Run -> CSV export.

import os
import sys
import csv
import queue
import threading
import time
from datetime import datetime

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ── make project root importable ──────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AUTOMATION_ROOT = os.path.dirname(SCRIPT_DIR)
if AUTOMATION_ROOT not in sys.path:
    sys.path.insert(0, AUTOMATION_ROOT)

from xarm.wrapper import XArmAPI
from robot.move import RobotMain                 # unchanged, working logic
from barcode.scanner import BarcodeListener, lookup_card
from reader.cli import configure_reader_for_card, get_reader_info
try:
    from reader.cli import check_reader
except Exception:
    check_reader = None

try:
    import config
    DEFAULT_IP = getattr(config, "ROBOT_IP", "192.168.1.177")
except Exception:
    config = None
    DEFAULT_IP = "192.168.1.177"

# ── robot constants (mirrors robot/move.py — values only, no logic) ────────
PICK_ANGLE         = [-43.6, 50.0, 71.5, 180.0, -19.8, -134.4]
BARCODE_SCAN_ANGLE = [-43.7, 48.5, 71.5, 142.4, -74.1, -106.1]
PLACE_A_ANGLE      = [4.2, 27.4, 39.5, 186.7, -10.4, -93.4]
PLACE_B_ANGLE      = [4.2, 27.4, 39.5, 186.7, -10.4, -183.4]
RELEASE_ANGLE      = [44.4, 58.7, 76.5, 168.6, -14.4, -112.8]
HOME_ANGLE         = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
TABLE_Z            = 61.0     # mm (matches smart_pick in move.py)
MAX_PRESENT_DROP   = 70.0     # mm hard cap for reader descent

# wiggle tuning
WIGGLE_DEG      = 4.0       # degrees J6 (wrist) rotation left/right
WIGGLE_LIFT_DEG = 3.0       # degrees J2 (shoulder) nudge for the up/down "wave"
                            #   joint-space — gives ~ a few mm of vertical motion.
                            #   Raise for a bigger wave; keep it small.
WIGGLE_SPEED   = 45
WIGGLE_ACC     = 350
WIGGLE_PAUSE_S = 0.25

# ── rf IDEAS brand palette (kept from the existing approved GUI) ───────────
BRAND = {
    'red': '#ED2024', 'red_hover': '#C9191D', 'text': '#58595B',
    'purple': '#494A8B', 'border': '#A7A9AC', 'divider': '#DCDCDE',
    'bg': '#F4F4F6', 'card': '#FFFFFF', 'light': '#EEEEEE',
    'dark': '#161618', 'log_bg': '#1C1C1F', 'green': '#2E9E5B',
    'amber': '#E8A13D', 'white': '#FFFFFF',
}
FONT_H1   = ("Verdana", 14, "bold")
FONT_H2   = ("Verdana", 9, "bold")
FONT_BODY = ("Verdana", 10)
FONT_SMALL= ("Verdana", 8)
FONT_BTN  = ("Verdana", 10, "bold")
FONT_MONO = ("Consolas", 9)

READER_TYPES = ["Mini Desktop", "HIP2", "NANO", "MICRO", "PICO", "OTHER"]


# ===========================================================================
# ROBOT: subclass of the unchanged RobotMain
# ===========================================================================
class GuiRobot(RobotMain):
    """Adds barcode-scanner wiggle + configurable run + read-height capture.
    All actual motion uses the inherited (working) methods."""

    def init_gui(self):
        self.cfg_cycles = 1
        self.cfg_scans = 1
        self.cfg_descent_speed = 20.0     # mm/s, live-updatable from slider
        self.cfg_descent_step = 2.0       # mm per step
        self.cfg_retries = 3
        self._on_progress = None
        self._on_result = None
        self._last_barcode = None
        self.results = []

    # ---- wiggle override (only behavioural addition) ----
    def _scan_barcode_and_config(self, timeout=20):
        """Wave (wrist turn + up/down) in front of the scanner while waiting
        for a barcode, then configure the reader for the matched card."""
        ret = self._arm.get_servo_angle()
        base = list(ret[1]) if ret[0] == 0 else list(BARCODE_SCAN_ANGLE)

        result = {}
        event = threading.Event()

        def on_barcode(barcode):
            if result.get('card'):
                return
            card = lookup_card(barcode)
            if card:
                result['card'] = card
                result['barcode'] = barcode
                event.set()
                print('>> Barcode {} -> {}'.format(barcode, card.get('name', '?')))
            else:
                print('>> Unknown barcode: {}'.format(barcode))

        listener = BarcodeListener(on_barcode)
        listener.start()
        print('>> Waving (turn + up/down) in front of barcode scanner...')

        deadline = time.monotonic() + timeout
        # (J6 wrist turn, J2 lift) — turns AND waves up/down. Both are
        # joint-space nudges relative to the scan pose, so there is NO
        # Cartesian Z move and therefore no J5 speed/IK problem.
        moves = [
            ( WIGGLE_DEG,  WIGGLE_LIFT_DEG),   # turn one way, lift up
            (-WIGGLE_DEG, -WIGGLE_LIFT_DEG),   # turn other way, dip down
            ( 0.0,         0.0),               # back to center
        ]
        try:
            while self.is_alive and not event.is_set() and time.monotonic() < deadline:
                for turn, lift in moves:
                    if event.is_set() or not self.is_alive:
                        break
                    ang = list(base)
                    ang[1] += lift    # J2 (shoulder) → up/down wave
                    ang[5] += turn    # J6 (wrist)    → turn
                    self._arm.set_servo_angle(
                        angle=ang, speed=WIGGLE_SPEED, mvacc=WIGGLE_ACC,
                        wait=True, radius=0.0)
                    pause_end = time.monotonic() + WIGGLE_PAUSE_S
                    while time.monotonic() < pause_end and not event.is_set():
                        time.sleep(0.02)
        finally:
            listener.stop()
            # return to the scan pose so the next move starts from a known spot
            try:
                self._arm.set_servo_angle(
                    angle=base, speed=WIGGLE_SPEED, mvacc=WIGGLE_ACC,
                    wait=True, radius=0.0)
            except Exception:
                pass

        card = result.get('card')
        self._last_barcode = result.get('barcode')
        if not card:
            print('>> No valid barcode read.')
            return None

        print('>> Configuring reader for {}...'.format(card.get('name', '?')))
        try:
            ok = configure_reader_for_card(card, log_fn=print)
        except TypeError:
            ok = configure_reader_for_card(card)
        print('>> Reader configured.' if ok else '>> Reader configuration FAILED.')
        self._current_card = card
        return card

    # ---- helpers ----
    def _height_above_table(self):
        ret = self._arm.get_position()
        if ret[0] != 0:
            return None
        return ret[1][2] - TABLE_Z

    def _present_once(self):
        """One slow descent onto the reader; stop on read. Returns height or None."""
        dropped = self._descend_until_read(
            max_drop=MAX_PRESENT_DROP,
            step=self.cfg_descent_step,
            speed=self.cfg_descent_speed,   # ← slider value, live
        )
        height = self._height_above_table()
        read_ok = dropped < MAX_PRESENT_DROP - 0.001   # stopped early => read
        # raise back up by however far we went down
        self._arm.set_position(
            z=dropped, radius=0, speed=self._tcp_speed, mvacc=self._tcp_acc,
            relative=True, wait=True)
        return height if (read_ok and height is not None) else None

    def _measure_side(self, side, pose, scans):
        heights = []
        for s in range(scans):
            if not self.is_alive:
                break
            self._progress(self._cur_cycle, self.cfg_cycles,
                           "Side {} — scan {}/{}".format(side, s + 1, scans))
            self._angle_speed = 70
            self._angle_acc = 600
            code = self._arm.set_servo_angle(
                angle=pose, speed=self._angle_speed, mvacc=self._angle_acc,
                wait=True, radius=0.0)
            if not self._check_code(code, 'reader side {}'.format(side)):
                break
            h = self._present_once()
            if h is not None:
                heights.append(h)
                print('>>   Side {} scan {}: {:.2f} mm'.format(side, s + 1, h))
            else:
                print('>>   Side {} scan {}: no read'.format(side, s + 1))
        return heights

    def _progress(self, cycle, total, phase):
        if self._on_progress:
            self._on_progress(cycle, total, phase)

    # ---- abort (kill switch) ----
    def request_abort(self):
        self._stop_event.set()
        self.alive = False
        try:
            self._arm.emergency_stop()
        except Exception:
            pass

    # ---- re-expressed run(): same motions, now configurable + recorded ----
    def run(self):
        try:
            print('>> Homing (fast)...')
            code = self._arm.set_servo_angle(
                angle=HOME_ANGLE, speed=180, mvacc=1100, wait=True, radius=0.0)
            if not self._check_code(code, 'home'):
                return
            print('>> Home reached. Starting {} card(s).'.format(self.cfg_cycles))

            for i in range(self.cfg_cycles):
                if not self.is_alive:
                    break
                self._cur_cycle = i + 1
                self._progress(i + 1, self.cfg_cycles, "Picking card")
                print('>> ───────────────  Card {} of {}  ───────────────'.format(
                    i + 1, self.cfg_cycles))
                t1 = time.monotonic()
                error_flag = ""

                # ── Pick (with retries) ──
                pick_z = None
                for attempt in range(self.cfg_retries):
                    if not self.is_alive:
                        break
                    self._angle_speed = 180
                    self._angle_acc = 1100
                    code = self._arm.set_servo_angle(
                        angle=PICK_ANGLE, speed=self._angle_speed,
                        mvacc=self._angle_acc, wait=True, radius=0.0)
                    if not self._check_code(code, 'move to pick'):
                        break
                    self._arm.set_suction_cup(True, wait=False, delay_sec=0, hardware_version=1)
                    pick_z = self.smart_pick()
                    if pick_z is not None:
                        break
                    print('>> Pick attempt {} failed.'.format(attempt + 1))
                    self._arm.set_suction_cup(False, wait=False, delay_sec=0, hardware_version=1)

                if pick_z is None:
                    error_flag = "PICK FAIL"
                    print('>> Skipping card {} (pick failed).'.format(i + 1))
                    self._arm.set_servo_angle(angle=HOME_ANGLE, speed=120, mvacc=1000,
                                              wait=True, radius=0.0)
                    self._emit_result(i + 1, None, None, error_flag)
                    continue

                time.sleep(0.3)

                # ── Lift ──
                self._angle_speed = 1
                self._angle_acc = 50
                code = self._arm.set_position(
                    z=50, radius=0, speed=self._tcp_speed, mvacc=self._tcp_acc,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift'):
                    break
                time.sleep(0.3)
                self._arm.set_state(0)

                # ── Barcode scan + reader config (with wiggle) ──
                self._progress(i + 1, self.cfg_cycles, "Scanning barcode")
                self._angle_speed = 25
                self._angle_acc = 250
                code = self._arm.set_servo_angle(
                    angle=BARCODE_SCAN_ANGLE, speed=self._angle_speed,
                    mvacc=self._angle_acc, wait=True, radius=0.0)
                if not self._check_code(code, 'barcode pose'):
                    break

                card = self._scan_barcode_and_config()
                card_name = card.get('name') if card else None
                barcode = self._last_barcode
                if not card:
                    error_flag = "BARCODE FAIL"
                    print('>> No barcode — skipping measurement, releasing card.')

                side_a = side_b = []
                if card:
                    # ── Present to reader, both orientations, N scans each ──
                    side_a = self._measure_side("A", PLACE_A_ANGLE, self.cfg_scans)
                    side_b = self._measure_side("B", PLACE_B_ANGLE, self.cfg_scans)

                # ── Release ──
                self._progress(i + 1, self.cfg_cycles, "Releasing card")
                self._angle_speed = 70
                self._angle_acc = 600
                self._arm.set_servo_angle(
                    angle=RELEASE_ANGLE, speed=self._angle_speed,
                    mvacc=self._angle_acc, wait=False, radius=0.0)
                self._arm.set_suction_cup(False, wait=False, delay_sec=0, hardware_version=1)

                self._emit_result(i + 1, (card_name, barcode), (side_a, side_b), error_flag)
                print('>> Card {} done in {:.1f}s'.format(i + 1, time.monotonic() - t1))

        except Exception as e:
            print('>> MainException: {}'.format(e))
        finally:
            try:
                if self._stop_event.is_set():
                    print('>> Abort — parking arm safely...')
                    try:
                        self._arm.clean_error(); self._arm.clean_warn(); self._arm.set_state(0)
                    except Exception:
                        pass
                self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
                self._arm.set_servo_angle(angle=HOME_ANGLE, speed=80, mvacc=800,
                                          wait=True, radius=0.0)
            except Exception as e:
                print('>> Park error: {}'.format(e))
            self.alive = False
            try:
                self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
                self._arm.release_state_changed_callback(self._state_changed_callback)
            except Exception:
                pass
            self._arm.disconnect()
            print('>> Arm disconnected. Done.')

    def _emit_result(self, idx, card, sides, error_flag):
        name = barcode = None
        if card:
            name, barcode = card
        a = sides[0] if sides else []
        b = sides[1] if sides else []

        def stats(vals):
            if not vals:
                return ("", "", "", 0)
            return (round(sum(vals) / len(vals), 2), round(min(vals), 2),
                    round(max(vals), 2), len(vals))

        a_avg, a_min, a_max, a_n = stats(a)
        b_avg, b_min, b_max, b_n = stats(b)
        all_vals = list(a) + list(b)
        overall_avg = round(sum(all_vals) / len(all_vals), 2) if all_vals else ""
        overall_max = round(max(all_vals), 2) if all_vals else ""

        row = {
            "Card #": idx,
            "Card Type": barcode or "",
            "Card Title": name or "",
            "Barcode": barcode or "",
            "Side A Avg (mm)": a_avg, "Side A Min": a_min, "Side A Max": a_max, "Side A Scans": a_n,
            "Side B Avg (mm)": b_avg, "Side B Min": b_min, "Side B Max": b_max, "Side B Scans": b_n,
            "Average Read Height (mm)": overall_avg,
            "Max Read Height (mm)": overall_max,
            "Error / Skip": error_flag,
        }
        self.results.append(row)
        if self._on_result:
            self._on_result(row)


# ===========================================================================
# small styled-widget helpers
# ===========================================================================
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


# ===========================================================================
# MAIN APP
# ===========================================================================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("rf IDEAS — Credential Read Height Test")
        self.root.configure(bg=BRAND['bg'])
        self.root.geometry("1000x740")
        self.root.minsize(900, 660)

        self._q = queue.Queue()
        self.worker = None
        self.robot = None
        self.arm = None
        self._last_robot = None

        # checklist state
        self.chk = {"robot": False, "reader": False, "barcode": False}
        self._scanner = None

        # config vars
        self.ip_var = tk.StringVar(value=DEFAULT_IP)
        self.reader_type = tk.StringVar(value=READER_TYPES[0])
        self.reader_other = tk.StringVar(value="")
        self.cards_var = tk.IntVar(value=5)
        self.scans_var = tk.IntVar(value=3)
        self.spec_var = tk.DoubleVar(value=20.0)
        self.descent_var = tk.DoubleVar(value=20.0)
        self.comment_var = tk.StringVar(value="")
        self.reader_info = {}

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
                     background=BRAND['white'], foreground=BRAND['text'], padding=5)
        st.configure("Brand.Horizontal.TProgressbar", troughcolor=BRAND['light'],
                     background=BRAND['red'], thickness=14)

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
        pad.pack(padx=30, pady=24)

        tk.Label(pad, text="Pre-Run Device Check", font=FONT_H1, fg=BRAND['text'],
                 bg=BRAND['card']).pack(anchor=tk.W)
        tk.Label(pad, text="All checks must pass before the test panel unlocks.",
                 font=FONT_SMALL, fg=BRAND['purple'], bg=BRAND['card']).pack(anchor=tk.W, pady=(2, 14))

        iprow = tk.Frame(pad, bg=BRAND['card'])
        iprow.pack(anchor=tk.W, pady=(0, 14))
        tk.Label(iprow, text="Robot IP", font=FONT_BODY, fg=BRAND['text'], bg=BRAND['card']).pack(side=tk.LEFT)
        tk.Entry(iprow, textvariable=self.ip_var, font=FONT_BODY, width=16).pack(side=tk.LEFT, padx=10)

        self.chk_rows = {}
        for key, label in [("robot", "Robot arm connected & ready"),
                           ("reader", "Card reader connected (USB)"),
                           ("barcode", "Barcode scanner — scan to confirm")]:
            self.chk_rows[key] = self._check_row(pad, key, label)

        tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=14)

        self.continue_btn = flat_button(pad, "CONTINUE TO TEST  →", self.show_main,
                                        fg=BRAND['white'], bg=BRAND['border'],
                                        hover=BRAND['border'], state=tk.DISABLED)
        self.continue_btn.pack(fill=tk.X, pady=(16, 0))

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
            ok = False
            if check_reader:
                res = check_reader()
                ok = res[0] if isinstance(res, (list, tuple)) else bool(res)
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

        self._scanner = BarcodeListener(on_bc)
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
    def show_main(self):
        self._clear_container()
        main = tk.Frame(self.container, bg=BRAND['bg'])
        main.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        left = tk.Frame(main, bg=BRAND['card'], width=350, highlightthickness=1,
                        highlightbackground=BRAND['divider'])
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)
        pad = tk.Frame(left, bg=BRAND['card'])
        pad.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

        section_label(pad, "Test setup").pack(anchor=tk.W)

        self._field(pad, "Reader type")
        rt = ttk.Combobox(pad, textvariable=self.reader_type, values=READER_TYPES,
                          state="readonly", style="Brand.TCombobox", font=FONT_BODY)
        rt.pack(fill=tk.X)
        rt.bind("<<ComboboxSelected>>", self._toggle_other)
        self.other_entry = tk.Entry(pad, textvariable=self.reader_other, font=FONT_BODY)

        self._field(pad, "Comment (file header)")
        tk.Entry(pad, textvariable=self.comment_var, font=FONT_BODY).pack(fill=tk.X)

        grid = tk.Frame(pad, bg=BRAND['card'])
        grid.pack(fill=tk.X, pady=(10, 0))
        tk.Label(grid, text="Cards", font=FONT_SMALL, fg=BRAND['text'], bg=BRAND['card']).grid(row=0, column=0, sticky="w")
        tk.Spinbox(grid, from_=1, to=200, textvariable=self.cards_var, width=6, font=FONT_BODY).grid(row=1, column=0, sticky="w", padx=(0, 16))
        tk.Label(grid, text="Scans / side", font=FONT_SMALL, fg=BRAND['text'], bg=BRAND['card']).grid(row=0, column=1, sticky="w")
        tk.Spinbox(grid, from_=1, to=20, textvariable=self.scans_var, width=6, font=FONT_BODY).grid(row=1, column=1, sticky="w", padx=(0, 16))
        tk.Label(grid, text="Spec min (mm)", font=FONT_SMALL, fg=BRAND['text'], bg=BRAND['card']).grid(row=0, column=2, sticky="w")
        tk.Spinbox(grid, from_=0, to=100, increment=0.5, textvariable=self.spec_var, width=6, font=FONT_BODY).grid(row=1, column=2, sticky="w")

        tk.Frame(pad, bg=BRAND['divider'], height=1).pack(fill=tk.X, pady=14)

        head = tk.Frame(pad, bg=BRAND['card'])
        head.pack(fill=tk.X)
        section_label(head, "Descent speed (onto reader)").pack(side=tk.LEFT)
        self.speed_lbl = tk.Label(head, text="20 mm/s", font=("Verdana", 12, "bold"),
                                  fg=BRAND['red'], bg=BRAND['card'])
        self.speed_lbl.pack(side=tk.RIGHT)
        tk.Scale(pad, from_=5, to=60, resolution=1, orient="horizontal", showvalue=False,
                 variable=self.descent_var, command=self._on_speed,
                 bg=BRAND['card'], troughcolor=BRAND['light'], highlightthickness=0,
                 activebackground=BRAND['red']).pack(fill=tk.X, pady=(2, 0))

        tk.Frame(pad, bg=BRAND['card']).pack(expand=True, fill=tk.BOTH)

        self.start_btn = flat_button(pad, "START TEST", self._on_start,
                                     fg=BRAND['white'], bg=BRAND['red'], hover=BRAND['red_hover'])
        self.start_btn.pack(fill=tk.X, pady=(0, 6))
        self.stop_btn = flat_button(pad, "STOP / ABORT", self._on_stop,
                                    fg=BRAND['red'], bg=BRAND['card'], hover="#FBEAEA",
                                    state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=(0, 6))
        self.export_btn = flat_button(pad, "EXPORT CSV", self._on_export,
                                      fg=BRAND['text'], bg=BRAND['light'], hover=BRAND['divider'],
                                      font=FONT_SMALL, pady=6)
        self.export_btn.pack(fill=tk.X)

        right = tk.Frame(main, bg=BRAND['card'], highlightthickness=1,
                         highlightbackground=BRAND['divider'])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0))
        rp = tk.Frame(right, bg=BRAND['card'])
        rp.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

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

        section_label(rp, "Activity log").pack(anchor=tk.W, pady=(14, 4))
        self.log = scrolledtext.ScrolledText(rp, font=FONT_MONO, bg=BRAND['log_bg'],
                                             fg="#9FE8B8", insertbackground="white",
                                             relief=tk.FLAT, padx=10, pady=8,
                                             state=tk.DISABLED, wrap=tk.WORD)
        self.log.pack(fill=tk.BOTH, expand=True)

        self.set_status("Ready — set parameters and press START")

    def _field(self, parent, text):
        tk.Label(parent, text=text, font=FONT_SMALL, fg=BRAND['text'],
                 bg=BRAND['card']).pack(anchor=tk.W, pady=(10, 2))

    def _toggle_other(self, _e=None):
        if self.reader_type.get() == "OTHER":
            self.other_entry.pack(fill=tk.X, pady=(4, 0))
        else:
            self.other_entry.pack_forget()

    def _on_speed(self, _v=None):
        v = self.descent_var.get()
        self.speed_lbl.config(text="{:g} mm/s".format(v))
        if self.robot is not None:
            self.robot.cfg_descent_speed = float(v)

    def _log(self, msg):
        self._q.put(("log", msg))

    def _append_log(self, msg):
        if not hasattr(self, "log"):
            self.set_status(msg[-90:])
            return
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _poll(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "progress":
                    cycle, total, phase = payload
                    if hasattr(self, "progress_lbl"):
                        self.progress_lbl.config(text="Card {} of {} — {}".format(cycle, total, phase))
                    if hasattr(self, "pbar"):
                        self.pbar['value'] = (cycle - 1) / max(total, 1) * 100
                elif kind == "result":
                    if hasattr(self, "passfail_lbl"):
                        self._handle_result(payload)
                elif kind == "done":
                    self._on_run_finished(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle_result(self, row):
        mx = row.get("Max Read Height (mm)")
        if mx == "" or mx is None:
            self.passfail_lbl.config(text="NO READ", fg=BRAND['amber'])
            self.passfail_dot.itemconfig(self.passfail_dot._id, fill=BRAND['amber'])
        else:
            ok = float(mx) >= self.spec_var.get()
            self.passfail_lbl.config(text="PASS" if ok else "FAIL",
                                     fg=BRAND['green'] if ok else BRAND['red'])
            self.passfail_dot.itemconfig(self.passfail_dot._id,
                                         fill=BRAND['green'] if ok else BRAND['red'])

    def _on_start(self):
        if self.worker and self.worker.is_alive():
            return
        self._start_run(cycles=max(1, int(self.cards_var.get())), verify=False)

    def _start_run(self, cycles, verify):
        if hasattr(self, "start_btn"):
            self.start_btn.config(state=tk.DISABLED)
        if hasattr(self, "stop_btn"):
            self.stop_btn.config(state=tk.NORMAL)
        if hasattr(self, "pbar"):
            self.pbar['value'] = 0
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
            robot = GuiRobot(arm)
            robot.init_gui()
            robot.cfg_cycles = cycles
            robot.cfg_scans = max(1, int(self.scans_var.get()))
            robot.cfg_descent_speed = float(self.descent_var.get())
            robot._on_progress = lambda c, t, p: self._q.put(("progress", (c, t, p)))
            robot._on_result = lambda row: self._q.put(("result", row))
            self.robot = robot
            self._last_robot = robot
            robot.run()
            if not verify:
                self._auto_export(robot)
        except Exception as e:
            self._q.put(("log", "ERROR: {}".format(e)))
        finally:
            sys.stdout = old_stdout
            self._q.put(("done", verify))

    def _on_run_finished(self, verify):
        if hasattr(self, "start_btn"):
            self.start_btn.config(state=tk.NORMAL)
        if hasattr(self, "stop_btn"):
            self.stop_btn.config(state=tk.DISABLED)
        if hasattr(self, "pbar"):
            self.pbar['value'] = 100
        self.set_status("Run finished — export CSV if needed")
        self.robot = None

    def _on_stop(self):
        if self.robot:
            self._log(">> ABORT pressed.")
            try:
                self.robot.request_abort()
            except Exception as e:
                self._log("Abort error: {}".format(e))

    def _results_dir(self):
        if config and hasattr(config, "get_results_path"):
            try:
                p = config.get_results_path("x.csv")
                return os.path.dirname(p)
            except Exception:
                pass
        if config and getattr(config, "PATHS", None) and config.PATHS.get("results"):
            return config.PATHS["results"]
        d = os.path.join(AUTOMATION_ROOT, "results")
        os.makedirs(d, exist_ok=True)
        return d

    def _write_csv(self, robot):
        if not robot or not robot.results:
            return None
        rdir = self._results_dir()
        os.makedirs(rdir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        model = self.reader_info.get("Part-Number", "reader")
        path = os.path.join(rdir, "{}_{}_read_heights.csv".format(ts, model))
        rtype = self.reader_other.get().strip()[:40] if self.reader_type.get() == "OTHER" else self.reader_type.get()
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("# rf IDEAS Credential Read Height Test\n")
            f.write("# Comment: {}\n".format(self.comment_var.get()))
            f.write("# Reader Type: {}\n".format(rtype))
            f.write("# Reader Model: {}\n".format(self.reader_info.get("Part-Number", "")))
            f.write("# Firmware Filename: {}\n".format(self.reader_info.get("Firmware Filename", "")))
            f.write("# Date: {}\n".format(ts))
            fields = list(robot.results[0].keys())
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in robot.results:
                w.writerow(row)
        return path

    def _auto_export(self, robot):
        path = self._write_csv(robot)
        if path:
            self._q.put(("log", ">> Results saved -> {}".format(path)))

    def _on_export(self):
        robot = self.robot or self._last_robot
        if robot is None or not getattr(robot, "results", None):
            messagebox.showinfo("Export", "No results yet — run a test first.")
            return
        path = self._write_csv(robot)
        if path:
            messagebox.showinfo("Export", "Saved:\n{}".format(path))

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Test running", "A test is running. Abort and exit?"):
                return
            if self.robot:
                try:
                    self.robot.request_abort()
                except Exception:
                    pass
        try:
            if self._scanner:
                self._scanner.stop()
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