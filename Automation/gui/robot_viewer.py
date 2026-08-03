# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""Local HTTP three.js Lite 6 mesh viewer (browser) for the Tk GUI.

Role
    Dependency-free stdlib ``http.server`` that serves ``gui/viewer/`` assets,
    a ``/joints`` JSON endpoint (angles + suction), and ``/stations`` (workcell
    marker joint poses). Read-only: the browser never commands the arm.

Inputs
    ``root_dir`` with ``lite6_viewer.html``, ``lite6.urdf``, and
    ``meshes/visual/link_base.stl`` … ``link6.stl``. Joint angles (deg) and
    optional suction flag via ``set_state``.

Outputs / side effects
    Binds a local TCP port (default 8765); opens a browser tab on request.

Usage from the GUI::

    v = RobotViewerServer(root_dir)
    url = v.start()          # e.g. http://127.0.0.1:8765/
    v.open_in_browser()
    v.set_state([j1..j6], suction=True)
    v.stop()
"""

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".urdf": "application/xml",
    ".xml": "application/xml",
    ".stl": "application/octet-stream",
    ".js": "text/javascript",
    ".json": "application/json",
    ".css": "text/css",
}


def _station_defs():
    """Workcell markers as joint poses (deg) from gui/constants.py."""
    try:
        from constants import (
            DROP_ANGLE, PICK_ANGLE, READER_STAGING_0_ANGLE, FLIP_REGRAB_POSE,
        )
    except Exception:
        return []
    return [
        {"id": "drop", "label": "Drop", "j": [float(x) for x in DROP_ANGLE[:6]]},
        {"id": "pickup", "label": "pick up", "j": [float(x) for x in PICK_ANGLE[:6]]},
        {"id": "reader", "label": "Reader",
         "j": [float(x) for x in READER_STAGING_0_ANGLE[:6]]},
        {"id": "flip", "label": "Flip", "j": [float(x) for x in FLIP_REGRAB_POSE[:6]]},
    ]


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the GUI console quiet

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        srv = self.server
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            path = "/lite6_viewer.html"

        if path == "/joints":
            with srv.lock:
                body = json.dumps({
                    "j": list(srv.joints),
                    "suction": bool(srv.suction),
                }).encode("utf-8")
            self._send(200, body, "application/json")
            return

        if path == "/stations":
            with srv.lock:
                stations = list(srv.stations)
            body = json.dumps({"stations": stations}).encode("utf-8")
            self._send(200, body, "application/json")
            return

        # static file, restricted to root_dir (no traversal)
        rel = path.lstrip("/")
        full = os.path.normpath(os.path.join(srv.root_dir, rel))
        if not full.startswith(os.path.normpath(srv.root_dir)):
            self._send(403, b"forbidden", "text/plain")
            return
        if not os.path.isfile(full):
            self._send(404, b"not found: " + rel.encode("utf-8", "replace"), "text/plain")
            return
        try:
            with open(full, "rb") as f:
                data = f.read()
        except Exception as e:
            self._send(500, str(e).encode("utf-8"), "text/plain")
            return
        ctype = _MIME.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        self._send(200, data, ctype)


class RobotViewerServer:
    """Serve viewer assets, live joint/suction state, and station poses."""

    def __init__(self, root_dir, host="127.0.0.1", port=8765):
        self.root_dir = os.path.abspath(root_dir)
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None
        self.joints = [0.0] * 6
        self.suction = False
        self.stations = _station_defs()
        self.lock = threading.Lock()

    def files_present(self):
        """True if the viewer assets exist (so the GUI can warn if not)."""
        need = [
            "lite6_viewer.html", "lite6.urdf",
            os.path.join("meshes", "visual", "link_base.stl"),
            os.path.join("meshes", "visual", "link6.stl"),
        ]
        return all(os.path.isfile(os.path.join(self.root_dir, n)) for n in need)

    def start(self):
        """Start the daemon HTTP server; return the viewer URL."""
        if self._httpd is not None:
            return self.url()
        httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        httpd.root_dir = self.root_dir
        httpd.joints = self.joints
        httpd.suction = self.suction
        httpd.stations = self.stations
        httpd.lock = self.lock
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url()

    def url(self):
        return "http://{}:{}/".format(self.host, self.port)

    def set_joints(self, joints):
        """Update cached J1–J6 angles (degrees). Prefer ``set_state`` when suction is known."""
        self.set_state(joints)

    def set_state(self, joints, suction=None):
        """Update joints and optional suction flag served at ``/joints``."""
        with self.lock:
            if joints is not None:
                for i in range(min(6, len(joints))):
                    self.joints[i] = float(joints[i])
            if suction is not None:
                self.suction = bool(suction)
            if self._httpd is not None:
                self._httpd.joints = self.joints
                self._httpd.suction = self.suction

    def open_in_browser(self):
        try:
            webbrowser.open(self.url())
            return True
        except Exception:
            return False

    def stop(self):
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
