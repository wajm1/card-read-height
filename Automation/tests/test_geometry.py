"""Characterization tests for the read-height geometry / joint math.

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Lock in the pure math that converts TCP height <-> card-face height and that
    keeps the wrist (J6) inside the Lite 6 limits (the fix that prevents the C23
    fault at the drop bin). These functions have no hardware dependency; if a
    refactor changes their output, these tests fail.
"""

import config
from constants import (
    nearest_j6_in_range, joint_limit_issues, LITE6_JOINT_LIMITS,
)


def test_card_face_offset_is_added():
    # Card face sits SUCTION_CUP_CARD_OFFSET_MM above the TCP.
    assert config.card_face_above_table_from_tcp(50.0) == 50.0 + config.SUCTION_CUP_CARD_OFFSET_MM


def test_tcp_and_card_face_round_trip():
    for h in (0.0, 12.5, 44.0, 101.6):
        tcp = config.tcp_above_table_for_card_face(h)
        assert abs(config.card_face_above_table_from_tcp(tcp) - h) < 1e-9


def test_nearest_j6_stays_in_range_and_physically_identical():
    lo, hi = LITE6_JOINT_LIMITS[5]
    # A commanded -630.8 deg is identical (mod 360) to -270.8 which is legal.
    out = nearest_j6_in_range(-630.8, ref_j6=-270.8)
    assert lo < out < hi
    # Physically identical => difference is an integer number of full turns.
    assert abs(((out - (-630.8)) % 360.0)) < 1e-6


def test_nearest_j6_prefers_value_closest_to_reference():
    # 350 and -10 are physically identical (differ by 360) and BOTH inside the
    # safe range, so the wind closest to the wrist's current angle is chosen.
    assert abs(nearest_j6_in_range(350.0, ref_j6=340.0) - 350.0) < 1e-6
    assert abs(nearest_j6_in_range(350.0, ref_j6=0.0) - (-10.0)) < 1e-6


def test_nearest_j6_excludes_values_past_the_safety_margin():
    # 360 is identical to 0 but sits outside the +/-358.5 safe band, so the
    # in-range wind (0) is returned rather than 360 even when ref is near 360.
    assert abs(nearest_j6_in_range(0.0, ref_j6=350.0) - 0.0) < 1e-6


def test_joint_limit_issues_flags_out_of_range():
    good = [0, 0, 0, 0, 0, 0]
    assert joint_limit_issues(good) == []
    bad = [0, 200, 0, 0, 0, 0]      # J2 limit is +/-150
    issues = joint_limit_issues(bad)
    assert issues and "J2" in issues[0]
