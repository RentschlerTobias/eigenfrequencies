"""Provenance tracking for reproducible runs.

Captures metadata about every solve/validate/optimize run so results can be
traced back to the exact configuration, git state, and execution environment.
"""

import dataclasses
import datetime
import os
import platform
import socket
import subprocess
import warnings
from datetime import datetime as _dt, timezone as _tz


def _git_commit_and_dirty() -> tuple:
    """Return (git_commit: str | None, git_dirty: bool).

    Runs ``git rev-parse HEAD`` and ``git status --porcelain`` in the repo root.
    Gracefully handles missing .git, git not installed, and detached HEAD.
    Warns to stderr on any error; never crashes.
    """
    try:
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if repo_root.returncode != 0:
            warnings.warn(
                f"git rev-parse --show-toplevel failed (exit {repo_root.returncode}); "
                " provenance git_commit=null, git_dirty=false",
                stacklevel=2,
            )
            return None, False

        git_dir = repo_root.stdout.strip()
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=git_dir,
        )
        if head.returncode != 0:
            warnings.warn(
                f"git rev-parse HEAD failed (exit {head.returncode}); "
                "provenance git_commit=null",
                stacklevel=2,
            )
            return None, False

        commit = head.stdout.strip()

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=git_dir,
        )
        dirty = status.returncode == 0 and bool(status.stdout.strip())

        return commit, dirty

    except FileNotFoundError:
        warnings.warn(
            "git not found in PATH; provenance git_commit=null, git_dirty=false",
            stacklevel=2,
        )
        return None, False
    except Exception as exc:
        warnings.warn(
            f"git provenance probe failed: {exc}; provenance git_commit=null, git_dirty=false",
            stacklevel=2,
        )
        return None, False


def _package_version() -> str:
    """Return the installed eigenfrequencies version string."""
    try:
        from eigenfrequencies import version as _v

        return _v.__version__
    except Exception:
        pass

    try:
        import importlib.metadata

        return importlib.metadata.version("eigenfrequencies")
    except Exception:
        return "unknown"


def generate(config) -> dict:
    """Capture provenance metadata for a run.

    Args:
        config: A ``RunConfig`` (or any dataclass with ``dataclasses.asdict``).

    Returns:
        A dict with keys:
        - config_snapshot: dataclasses.asdict(config)
        - git_commit: str | None
        - git_dirty: bool
        - package_version: str
        - python_version: str
        - timestamp_utc: str (ISO 8601)
        - hostname: str
        - slurm_job_id: str | None  (from SLURM_JOB_ID env, null if absent)
        - container_image: str | None  (from PROVENANCE_CONTAINER env, null if absent)
    """
    git_commit, git_dirty = _git_commit_and_dirty()

    slurm_job_id = os.environ.get("SLURM_JOB_ID")
    container_image = os.environ.get("PROVENANCE_CONTAINER")

    return {
        "config_snapshot": dataclasses.asdict(config),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "package_version": _package_version(),
        "python_version": platform.python_version(),
        "timestamp_utc": _dt.now(_tz.utc).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "slurm_job_id": slurm_job_id,
        "container_image": container_image,
    }
