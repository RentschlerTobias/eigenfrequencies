"""Cluster evaluation runner — dtOO (native) + FEniCSx (enroot container).

Ported from turbine_runner/legacy/optimize.py:_run_dtoo / _run_fenicsx.
Configured entirely via environment variables so SLURM submit scripts can
override without touching Python code.

Environment variables
---------------------
EIGENFREQUENCIES_REPO   repo root (auto-detected from this file's location if unset)
FENICSX_CONTAINER       enroot container name  (default: pyxis_fenicsx)
DTOO_CASE_DIR           dtOO case directory    (default: ~/dtOO/build/test/tistos)
DTOO_EXPORT_SCRIPT      path to dtoo_export.py (default: $REPO/turbine_runner/dtoo_export.py)
FENICSX_EVAL_SCRIPT     path to evaluate.py    (default: $REPO/turbine_runner/evaluate.py)
TMPDIR                  worker scratch root    (default: /tmp)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(os.environ.get(
        "EIGENFREQUENCIES_REPO",
        str(Path(__file__).parents[4]),  # src/eigenfrequencies/adapters/cluster/ -> repo root
    ))


def worker_dir(worker_id: int) -> str:
    tmpdir = os.environ.get("TMPDIR", "/tmp")
    return os.path.join(tmpdir, f"worker_{worker_id}")


def run_dtoo(design: dict, worker_id: int = 0) -> bool:
    """Build runner.msh via dtOO (native, host-side).

    Writes design.json to the worker scratch dir, invokes dtoo_export.py via
    ``bash -lc`` (so ~/pe is sourced and LD_LIBRARY_PATH is set), and checks
    that runner.msh was produced.

    Returns True on success, False on failure (logs to dtoo.log in worker dir).
    """
    repo = _repo_root()
    wdir = worker_dir(worker_id)
    os.makedirs(wdir, exist_ok=True)

    design_json = os.path.join(wdir, "design.json")
    msh = os.path.join(wdir, "runner.msh")

    with open(design_json, "w") as fh:
        json.dump(design, fh)
    if os.path.exists(msh):
        os.remove(msh)

    export_script = os.environ.get(
        "DTOO_EXPORT_SCRIPT",
        str(repo / "turbine_runner" / "dtoo_export.py"),
    )
    dtoo_case = os.environ.get("DTOO_CASE_DIR", "~/dtOO/build/test/tistos")

    cmd = [
        "bash", "-lc",
        f"source ~/pe && "
        f"export LD_LIBRARY_PATH=~/dtOO/install/lib:~/dtOO/install/lib64:$LD_LIBRARY_PATH && "
        f"export DTOO_CASE_DIR={dtoo_case} && "
        f"export DTOO_OUTPUT_MSH={msh} && "
        f"export DTOO_DESIGN_JSON={design_json} && "
        f"python3 {export_script}",
    ]
    log_path = os.path.join(wdir, "dtoo.log")
    with open(log_path, "w") as log_fh:
        res = subprocess.run(cmd, stdout=log_fh, stderr=subprocess.STDOUT)

    if res.returncode != 0 or not os.path.exists(msh):
        with open(log_path) as log_fh:
            tail = log_fh.read()[-8000:]
        print(f"[runner] dtOO FAILED (worker {worker_id}):\n{tail}", file=sys.stderr, flush=True)
        return False
    return True


def run_fenicsx(worker_id: int = 0) -> dict:
    """Run evaluate.py inside the enroot container, return parsed RESULT_JSON.

    Mounts the repo at /workspace and the worker scratch dir at /worker_data.
    Sets HOME/DOLFINX_CACHE_DIR/XDG_RUNTIME_DIR/TMPDIR to /tmp inside the
    container so PMIx/MPI does not fall back to /run/user/$UID (unwritable in
    batch context).

    Returns dict with keys ``frequencies_hz`` (list[float]) and ``ok`` (bool).
    """
    repo = _repo_root()
    wdir = worker_dir(worker_id)

    container = os.environ.get("FENICSX_CONTAINER", "pyxis_fenicsx")
    eval_script = os.environ.get(
        "FENICSX_EVAL_SCRIPT",
        "/workspace/turbine_runner/evaluate.py",
    )

    cmd = [
        "enroot", "start",
        "-m", f"{repo}:/workspace",
        "-m", f"{wdir}:/worker_data",
        container,
        "bash", "-c",
        "export HOME=/tmp; export DOLFINX_CACHE_DIR=/tmp; "
        "export XDG_RUNTIME_DIR=/tmp; export TMPDIR=/tmp; "
        f"python3 {eval_script} /worker_data/runner.msh",
    ]

    log_path = os.path.join(wdir, "fenicsx.log")
    env = os.environ.copy()
    scratch = os.environ.get("TMPDIR", "/tmp")
    enroot_tmp = os.path.join(scratch, "enroot_tmp", f"worker_{worker_id}")
    os.makedirs(enroot_tmp, exist_ok=True)
    env["ENROOT_TEMP_PATH"] = enroot_tmp

    with open(log_path, "w") as log_fh:
        subprocess.run(cmd, stdout=log_fh, stderr=subprocess.STDOUT, env=env)

    with open(log_path) as log_fh:
        lines = log_fh.read().splitlines()

    for line in reversed(lines):
        if line.startswith("RESULT_JSON "):
            return json.loads(line[len("RESULT_JSON "):])

    print(
        f"[runner] FEniCSx FAILED (worker {worker_id}):\n{lines[-40:]}",
        file=sys.stderr,
        flush=True,
    )
    return {"frequencies_hz": [], "ok": False}
