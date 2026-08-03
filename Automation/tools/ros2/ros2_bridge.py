#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# Author:  Wajahat Mahmood
# Updated: 2026-07-30
# Project: rf IDEAS Credential Read Height Automation
# Summary: see the module docstring below for this file's responsibility.
# ---------------------------------------------------------------------------
"""ros2_bridge.py — republish Lite 6 telemetry from the read-height GUI onto the
ROS2 graph as sensor_msgs/JointState (and test results as std_msgs/String JSON).

WHY A SEPARATE PROCESS?
    ROS2's rclpy is built against the ROS2 distro's Python (e.g. 3.12 for Jazzy)
    and can't be imported into the GUI's Python 3.14 process. So the GUI stays
    100% ROS-free and simply emits small JSON/UDP packets. This node — run in
    your ROS2 environment (Ubuntu / WSL2 / another machine) — listens on that
    UDP port and publishes to the ROS graph. Because the link is one-way UDP,
    the bridge can NEVER command the arm; if it isn't running, the GUI is
    unaffected (packets are simply dropped).

TELEMETRY WIRE FORMAT (one JSON object per UDP datagram):
    {"t": "joints", "j": [j1..j6]}            # joint angles, DEGREES
    {"t": "result", "row": [...]}             # a results CSV row (list of cells)

USAGE (in your ROS2 env):
    # 1) publish the Lite 6 model so rviz2 can render the real meshes:
    ros2 launch xarm_description lite6_rviz_display.launch.py      # or your own
    #    (robot_state_publisher + rviz2 with the official Lite 6 URDF)
    # 2) run this bridge:
    python tools/ros2/ros2_bridge.py --udp-port 9870   # from Automation/
    # In rviz2: Fixed Frame = link_base (or "world"), add a RobotModel display.
    # The arm now mirrors the live rig.

Topics published:
    /joint_states            sensor_msgs/JointState
    /read_height/results     std_msgs/String   (JSON of each result row)
"""

import argparse
import json
import math
import socket
import threading

JOINT_NAMES = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]


def _udp_reader(sock, on_packet, stop_evt):
    sock.settimeout(0.5)
    while not stop_evt.is_set():
        try:
            data, _addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            break
        for line in data.decode("utf-8", "replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                on_packet(json.loads(line))
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description="UDP -> ROS2 JointState bridge for the Lite 6 read-height rig")
    ap.add_argument("--udp-host", default="0.0.0.0", help="UDP bind host (default 0.0.0.0)")
    ap.add_argument("--udp-port", type=int, default=9870, help="UDP port (default 9870)")
    args = ap.parse_args()

    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import JointState
        from std_msgs.msg import String
    except Exception as e:
        raise SystemExit(
            "rclpy / ROS2 message packages not found. Run this script inside a "
            "sourced ROS2 environment (e.g. `source /opt/ros/jazzy/setup.bash`). "
            "Original error: {}".format(e)
        )

    rclpy.init()
    node = Node("lite6_read_height_bridge")
    js_pub = node.create_publisher(JointState, "/joint_states", 10)
    res_pub = node.create_publisher(String, "/read_height/results", 10)
    node.get_logger().info("Lite 6 bridge up. Listening for UDP telemetry on {}:{}".format(
        args.udp_host, args.udp_port))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.udp_host, args.udp_port))

    def on_packet(msg):
        kind = msg.get("t")
        if kind == "joints":
            j = msg.get("j") or []
            if len(j) >= 6:
                m = JointState()
                m.header.stamp = node.get_clock().now().to_msg()
                m.name = list(JOINT_NAMES)
                m.position = [math.radians(float(a)) for a in j[:6]]
                js_pub.publish(m)
        elif kind == "result":
            s = String()
            s.data = json.dumps(msg.get("row"))
            res_pub.publish(s)

    stop_evt = threading.Event()
    reader = threading.Thread(target=_udp_reader, args=(sock, on_packet, stop_evt), daemon=True)
    reader.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            sock.close()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
