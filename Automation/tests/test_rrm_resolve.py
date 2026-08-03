"""Tests for RRMTool_CLI.exe path resolution (the 'reader config failed' fix).

Author:  Wajahat Mahmood
Created: 2026-07-30
Purpose:
    Verify the rig finds RRMTool_CLI.exe from the environment variable and from
    the persistent override file (files/rrmtool_path.txt), tolerates a comment-
    only override file, and falls back to the canonical default when nothing
    exists. This is what prevents the "RRMTool_CLI not found" reader-config
    failure when RRMTool is installed somewhere other than Program Files.
"""

import config


def test_read_rrm_path_file_returns_first_real_line(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_ROOT", str(tmp_path))
    files = tmp_path / "files"
    files.mkdir()
    (files / "rrmtool_path.txt").write_text(
        '# a comment\n"C:\\tools\\RRMTool_CLI.exe"\n', encoding="utf-8")
    assert config._read_rrm_path_file() == "C:\\tools\\RRMTool_CLI.exe"


def test_read_rrm_path_file_comment_only_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_ROOT", str(tmp_path))
    files = tmp_path / "files"
    files.mkdir()
    (files / "rrmtool_path.txt").write_text("# only comments here\n", encoding="utf-8")
    assert config._read_rrm_path_file() is None


def test_read_rrm_path_file_missing_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_ROOT", str(tmp_path))  # no files/ dir
    assert config._read_rrm_path_file() is None


def test_resolve_prefers_existing_env_var(tmp_path, monkeypatch):
    exe = tmp_path / "RRMTool_CLI.exe"
    exe.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("RRM_CLI", str(exe))
    assert config.resolve_rrm_cli() == str(exe)


def test_resolve_uses_override_file_when_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("RRM_CLI", raising=False)
    monkeypatch.setattr(config, "WORKSPACE_ROOT", str(tmp_path))
    files = tmp_path / "files"
    files.mkdir()
    exe = tmp_path / "RRMTool_CLI.exe"
    exe.write_text("stub", encoding="utf-8")
    (files / "rrmtool_path.txt").write_text(str(exe) + "\n", encoding="utf-8")
    assert config.resolve_rrm_cli() == str(exe)


def test_resolve_falls_back_to_default_when_nothing_found(monkeypatch):
    monkeypatch.setattr(config, "_rrm_cli_candidates", lambda: [None, "/no/such/file"])
    assert config.resolve_rrm_cli() == config._RRM_CLI_DEFAULT
