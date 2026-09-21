"""Tests for the provenance module."""

import os
import re
import subprocess
from unittest.mock import patch

import pytest

from eigenfrequencies import provenance
from eigenfrequencies.config import ModalAnalysisConfig, ResonanceConfig


def _minimal_config() -> ModalAnalysisConfig:
    return ModalAnalysisConfig(resonance=ResonanceConfig(n_rpm=72.0))


class TestGenerateHappyPath:
    """Happy path: git is available and working, all env vars absent."""

    def test_returns_dict(self):
        assert isinstance(provenance.generate(_minimal_config()), dict)

    def test_config_snapshot_is_dict(self):
        result = provenance.generate(_minimal_config())
        assert isinstance(result["config_snapshot"], dict)

    def test_config_snapshot_has_expected_keys(self):
        snap = provenance.generate(_minimal_config())["config_snapshot"]
        assert "resonance" in snap
        assert "material" in snap
        assert "bc" in snap

    def test_git_commit_is_valid_hex(self):
        commit = provenance.generate(_minimal_config())["git_commit"]
        if commit is not None:
            assert len(commit) == 40
            assert re.fullmatch(r"[0-9a-f]{40}", commit)

    def test_git_dirty_is_bool(self):
        assert isinstance(provenance.generate(_minimal_config())["git_dirty"], bool)

    def test_package_version_is_string(self):
        version = provenance.generate(_minimal_config())["package_version"]
        assert isinstance(version, str)
        assert len(version) > 0

    def test_python_version_is_string(self):
        version = provenance.generate(_minimal_config())["python_version"]
        assert isinstance(version, str)
        assert len(version) > 0

    def test_timestamp_utc_looks_like_iso(self):
        ts = provenance.generate(_minimal_config())["timestamp_utc"]
        assert isinstance(ts, str)
        assert ts.endswith("Z")
        assert "T" in ts
        date_part, _ = ts.rstrip("Z").split("T", 1)
        assert len(date_part.split("-")) == 3

    def test_hostname_is_string(self):
        hostname = provenance.generate(_minimal_config())["hostname"]
        assert isinstance(hostname, str)
        assert len(hostname) > 0

    def test_slurm_job_id_null_when_absent(self):
        assert provenance.generate(_minimal_config())["slurm_job_id"] is None

    def test_container_image_null_when_absent(self):
        assert provenance.generate(_minimal_config())["container_image"] is None

    def test_all_keys_present(self):
        expected = {
            "config_snapshot",
            "git_commit",
            "git_dirty",
            "package_version",
            "python_version",
            "timestamp_utc",
            "hostname",
            "slurm_job_id",
            "container_image",
        }
        assert set(provenance.generate(_minimal_config()).keys()) == expected


class TestGenerateEnvOverrides:
    """SLURM_JOB_ID and PROVENANCE_CONTAINER env vars are captured."""

    def test_slurm_job_id_from_env(self):
        cfg = _minimal_config()
        with patch.dict(os.environ, {"SLURM_JOB_ID": "12345"}, clear=False):
            result = provenance.generate(cfg)
        assert result["slurm_job_id"] == "12345"

    def test_container_image_from_env(self):
        cfg = _minimal_config()
        with patch.dict(
            os.environ,
            {"PROVENANCE_CONTAINER": "atismer/dtoo-opensuse:stable"},
            clear=False,
        ):
            result = provenance.generate(cfg)
        assert result["container_image"] == "atismer/dtoo-opensuse:stable"


class TestGenerateNoGit:
    """No .git directory: git_commit=null, git_dirty=false, no crash."""

    def test_git_not_installed(self):
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            with pytest.warns(UserWarning, match="git not found"):
                result = provenance.generate(_minimal_config())
        assert result["git_commit"] is None
        assert result["git_dirty"] is False


class TestGenerateDirtyGit:
    """git status --porcelain returns non-empty: git_dirty=True."""

    def test_dirty_flag_true_when_modified(self):
        _real_run = subprocess.run

        def _fake_run(cmd, **kwargs):
            if "--show-toplevel" in cmd:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="/repo\n")
            if "HEAD" in cmd:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="a" * 40 + "\n"
                )
            if "--porcelain" in cmd:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=" M src/eigenfrequencies/some_file.py\n",
                )
            return _real_run(cmd, **kwargs)

        with patch.object(subprocess, "run", side_effect=_fake_run):
            result = provenance.generate(_minimal_config())

        assert result["git_dirty"] is True
        assert result["git_commit"] == "a" * 40
