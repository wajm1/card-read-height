"""robot_viewer.py — serve the three.js Lite 6 mesh viewer locally and feed it
live joint angles. Dependency-free (uses the stdlib http.server); the GUI stays
Python-only. Read-only: the browser can never command the arm.

Expected files under `root_dir` (default: a "viewer" folder beside gui.py):
    lite6_viewer.html
    lite6.urdf
    meshes/visual/link_base.stl, link1.stl ... link6.stl

Usage from the GUI:
    v = RobotViewerServer(root_dir)
    url = v.start()          # e.g. http://127.0.0.1:8765/
    v.open_in_browser()
    v.set_joints([j1..j6])   # degrees; call from the telemetry feed
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
                body = json.dumps({"j": list(srv.joints)}).encode("utf-8")
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
    def __init__(self, root_dir, host="127.0.0.1", port=8765):
        self.root_dir = os.path.abspath(root_dir)
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None
        self.joints = [0.0] * 6
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
        if self._httpd is not None:
            return self.url()
        httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        httpd.root_dir = self.root_dir
        httpd.joints = self.joints
        httpd.lock = self.lock
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url()

    def url(self):
        return "http://{}:{}/".format(self.host, self.port)

    def set_joints(self, joints):
        with self.lock:
            for i in range(min(6, len(joints))):
                self.joints[i] = float(joints[i])

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
