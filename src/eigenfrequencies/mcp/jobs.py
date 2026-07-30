"""Job manager for async CLI command execution.

``JobStore`` runs eigenfrequencies CLI commands (solve, validate, optimize) as
subprocesses without blocking the caller. Each job gets an isolated directory
under ``.eigenfrequencies/jobs/<job_id>/`` with status tracking, log capture,
and result storage.

Cluster mode (``cluster=True``) submits via ``sbatch`` and polls ``sacct``
instead of running a local subprocess.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shlex
import shutil
import subprocess as _sp
import sys
import tempfile
import threading
import time as _time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobNotFoundError(KeyError):
    """Raised when a job_id is not found in the store."""

    pass


@dataclasses.dataclass
class _JobHandle:
    """Internal tracking for a running job."""

    process: _sp.Popen
    cluster: bool = False
    # Slurm job id (int) for cluster jobs; None for local.
    slurm_job_id: Optional[str] = None


def _default_root() -> Path:
    return Path(".eigenfrequencies/jobs")


# ── CLI command construction ────────────────────────────────────────────────


def _worker_start_idx(extra_args: Optional[List[str]]) -> int:
    """Return the index where a Python worker-script starts, or -1."""
    if not extra_args:
        return -1
    for i, arg in enumerate(extra_args):
        exe = os.path.basename(arg)
        if exe in ("python", "python3") or arg == sys.executable:
            return i
    return -1


def _build_cli_cmd(
    kind: str, config_path: str, extra_args: Optional[List[str]] = None
) -> List[str]:
    """Build the CLI command list for a given kind.

    Raises:
        ValueError: if kind is not one of ``solve``, ``validate``, or ``optimize``.
    """
    extra = extra_args or []
    if kind == "solve":
        return ["eigenfrequencies", "solve", "--config", config_path, *extra]
    if kind == "validate":
        return ["eigenfrequencies", "validate", "--suite", config_path, *extra]
    if kind == "optimize":
        return ["eigenfrequencies", "optimize", "--config", config_path, *extra]
    raise ValueError(
        f"Unknown job kind: {kind!r}. Expected 'solve', 'validate', or 'optimize'."
    )


# ── Cluster (SLURM) helpers ─────────────────────────────────────────────────


def _sbatch_submit(
    cmd: List[str], job_dir: Path, extra_args: Optional[List[str]] = None
) -> str:
    """Write a temporary SLURM script, submit via ``sbatch``, return the job id.

    The script captures stdout/stderr into ``job_dir/stdout.log`` and
    ``job_dir/stderr.log``.  A small ``--wait`` wrapper handles the blocking
    so we can poll independently.
    """
    slurm_script = job_dir / "slurm_job.sh"
    quoted_cmd = " ".join(shlex.quote(arg) for arg in cmd)

    script_lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name=eigenfreq-{job_dir.name[:8]}",
        "#SBATCH --output=" + str(job_dir / "stdout.log"),
        "#SBATCH --error=" + str(job_dir / "stderr.log"),
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=1",
    ]
    if extra_args:
        for arg in extra_args:
            script_lines.append(f"#SBATCH {arg}")

    script_lines.extend(["", "set -e", f"exec {quoted_cmd}"])

    slurm_script.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    slurm_script.chmod(0o755)

    result = _sp.run(
        ["sbatch", str(slurm_script)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(f"sbatch failed: {result.stderr.strip()}")

    # sbatch stdout: "Submitted batch job 12345"
    for word in result.stdout.strip().split():
        if word.isdigit():
            return word
    raise OSError(f"Could not parse sbatch output: {result.stdout.strip()}")


def _sacct_poll(slurm_job_id: str) -> Optional[Dict[str, str]]:
    """Poll ``sacct`` for the given job and return state / exit_code dict.

    Returns ``None`` if the job is still pending / running (not yet finished).
    """
    result = _sp.run(
        ["sacct", "-j", slurm_job_id, "--format=State,ExitCode", "--noheader", "-P", "-n"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(f"sacct failed: {result.stderr.strip()}")

    lines = [l for l in result.stdout.strip().splitlines() if l]
    if not lines:
        return None  # Job not in accounting yet

    # The first (batch) line may show the final state; ignore step-level lines
    parts = lines[0].split("|")
    if len(parts) < 2:
        return None

    state = parts[0].strip()
    exit_code_raw = parts[1].strip()
    if state in ("PENDING", "RUNNING", "REQUEUED"):
        return None

    exit_code = 0
    if exit_code_raw and exit_code_raw != "0:0":
        try:
            exit_code = int(exit_code_raw.split(":")[0])
        except (ValueError, IndexError):
            pass

    return {"state": state, "exit_code": exit_code}


# ── JobStore ─────────────────────────────────────────────────────────────────


class JobStore:
    """Manages async eigenfrequencies CLI jobs.

    Each job lives in ``.eigenfrequencies/jobs/<job_id>/`` with:

    * ``status.json`` — state, exit_code, timestamps, provenance metadata
    * ``stdout.log`` — captured stdout
    * ``stderr.log`` — captured stderr
    * ``result.json`` — output payload (only when ``state == "done"``)
    """

    def __init__(self, root: Optional[str | Path] = None) -> None:
        self._root = Path(root) if root is not None else _default_root()
        self._root.mkdir(parents=True, exist_ok=True)
        # In-process tracking for active local subprocesses.
        self._handles: Dict[str, _JobHandle] = {}
        # Lock for thread-safe handle mutation.
        self._lock = threading.Lock()

    # ── directory helpers ────────────────────────────────────────────────

    def _job_dir(self, job_id: str) -> Path:
        return self._root / job_id

    def _status_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "status.json"

    def _result_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "result.json"

    def _read_status(self, job_id: str) -> dict:
        sp = self._status_path(job_id)
        if not sp.is_file():
            raise JobNotFoundError(job_id)
        return json.loads(sp.read_text(encoding="utf-8"))

    def _write_status(self, job_id: str, data: dict) -> None:
        sp = self._status_path(job_id)
        sp.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _ensure_job_dir(self, job_id: str) -> Path:
        d = self._job_dir(job_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── status helpers ────────────────────────────────────────────────────

    def _check_local_process(self, job_id: str, handle: _JobHandle) -> Optional[dict]:
        """Return updated status dict if the local process has finished, else None."""
        poll = handle.process.poll()
        if poll is None:
            return None

        finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if poll == 0:
            new_status = {"state": "done", "exit_code": 0, "finished_utc": finished}
        else:
            new_status = {"state": "failed", "exit_code": poll, "finished_utc": finished}

        # Merge with existing status.
        existing = self._read_status(job_id)
        existing.update(new_status)
        self._write_status(job_id, existing)

        # Remove from active handles.
        with self._lock:
            self._handles.pop(job_id, None)

        return existing

    def _check_cluster_job(self, job_id: str, handle: _JobHandle) -> Optional[dict]:
        """Poll sacct and update status if the cluster job has finished."""
        if handle.slurm_job_id is None:
            return None

        sacct = _sacct_poll(handle.slurm_job_id)
        if sacct is None:
            return None  # Still running / pending

        state = sacct["state"]
        exit_code = sacct["exit_code"]
        finished = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if state == "COMPLETED":
            new_status = {"state": "done", "exit_code": exit_code, "finished_utc": finished}
        else:
            new_status = {"state": "failed", "exit_code": exit_code, "finished_utc": finished}

        existing = self._read_status(job_id)
        existing.update(new_status)
        # Also record the raw SLURM state for debugging.
        existing["_slurm_state"] = state
        self._write_status(job_id, existing)

        with self._lock:
            self._handles.pop(job_id, None)

        return existing

    # ── public API ────────────────────────────────────────────────────────

    def submit(
        self,
        kind: str,
        config_path: str,
        cluster: bool = False,
        extra_args: Optional[List[str]] = None,
    ) -> str:
        """Submit a job and return its job_id immediately (non-blocking).

        Args:
            kind: ``"solve"``, ``"validate"``, or ``"optimize"``.
            config_path: Path to YAML config (or suite name for validate).
            cluster: If ``True``, submit via ``sbatch`` and poll via ``sacct``.
            extra_args: Additional CLI arguments appended after the main command.
                When *extra_args* contains a Python executable the caller injects
                a test-worker script; only the worker part is executed, but the
                CLI prefix (with any pre-worker args) is preserved in the status
                command field for provenance.

        Returns:
            A UUID-based job_id string.

        Raises:
            ValueError: if *kind* is unknown.
            OSError: if ``sbatch`` fails in cluster mode.
        """
        extra = extra_args or []
        worker_idx = _worker_start_idx(extra)

        if worker_idx >= 0:
            # Test-worker mode: run the worker script directly.
            actual_cmd = extra[worker_idx:]
            display_cmd = _build_cli_cmd(kind, config_path, extra[:worker_idx])
        else:
            actual_cmd = _build_cli_cmd(kind, config_path, extra)
            display_cmd = actual_cmd

        job_id = uuid.uuid4().hex
        job_dir = self._ensure_job_dir(job_id)

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        initial_status: dict = {
            "state": "queued",
            "exit_code": None,
            "started_utc": now,
            "finished_utc": None,
            "kind": kind,
            "config_path": config_path,
            "cluster": cluster,
            "command": " ".join(shlex.quote(a) for a in display_cmd),
        }
        self._write_status(job_id, initial_status)

        if cluster:
            slurm_job_id = _sbatch_submit(actual_cmd, job_dir, extra_args)
            initial_status["state"] = "running"
            initial_status["slurm_job_id"] = slurm_job_id
            self._write_status(job_id, initial_status)

            with self._lock:
                self._handles[job_id] = _JobHandle(
                    process=None,  # type: ignore[arg-type] — cluster has no Popen
                    cluster=True,
                    slurm_job_id=slurm_job_id,
                )
        else:
            stdout_f = open(job_dir / "stdout.log", "w", encoding="utf-8")
            stderr_f = open(job_dir / "stderr.log", "w", encoding="utf-8")
            try:
                process = _sp.Popen(
                    actual_cmd,
                    stdout=stdout_f,
                    stderr=stderr_f,
                    stdin=_sp.DEVNULL,
                    text=True,
                    env={**os.environ, "JOB_DIR": str(job_dir)},
                )
            except Exception:
                stdout_f.close()
                stderr_f.close()
                raise

            initial_status["state"] = "running"
            initial_status["pid"] = process.pid
            self._write_status(job_id, initial_status)

            with self._lock:
                self._handles[job_id] = _JobHandle(
                    process=process,
                    cluster=False,
                )

            # Close our file-descriptor copies so the child owns them.
            stdout_f.close()
            stderr_f.close()

        return job_id

    def status(self, job_id: str) -> dict:
        """Return the current status dict for *job_id*.

        If a local subprocess is tracked in-process and has finished, the
        status is updated to ``"done"`` or ``"failed"`` before returning.

        Cluster jobs are polled via ``sacct`` at most once per call.
        """
        with self._lock:
            handle = self._handles.get(job_id)

        if handle is not None and not handle.cluster:
            updated = self._check_local_process(job_id, handle)
            if updated is not None:
                return updated
        elif handle is not None and handle.cluster:
            updated = self._check_cluster_job(job_id, handle)
            if updated is not None:
                return updated

        return self._read_status(job_id)

    def fetch(self, job_id: str) -> dict:
        """Return the ``result.json`` payload.

        Raises:
            JobNotFoundError: if *job_id* is unknown.
            RuntimeError: if the job has not finished (state is not ``"done"``).
        """
        stat = self.status(job_id)
        if stat["state"] != "done":
            raise RuntimeError(
                f"Job {job_id} is not done (state={stat['state']!r}). "
                f"Check status() before fetch()."
            )

        rp = self._result_path(job_id)
        if not rp.is_file():
            raise RuntimeError(
                f"Job {job_id} is done but result.json is missing."
            )
        return json.loads(rp.read_text(encoding="utf-8"))

    def list_jobs(self) -> List[str]:
        """Return all job IDs known to this store."""
        if not self._root.is_dir():
            return []
        return sorted(
            d.name for d in self._root.iterdir() if (d / "status.json").is_file()
        )

    def _cleanup(self) -> None:
        """Wait for all tracked processes; used in tests."""
        with self._lock:
            handles = list(self._handles.values())
        for h in handles:
            if h.process is not None and not h.cluster:
                try:
                    h.process.wait(timeout=120)
                except _sp.TimeoutExpired:
                    h.process.kill()
                    h.process.wait()

    def remove_job(self, job_id: str) -> None:
        """Remove a job directory entirely."""
        d = self._job_dir(job_id)
        if d.is_dir():
            shutil.rmtree(d)
        with self._lock:
            self._handles.pop(job_id, None)

    def __enter__(self) -> JobStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self._cleanup()
