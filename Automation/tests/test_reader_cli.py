"""Characterization tests for RRMTool HWG helpers (used by all three tests).

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Lock the HWG-file editing that the reader configuration relies on: reading a
    card's primary CardType, rewriting integer settings while preserving trailing
    comments, and building the short-lockout "continuous read" HWG used by the
    Deadzone and Tap-and-Go tests. No RRMTool_CLI or reader hardware is invoked.
"""

from reader import cli

SAMPLE_HWG = """CardType: 31233 / 0
iIDLockOutTm = 500  ; lockout ms
iIDHoldTO = 200
bSndOnRx = 1
"""


def test_rewrite_hwg_int_replaces_value_and_keeps_comment():
    out = cli._rewrite_hwg_int(SAMPLE_HWG, "iIDLockOutTm", 100)
    assert "iIDLockOutTm = 100" in out
    assert "; lockout ms" in out       # trailing comment preserved


def test_parse_hwg_primary_card_type(tmp_path):
    p = tmp_path / "card.hwg+"
    p.write_text(SAMPLE_HWG, encoding="utf-8")
    assert cli.parse_hwg_primary_card_type(str(p)) == 31233


def test_parse_hwg_primary_card_type_none_when_zero(tmp_path):
    p = tmp_path / "z.hwg+"
    p.write_text("CardType: 0 / 0\n", encoding="utf-8")
    assert cli.parse_hwg_primary_card_type(str(p)) is None


def test_make_continuous_hwg_applies_short_lockout(tmp_path):
    src = tmp_path / "src.hwg+"
    src.write_text(SAMPLE_HWG, encoding="utf-8")
    dest = cli.make_continuous_hwg(str(src), str(tmp_path / "cont.hwg+"))
    text = open(dest, encoding="utf-8").read()
    assert "iIDLockOutTm = {}".format(cli.CONTINUOUS_LOCKOUT_MS) in text
    assert "iIDHoldTO = {}".format(cli.CONTINUOUS_HOLD_MS) in text
    # bSndOnRx must stay 0 (see cli.py note: 1 bypasses the lockout timer).
    assert "bSndOnRx = 0" in text
