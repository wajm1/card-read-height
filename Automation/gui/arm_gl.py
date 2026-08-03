# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""Embedded OpenGL Lite 6 mesh viewer for the Tk GUI (Live arm panel).

Role
    Renders UFACTORY visual STL meshes inside a Tk widget via pyopengltk +
    PyOpenGL. Read-only: consumes joint angles the GUI already polls; never
    commands the arm.

Inputs
    Parent Tk widget, path to ``viewer/meshes/visual/*.stl``, joint angles (deg).

Outputs / side effects
    Draws into an OpenGL frame. Requires optional deps:
    ``pip install pyopengltk PyOpenGL numpy``.

Kinematics use the Lite 6 URDF joint chain (validated to match the DH model to
<1 mm), so the on-screen pose matches the real arm.
"""

import math
import os
import struct
import tkinter as tk

# URDF joint chain: (xyz meters, rpy radians). Axis is +Z for every joint.
_CHAIN = [
    ((0.0, 0.0, 0.2435), (0.0, 0.0, 0.0)),
    ((0.0, 0.0, 0.0),     (1.5708, -1.5708, 3.1416)),
    ((0.2002, 0.0, 0.0),  (-3.1416, 0.0, 1.5708)),
    ((0.087, -0.22761, 0.0), (1.5708, 0.0, 0.0)),
    ((0.0, 0.0, 0.0),     (1.5708, 0.0, 0.0)),
    ((0.0, 0.0625, 0.0),  (-1.5708, 0.0, 0.0)),
]
_LINK_FILES = ["link_base", "link1", "link2", "link3", "link4", "link5", "link6"]
# link6 (tool flange) rendered slightly darker
_LINK_COLORS = [(0.90, 0.90, 0.92)] * 6 + [(0.62, 0.62, 0.66)]


def _read_binary_stl(path):
    """Return a flat list of (nx,ny,nz,(x,y,z)*3) triangles from a binary STL."""
    tris = []
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        data = f.read(n * 50)
    off = 0
    for _ in range(n):
        nx, ny, nz = struct.unpack_from("<3f", data, off); off += 12
        v = []
        for _v in range(3):
            v.append(struct.unpack_from("<3f", data, off)); off += 12
        off += 2  # attribute byte count
        tris.append((nx, ny, nz, v[0], v[1], v[2]))
    return tris


def _rpy(r, p, y):
    import numpy as np
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _origin(xyz, rpy):
    import numpy as np
    M = np.eye(4)
    M[:3, :3] = _rpy(*rpy)
    M[:3, 3] = xyz
    return M


def _rotz(deg):
    import numpy as np
    q = math.radians(deg)
    c, s = math.cos(q), math.sin(q)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)


def link_transforms(joints_deg):
    """Cumulative 4x4 transform for each of the 7 links given joint angles."""
    import numpy as np
    Ts = [np.eye(4)]                      # link_base
    M = np.eye(4)
    for i in range(6):
        xyz, rpy = _CHAIN[i]
        M = M @ _origin(xyz, rpy) @ _rotz(joints_deg[i] if i < len(joints_deg) else 0.0)
        Ts.append(M.copy())
    return Ts


class ArmGLViewer:
    """Embeddable OpenGL Lite 6 view. Pack `self.frame`; call update(joints_deg)."""

    def __init__(self, parent, mesh_dir, brand=None):
        self.ok = False
        self.err = None
        b = brand or {}
        bg = b.get("bg3d", "#1b1d23")
        self.frame = tk.Frame(parent, bg=bg)
        self._gl = None
        try:
            import numpy            # noqa: F401
            from OpenGL import GL   # noqa: F401
            from pyopengltk import OpenGLFrame
        except Exception as e:      # pragma: no cover
            self.err = e
            tk.Label(
                self.frame,
                text=("Embedded 3D needs pyopengltk + PyOpenGL.\n\n"
                      "Install (Windows):\n"
                      "    py -3.14 -m pip install pyopengltk PyOpenGL\n\n"
                      "Then reopen the GUI.\n\n({})".format(e)),
                fg="#C9C9D4", bg=bg, justify="center", padx=12, pady=18,
            ).pack(fill=tk.BOTH, expand=True)
            return

        # parse meshes up front (no GL context needed yet)
        try:
            meshes = []
            for name in _LINK_FILES:
                meshes.append(_read_binary_stl(os.path.join(mesh_dir, name + ".stl")))
        except Exception as e:
            self.err = e
            tk.Label(self.frame,
                     text="Mesh files not found in:\n{}\n\n({})".format(mesh_dir, e),
                     fg="#C9C9D4", bg=bg, justify="center", padx=12, pady=18).pack(
                         fill=tk.BOTH, expand=True)
            return

        self._gl = _GLFrame(self.frame, meshes, bg=bg)
        self._gl.pack(fill=tk.BOTH, expand=True)
        self.ok = True

    def alive(self):
        try:
            return self.ok and bool(self.frame.winfo_exists())
        except Exception:
            return False

    def update(self, joints_deg, force=False):
        """Push live joint angles (degrees) into the OpenGL frame."""
        if self.ok and self._gl is not None:
            self._gl.set_joints(joints_deg)

    def close(self):
        """Destroy the Tk frame hosting the viewer."""
        try:
            self.frame.destroy()
        except Exception:
            pass


def _make_gl_frame_class():
    """Build the OpenGLFrame subclass lazily (only when GL is importable)."""
    from OpenGL import GL, GLU
    from pyopengltk import OpenGLFrame
    import numpy as np

    class _GLFrameImpl(OpenGLFrame):
        def __init__(self, parent, meshes, bg="#1b1d23"):
            super().__init__(parent, width=520, height=300)
            self._meshes = meshes
            self._lists = None
            self._joints = [0.0] * 6
            # Default camera close to UFactory Studio's 3/4 front view
            self._az = -48.0     # orbit azimuth (deg)
            self._el = 28.0      # orbit elevation (deg)
            self._dist = 1.05    # camera distance (m)
            self._target = (0.05, 0.0, 0.26)
            self._lastxy = None
            self.animate = 33    # ~30 fps continuous redraw
            self.bind("<Button-1>", self._on_press)
            self.bind("<B1-Motion>", self._on_drag)
            self.bind("<MouseWheel>", self._on_wheel)          # Windows/mac
            self.bind("<Button-4>", lambda e: self._zoom(0.9))  # Linux
            self.bind("<Button-5>", lambda e: self._zoom(1.1))

        def set_joints(self, j):
            self._joints = [float(x) for x in j[:6]] + [0.0] * max(0, 6 - len(j))

        # ---- mouse ----
        def _on_press(self, e):
            self._lastxy = (e.x, e.y)

        def _on_drag(self, e):
            if self._lastxy is None:
                self._lastxy = (e.x, e.y); return
            dx = e.x - self._lastxy[0]; dy = e.y - self._lastxy[1]
            self._lastxy = (e.x, e.y)
            self._az += dx * 0.4
            self._el = max(-89.0, min(89.0, self._el + dy * 0.4))

        def _on_wheel(self, e):
            self._zoom(0.9 if e.delta > 0 else 1.1)

        def _zoom(self, f):
            self._dist = max(0.4, min(4.0, self._dist * f))

        # ---- GL ----
        def initgl(self):
            GL.glClearColor(0.106, 0.114, 0.137, 1.0)
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_LIGHTING)
            GL.glEnable(GL.GL_LIGHT0)
            GL.glEnable(GL.GL_LIGHT1)
            GL.glEnable(GL.GL_NORMALIZE)
            GL.glEnable(GL.GL_COLOR_MATERIAL)
            GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [1.5, 1.2, 2.5, 0.0])
            GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
            GL.glLightfv(GL.GL_LIGHT1, GL.GL_POSITION, [-1.5, -1.0, 1.0, 0.0])
            GL.glLightfv(GL.GL_LIGHT1, GL.GL_DIFFUSE, [0.35, 0.35, 0.4, 1.0])
            GL.glShadeModel(GL.GL_SMOOTH)
            if self._lists is None:
                self._lists = []
                for tris in self._meshes:
                    lid = GL.glGenLists(1)
                    GL.glNewList(lid, GL.GL_COMPILE)
                    GL.glBegin(GL.GL_TRIANGLES)
                    for (nx, ny, nz, a, bb, c) in tris:
                        GL.glNormal3f(nx, ny, nz)
                        GL.glVertex3f(*a); GL.glVertex3f(*bb); GL.glVertex3f(*c)
                    GL.glEnd()
                    GL.glEndList()
                    self._lists.append(lid)

        def redraw(self):
            w = max(1, self.winfo_width()); h = max(1, self.winfo_height())
            GL.glViewport(0, 0, w, h)
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            GL.glMatrixMode(GL.GL_PROJECTION); GL.glLoadIdentity()
            GLU.gluPerspective(42.0, w / float(h), 0.02, 20.0)
            GL.glMatrixMode(GL.GL_MODELVIEW); GL.glLoadIdentity()

            # orbit camera around target, Z-up
            az = math.radians(self._az); el = math.radians(self._el)
            tx, ty, tz = self._target
            cx = tx + self._dist * math.cos(el) * math.cos(az)
            cy = ty + self._dist * math.cos(el) * math.sin(az)
            cz = tz + self._dist * math.sin(el)
            GLU.gluLookAt(cx, cy, cz, tx, ty, tz, 0.0, 0.0, 1.0)

            self._draw_grid()

            if self._lists:
                Ts = link_transforms(self._joints)
                for i, lid in enumerate(self._lists):
                    GL.glColor3f(*_LINK_COLORS[i])
                    GL.glPushMatrix()
                    GL.glMultMatrixf(np.ascontiguousarray(Ts[i].T, dtype=np.float32))
                    GL.glCallList(lid)
                    GL.glPopMatrix()
                # TCP RGB triad at the flange (UFactory Studio style)
                self._draw_tcp_axes(Ts[-1])

        def _draw_grid(self):
            GL.glDisable(GL.GL_LIGHTING)
            n = 10
            step = 0.1
            # faint grid
            GL.glColor3f(0.20, 0.22, 0.26)
            GL.glBegin(GL.GL_LINES)
            for i in range(-n, n + 1):
                if i == 0:
                    continue
                x = i * step
                GL.glVertex3f(x, -n * step, 0.0); GL.glVertex3f(x, n * step, 0.0)
                GL.glVertex3f(-n * step, x, 0.0); GL.glVertex3f(n * step, x, 0.0)
            GL.glEnd()
            # brighter center axes
            GL.glColor3f(0.32, 0.34, 0.40)
            GL.glBegin(GL.GL_LINES)
            GL.glVertex3f(-n * step, 0.0, 0.0); GL.glVertex3f(n * step, 0.0, 0.0)
            GL.glVertex3f(0.0, -n * step, 0.0); GL.glVertex3f(0.0, n * step, 0.0)
            GL.glEnd()
            GL.glEnable(GL.GL_LIGHTING)

        def _draw_tcp_axes(self, T):
            """Draw RGB XYZ arrows at the tool flange (like UFactory Studio)."""
            GL.glDisable(GL.GL_LIGHTING)
            GL.glLineWidth(2.5)
            origin = T[:3, 3]
            axes = (
                (T[:3, 0], (0.92, 0.22, 0.22)),  # X red
                (T[:3, 1], (0.22, 0.82, 0.28)),  # Y green
                (T[:3, 2], (0.25, 0.45, 0.95)),  # Z blue
            )
            length = 0.08
            GL.glBegin(GL.GL_LINES)
            for axis, color in axes:
                tip = origin + axis * length
                GL.glColor3f(*color)
                GL.glVertex3f(*origin)
                GL.glVertex3f(*tip)
            GL.glEnd()
            GL.glLineWidth(1.0)
            GL.glEnable(GL.GL_LIGHTING)

    return _GLFrameImpl


# Build the concrete class only if the GL stack imports; else _GLFrame stays None.
try:
    _GLFrame = _make_gl_frame_class()
except Exception:      # pragma: no cover
    _GLFrame = None
