"""Characterization tests for per-angle staging pose derivation.

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    The read angles (0/90/180/270) are produced by rotating ONLY the wrist (J6)
    of the calibrated 0-degree staging pose. Getting this wrong points the card
    at the wrong orientation or trips a joint limit, so lock the mapping and the
    +/-360 wrap. Uses the FakeArm-backed GuiRobot fixture (no real motion).
"""

from constants import READER_STAGING_0_ANGLE, LITE6_JOINT_LIMITS


def test_zero_angle_matches_calibrated_staging(gui_robot):
    pose = gui_robot._staging_pose_for_angle(0)
    assert pose[:5] == list(READER_STAGING_0_ANGLE)[:5]


def test_each_angle_only_moves_the_wrist(gui_robot):
    base = list(gui_robot.cfg_staging_0)
    for angle in (0, 90, 180, 270):
        pose = gui_robot._staging_pose_for_angle(angle)
        # J1..J5 identical across every angle.
        assert pose[:5] == base[:5]


def test_angle_offsets_are_applied_to_j6(gui_robot):
    base_j6 = list(gui_robot.cfg_staging_0)[5]
    # +J6 == +physical degrees on this rig; offset equals the angle itself.
    for angle, offset in ((0, 0.0), (90, 90.0), (180, 180.0), (270, 270.0)):
        pose = gui_robot._staging_pose_for_angle(angle)
        expected = base_j6 + offset
        while expected > 360.0:
            expected -= 360.0
        while expected < -360.0:
            expected += 360.0
        assert abs(pose[5] - expected) < 1e-6


def test_wrist_stays_within_limits(gui_robot):
    lo, hi = LITE6_JOINT_LIMITS[5]
    for angle in (0, 90, 180, 270):
        pose = gui_robot._staging_pose_for_angle(angle)
        assert lo <= pose[5] <= hi


def test_custom_calibrated_staging_pose_is_used(gui_robot):
    # A calibrated staging pose (from MARK READER TOP) overrides the default.
    gui_robot.cfg_staging_0 = [1.0, 2.0, 3.0, 4.0, 5.0, -10.0]
    pose = gui_robot._staging_pose_for_angle(90)
    assert pose[:5] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert abs(pose[5] - (-10.0 + 90.0)) < 1e-6
