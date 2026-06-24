#!/usr/bin/env python3
import time
import traceback
import threading
import msvcrt
import os
import sys
from xarm import version
from xarm.wrapper import XArmAPI

# Make the project root importable so we can use the barcode + reader helpers.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from barcode.scanner import BarcodeListener, lookup_card
    from reader.cli import configure_reader_for_card
    _READER_OK = True
    _READER_ERR = None
except Exception as _e:  # these modules only exist in the full project tree
    _READER_OK = False
    _READER_ERR = _e


class CardReadListener:
    """Detects a credential read from the reader's USB keyboard-wedge output.

    Degrades gracefully: if the `keyboard` module isn't available, read_detected()
    just stays False and the descent runs to full depth (old behaviour).
    """

    def __init__(self):
        self._event = threading.Event()
        self._buf = ""
        self._hook = None

    def start(self):
        try:
            import keyboard
        except Exception as e:
            print('>> (read-detect disabled: keyboard module unavailable: {})'.format(e))
            return
        self._event.clear()
        self._buf = ""
        self._hook = keyboard.hook(self._on_key)

    def stop(self):
        if self._hook:
            try:
                import keyboard
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None

    def _on_key(self, e):
        if e.event_type != 'down':
            return
        if e.name == 'enter':
            if self._buf.strip():
                self._event.set()
        elif len(e.name) == 1:
            self._buf += e.name

    def read_detected(self):
        return self._event.is_set()


