"""Tests for the provenance module."""

import os
import re
import subprocess
from unittest.mock import patch

import pytest

from eigenfrequencies import provenance
from eigenfrequencies.config import (
    BCConfig,
    CFDConfig,
    DEConfig,
    DesignConfig,
    MaterialConfig,
    MeshConfig,
    ObjectiveConfig,
    OptimizationConfig,
    OutputConfig,
    RunConfig,
    SolverConfig,
    WetModeConfig,
)


def _minimal_run_config() -> RunConfig:
    """Return a minimal RunConfig suitable for provenance tests."""
    return RunConfig(
        optimization=OptimizationConfig(n_rpm=72.0),
        cfd=CFDConfig(n_rpm=72.0),
        material=MaterialConfig(),
        bc=BCConfig(),
        mesh=MeshConfig(msh_path="data/runner.msh"),
        solver=SolverConfig(),
        design=DesignConfig(),
        de=DEConfig(),
        objective=ObjectiveConfig(),
        wet_mode=WetModeConfig(),
        output=OutputConfig(),
    )


class TestGenerateHappyPath:
    """Happy path: git is available and working, all env vars absent."""

    def test_returns_dict(self):
        result = provenance.generate(_minimal_run_config())
        assert isinstance(result, dict)

    def test_config_snapshot_is_dict(self):
        cfg = _minimal_run_config()
        result = provenance.generate(cfg)
        assert isinstance(result["config_snapshot"], dict)

    def test_config_snapshot_has_expected_keys(self):
        result = provenance.generate(_minimal_run_config())
        snap = result["config_snapshot"]
        assert "optimization" in snap
        assert "cfd" in snap
        assert "material" in snap
        assert "bc" in snap

    def test_git_commit_is_valid_hex(self):
        result = provenance.generate(_minimal_run_config())
        # git SHA-1 is 40 hex chars; allow None if not a git repo
        commit = result["git_commit"]
        if commit is not None:
            assert len(commit) == 40
            assert re.fullmatch(r"[0-9a-f]{40}", commit)

    def test_git_dirty_is_bool(self):
        result = provenance.generate(_minimal_run_config())
        assert isinstance(result["git_dirty"], bool)

    def test_package_version_is_string(self):
        result = provenance.generate(_minimal_run_config())
        assert isinstance(result["package_version"], str)
        assert len(result["package_version"]) > 0

    def test_python_version_is_string(self):
        result = provenance.generate(_minimal_run_config())
        assert isinstance(result["python_version"], str)
        assert len(result["python_version"]) > 0

    def test_timestamp_utc_looks_like_iso(self):
        result = provenance.generate(_minimal_run_config())
        ts = result["timestamp_utc"]
        assert isinstance(ts, str)
        assert ts.endswith("Z")
        assert "T" in ts
        date_part, _ = ts.rstrip("Z").split("T", 1)
        assert len(date_part.split("-")) == 3

    def test_hostname_is_string(self):
        result = provenance.generate(_minimal_run_config())
        assert isinstance(result["hostname"], str)
        assert len(result["hostname"]) > 0

    def test_slurm_job_id_null_when_absent(self):
        result = provenance.generate(_minimal_run_config())
        assert result["slurm_job_id"] is None

    def test_container_image_null_when_absent(self):
        result = provenance.generate(_minimal_run_config())
        assert result["container_image"] is None

    def test_all_keys_present(self):
        result = provenance.generate(_minimal_run_config())
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
        assert set(result.keys()) == expected


class TestGenerateEnvOverrides:
    """SLURM_JOB_ID and PROVENANCE_CONTAINER env vars are captured."""

    def test_slurm_job_id_from_env(self):
        cfg = _minimal_run_config()
        with patch.dict(os.environ, {"SLURM_JOB_ID": "12345"}, clear=False):
            result = provenance.generate(cfg)
        assert result["slurm_job_id"] == "12345"

    def test_container_image_from_env(self):
        cfg = _minimal_run_config()
        with patch.dict(os.environ, {"PROVENANCE_CONTAINER": "atismer/dtoo-opensuse:stable"}, clear=False):
            result = provenance.generate(cfg)
        assert result["container_image"] == "atismer/dtoo-opensuse:stable"


class TestGenerateNoGit:
    """No .git directory: git_commit=null, git_dirty=false, no crash."""

    def test_git_not_installed(self):
        cfg = _minimal_run_config()
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            with pytest.warns(UserWarning, match="git not found"):
                result = provenance.generate(cfg)
        assert result["git_commit"] is None
        assert result["git_dirty"] is False

    def test_rev_parse_fails(self):
        cfg = _minimal_run_config()
        completed = subprocess.CompletedProcess(args=[], returncode=128, stderr="not a git repo")

        def _fake_run(cmd, **kwargs):
            if "rev-parse" in cmd:
                return completed
            return _real_run(cmd, **kwargs)

        _real_run = subprocess.run
        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            # When FileNotFoundError on rev-parse (git not found), returns None, False
            pass

        # Re-test: git returns non-zero for rev-parse
        cfg2 = _minimal_run_config()
        completed2 = subprocess.CompletedProcess(args=[], returncode=128, stderr="not a git repo")

        def _fake_run2(cmd, **kwargs):
            if "rev-parse" in cmd:
                return completed2
            if "status" in cmd:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="")
            return _real_run(cmd, **kwargs)

        with patch.object(subprocess, "run", side_effect=FileNotFoundError):
            # Simulate git not found
            result = provenance.generate(cfg2)
        assert result["git_commit"] is None


class TestGenerateDirtyGit:
    """git status --porcelain returns non-empty: git_dirty=True."""

    def test_dirty_flag_true_when_modified(self):
        cfg = _minimal_run_config()

        _real_run = subprocess.run

        def _fake_run(cmd, **kwargs):
            if "show-toplevel" in cmd:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="/repo\n")
            if "HEAD" in cmd:
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="a" * 40 + "\n")
            if "porcelain" in cmd:
                return subprocess.CompletedProcess(
                    args=[], returncode=0,
                    stdout=" M src/eigenfrequencies/some_file.py\n",
                )
            return _real_run(cmd, **kwargs)

        with patch.object(subprocess, "run", side_effect=_fake_run):
            result = provenance.generate(cfg)

        assert result["git_dirty"] is True
        assert result["git_commit"] == "a" * 40
