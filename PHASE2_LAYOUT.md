# Phase 2 target layout (approved)

Sign-off: delete/quarantine list from ARCHITECTURE.md §8 (user: Y).

```
Automation/
├── config.py
├── requirements.txt
├── barcode/
│   └── scanner.py
├── reader/
│   ├── cli.py
│   ├── ReaderConfig.py
│   └── ReaderConfigSDK.py
├── robot/                      # production motion + CLI
│   ├── move.py
│   ├── cardreadheight.py
│   └── test_settings.py
├── gui/                        # operator UI + optional viewers used by UI
│   ├── gui.py
│   ├── arm_gl.py               # embedded Live arm (required for mesh view)
│   ├── robot_viewer.py         # browser mesh view
│   └── viewer/                 # meshes + html + urdf (canonical)
│       ├── lite6_viewer.html
│       ├── lite6.urdf
│       └── meshes/visual/*.stl
└── tools/                      # optional / experimental / commissioning
    ├── cardheight.py           # interactive Z jogger (was robot/)
    ├── experimental/
    │   └── move2.py            # reverse characteriser (was robot/)
    └── ros2/
        └── ros2_bridge.py      # UDP→ROS2 (was gui/)
```

## Actions this phase

| Action | Item |
|--------|------|
| **Delete** | `gui/arm3d.py` + strip unused import from `gui.py` |
| **Quarantine** | `robot/move2.py` → `tools/experimental/move2.py` (fix `AUTOMATION_ROOT`) |
| **Move** | `robot/cardheight.py` → `tools/cardheight.py` |
| **Move** | `gui/ros2_bridge.py` → `tools/ros2/ros2_bridge.py` |
| **Delete duplicates** | `gui/lite6_viewer.html`, `gui/lite6.urdf` (canonical copies stay under `viewer/`) |

No production motion/timing/CSV behavior changes. Entry points `python gui/gui.py` and `python robot/cardreadheight.py` unchanged.