class RobotMain(object):

    def __init__(self, robot):
        self.alive = True
        self._arm = robot
        self._ignore_exit_state = False
        self._tcp_speed = 150
        self._tcp_acc = 2000
        self._angle_speed = 20
        self._angle_acc = 500
        self._stop_event = threading.Event()
        self._last_pick_z = None
        self._current_card = None
        self._robot_init()
        # Listen for Q key to stop
        self._input_thread = threading.Thread(target=self._listen_for_stop, daemon=True)
        self._input_thread.start()

    # ─── Init ────────────────────────────────────────────────────────────────

    def _robot_init(self):
        self._arm.clean_warn()
        self._arm.clean_error()
        self._arm.motion_enable(True)
        self._arm.set_mode(0)
        self._arm.set_state(0)
        time.sleep(1)
        self._arm.register_error_warn_changed_callback(self._error_warn_changed_callback)
        self._arm.register_state_changed_callback(self._state_changed_callback)

    # ─── Callbacks ───────────────────────────────────────────────────────────

    def _error_warn_changed_callback(self, data):
        if data and data['error_code'] != 0:
            self.alive = False
            self.pprint('Error {}, stopping.'.format(data['error_code']))
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)

    def _state_changed_callback(self, data):
        if not self._ignore_exit_state and data and data['state'] == 4:
            self.alive = False
            self.pprint('State=4, stopping.')
            self._arm.release_state_changed_callback(self._state_changed_callback)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _listen_for_stop(self):
        print('>> Press Q at any time for a clean stop...')
        while not self._stop_event.is_set():
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key.lower() == 'q':
                    print('>> Q pressed — finishing current move then stopping cleanly...')
                    self._stop_event.set()
                    self.alive = False
                    break
            time.sleep(0.1)

    def _check_code(self, code, label):
        if not self.is_alive or code != 0:
            self.alive = False
            ret1 = self._arm.get_state()
            ret2 = self._arm.get_err_warn_code()
            self.pprint('{} failed | code={} connected={} state={} error={} | ret1={} ret2={}'.format(
                label, code, self._arm.connected, self._arm.state, self._arm.error_code, ret1, ret2))
        return self.is_alive

    def clean_stop(self):
        """Gracefully stop — turn off suction, move to home, then disable."""
        print('>> Clean stop initiated...')
        self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
        print('>> Suction off.')
        time.sleep(0.3)
        print('>> Returning to home position...')
        self._arm.set_servo_angle(
            angle=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            speed=60, mvacc=500,
            wait=True, radius=0.0)
        time.sleep(0.5)
        self._arm.motion_enable(False)
        print('>> Arm safely stopped at home.')

    @staticmethod
    def pprint(*args, **kwargs):
        try:
            stack_tuple = traceback.extract_stack(limit=2)[0]
            print('[{}][{}] {}'.format(
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
                stack_tuple[1],
                ' '.join(map(str, args))))
        except:
            print(*args, **kwargs)

    @property
    def is_alive(self):
        if self._stop_event.is_set():
            return False
        if self.alive and self._arm.connected and self._arm.error_code == 0:
            if self._ignore_exit_state:
                return True
            if self._arm.state == 5:
                cnt = 0
                while self._arm.state == 5 and cnt < 5:
                    cnt += 1
                    time.sleep(0.1)
            return self._arm.state < 4
        return False

    # ─── Barcode read + reader configuration ──────────────────────────────────

    def _scan_barcode_and_config(self, timeout=15):
        """Read the barcode at the scan position and load the matching reader config."""
        if not _READER_OK:
            print('>> Barcode/reader modules unavailable ({}). Skipping config.'.format(_READER_ERR))
            return None

        result = {}
        event = threading.Event()

        def on_barcode(barcode):
            if result.get('card'):
                return
            card = lookup_card(barcode)
            if card:
                result['card'] = card
                event.set()
                print('>> Barcode {} -> {}'.format(barcode, card.get('name', '?')))
            else:
                print('>> Unknown barcode: {}'.format(barcode))

        listener = BarcodeListener(on_barcode)
        listener.start()
        print('>> Waiting for barcode (up to {}s)...'.format(timeout))
        event.wait(timeout=timeout)
        listener.stop()

        card = result.get('card')
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

    # ─── Descend until the card is read ────────────────────────────────────────

    def _descend_until_read(self, max_drop=70, step=2.0, speed=25):
        """Lower toward the reader in small steps; stop the instant a read is seen.

        Returns how far it actually descended (mm) so the caller can raise back up.
        """
        listener = CardReadListener()
        listener.start()
        dropped = 0.0
        try:
            print('>> Descending toward reader (stop on read, max {}mm)...'.format(max_drop))
            while dropped < max_drop:
                if not self.is_alive:
                    break
                if listener.read_detected():
                    print('>> Card READ at {:.1f}mm — stopping descent.'.format(dropped))
                    break
                code = self._arm.set_position(
                    z=-step, radius=0,
                    speed=speed, mvacc=self._tcp_acc,
                    relative=True, wait=True)
                if not self._check_code(code, 'descend toward reader'):
                    break
                dropped += step
                time.sleep(0.05)  # brief dwell to let the reader fire
                if listener.read_detected():
                    print('>> Card READ at {:.1f}mm — stopping descent.'.format(dropped))
                    break
            else:
                print('>> Reached {:.0f}mm with no read.'.format(max_drop))
        finally:
            listener.stop()
        return dropped

    # ─── Smart Pick ──────────────────────────────────────────────────────────

    def smart_pick(self):
        """
        Descends in 1mm steps at original tcp speed/acc.
        Stops immediately when suction confirms a card is grabbed.
        Records actual Z position of each pick for next cycle reference.
        Prints distance to table on every step.
        Hard cap on max descent to prevent crushing the stack.
        Backs off automatically if no card found within max depth.
        """
        STEP_SIZE    = 3.0    # mm per step
        MAX_DESCENT  = 55     # mm — hard limit, will never go beyond this
        SUCTION_WAIT = 0.2    # seconds to wait for suction check per step
        TABLE_Z      = 61 # mm — set this to your actual table Z coordinate
        

        print('>> Smart pick starting — descending in {}mm steps (max {}mm)...'.format(
            STEP_SIZE, MAX_DESCENT))

        total_descent = 0

        while total_descent < MAX_DESCENT:
            if not self.is_alive:
                return None

            # Descend one step at original speed
            code = self._arm.set_position(
                z=-STEP_SIZE, radius=-1,
                speed=self._tcp_speed, mvacc=self._tcp_acc,
                relative=True, wait=True)
            if not self._check_code(code, 'smart descend step'):
                return None

            total_descent += STEP_SIZE

            # Read current TCP position and print distance to table
            ret = self._arm.get_position()
            if ret[0] == 0:
                current_z = ret[1][2]
                distance_to_table = current_z - TABLE_Z
                print('>>   Suction cup to table: {:.1f}mm | Total descent: {:.1f}mm'.format(
                    distance_to_table, total_descent))
            else:
                current_z = None
                print('>>   Could not read position at descent {:.1f}mm'.format(total_descent))


            # Check air pump state — confirm suction grab
            if self._arm.arm.check_air_pump_state(1, timeout=SUCTION_WAIT, hardware_version=1):
                if current_z is not None:
                    self._last_pick_z = current_z
                    print('>> Card grabbed! Z={:.2f}mm | {:.1f}mm from table | after {:.1f}mm descent'.format(
                        current_z, current_z - TABLE_Z, total_descent))
                return current_z

        # Hit max descent with no grab — back off immediately to prevent damage
        print('>> WARNING: No card detected within {}mm — backing off!'.format(MAX_DESCENT))
        self._arm.set_position(
            z=MAX_DESCENT, radius=-1,
            speed=self._tcp_speed, mvacc=self._tcp_acc,
            relative=True, wait=True)
        return None

    # ─── Main Run ────────────────────────────────────────────────────────────

    def run(self):
        try:
            # ── Max speed home before loop ────────────────────────────────
            print('>> Setting arm to max speed for home position...')
            code = self._arm.set_servo_angle(
                angle=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                speed=180, mvacc=1100,
                wait=True, radius=0.0)
            if not self._check_code(code, 'home position'): return
            print('>> Home reached. Starting card cycles...')

            for i in range(14):
                if not self.is_alive:
                    break

                print('>> ─────────────────────────────────')
                print('>> Cycle {} of 14'.format(i + 1))
                t1 = time.monotonic()

                # ── Move to Pick Position ─────────────────────────────────

                self._angle_speed = 180
                self._angle_acc = 1100

                code = self._arm.set_servo_angle(
                    angle=[-43.6, 50.0, 71.5, 180.0, -19.8, -134.4],
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0)
                if not self._check_code(code, 'move to pick'): return

                # Enable suction before descending
                code = self._arm.set_suction_cup(True, wait=False, delay_sec=0, hardware_version=1)
                if not self._check_code(code, 'suction on'): return

                # ── Smart Descend & Pick ──────────────────────────────────

                pick_z = self.smart_pick()

                if pick_z is None:
                    print('>> Pick failed on cycle {} — stopping run.'.format(i + 1))
                    break

                time.sleep(0.3)

                # ── Lift ──────────────────────────────────────────────────

                self._angle_speed = 1
                self._angle_acc = 50

                # Slow gentle lift right after grab
                code = self._arm.set_position(
                    z=50, radius=0,
                    speed=self._tcp_speed, mvacc=self._tcp_acc,
                    relative=True, wait=True)
                if not self._check_code(code, 'lift card'): return

                time.sleep(0.3)

                code = self._arm.set_state(0)
                if not self._check_code(code, 'set_state'): return

                # ── Scan the barcode & configure the reader ───────────────

                self._angle_speed = 25
                self._angle_acc = 250

                code = self._arm.set_servo_angle(
                    angle=[-43.7, 48.5, 71.5, 142.4, -74.1, -106.1],
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0)
                if not self._check_code(code, 'move to barcode scan'): return

                # Read the barcode here and load the matching reader config
                self._scan_barcode_and_config()

                # ── Place Position 1 (reader side A) ──────────────────────

                self._angle_speed = 70
                self._angle_acc = 600

                code = self._arm.set_servo_angle(
                    angle=[4.2, 27.4, 39.5, 186.7, -10.4, -90],
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0)
                if not self._check_code(code, 'move to place 1'): return

                # Descend toward the reader, stop as soon as the card is read
                dropped = self._descend_until_read(max_drop=70, step=2.0, speed=25)

                # Raise back up by however far we descended
                code = self._arm.set_position(
                    z=dropped, radius=0,
                    speed=self._tcp_speed, mvacc=self._tcp_acc,
                    relative=True, wait=True)
                if not self._check_code(code, 'raise from place 1'): return

                # ── Place Position 2 (reader side B) ──────────────────────

                code = self._arm.set_servo_angle(
                    angle=[4.2, 27.4, 39.5, 186.7, -10.4, -180],
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=True, radius=0.0)
                if not self._check_code(code, 'move to place 2'): return

                # Descend toward the reader, stop as soon as the card is read
                dropped = self._descend_until_read(max_drop=70, step=2.0, speed=25)

                # Raise back up by however far we descended
                code = self._arm.set_position(
                    z=dropped, radius=0,
                    speed=self._tcp_speed, mvacc=self._tcp_acc,
                    relative=True, wait=True)
                if not self._check_code(code, 'raise from place 2'): return

                # ── Final Position & Release ──────────────────────────────

                code = self._arm.set_servo_angle(
                    angle=[44.4, 58.7, 76.5, 168.6, -14.4, -112.8],
                    speed=self._angle_speed, mvacc=self._angle_acc,
                    wait=False, radius=0.0)
                if not self._check_code(code, 'move to final position'): return

                code = self._arm.set_suction_cup(False, wait=False, delay_sec=0, hardware_version=1)
                if not self._check_code(code, 'suction off'): return

                self._angle_acc = 1100

                interval = time.monotonic() - t1
                print('>> Cycle {} complete in {:.2f}s'.format(i + 1, interval))

        except Exception as e:
            self.pprint('MainException: {}'.format(e))

        finally:
            if self._stop_event.is_set():
                self.clean_stop()
            else:
                # Normal finish — go home cleanly
                self._arm.set_suction_cup(False, wait=True, delay_sec=0, hardware_version=1)
                self._arm.set_servo_angle(
                    angle=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    speed=60, mvacc=500,
                    wait=True, radius=0.0)
            self.alive = False
            self._arm.release_error_warn_changed_callback(self._error_warn_changed_callback)
            self._arm.release_state_changed_callback(self._state_changed_callback)
            self._arm.disconnect()
            print('>> Arm disconnected. Done.')


if __name__ == '__main__':
    RobotMain.pprint('xArm-Python-SDK Version: {}'.format(version.__version__))
    arm = XArmAPI('192.168.1.177', baud_checkset=False)
    time.sleep(0.5)
    robot_main = RobotMain(arm)
    robot_main.run()