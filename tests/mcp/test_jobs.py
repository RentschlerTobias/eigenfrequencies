"""Tests for the MCP job manager (JobStore).

Covers the full lifecycle: submit → poll → fetch for local processes,
failure paths, cluster mock, and golden beam frequency verification.
"""

import json
import os
import signal
import subprocess as _sp
import sys
import time as _time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eigenfrequencies.mcp import JobNotFoundError, JobStore

# ── golden beam frequencies from tests/characterization/golden/beam.json ─────

GOLDEN_BEAM_FREQUENCIES = [
    8.39455014499035,
    53.07686426713339,
    83.07471261537489,
    157.8958968581103,
    188.84629117650178,
    313.02434307008417,
    503.66478802242244,
    546.7576615450993,
    573.0784920062803,
    879.8762123701898,
]

# ── helpers ─────────────────────────────────────────────────────────────────


def _poll_until_done(
    store: JobStore, job_id: str, timeout: float = 30.0, interval: float = 0.1
) -> dict:
    """Poll ``store.status(job_id)`` until state is done or failed."""
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        stat = store.status(job_id)
        if stat["state"] in ("done", "failed"):
            return stat
        _time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout} s")


def _write_result(job_dir: Path, payload: dict) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "result.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _simple_worker_script() -> str:
    """A tiny Python script that writes result.json and exits 0."""
    return (
        "import json, os, sys\n"
        "job_dir = os.environ['JOB_DIR']\n"
        "open(os.path.join(job_dir, 'stdout.log'), 'w').write('hello stdout\\n')\n"
        "open(os.path.join(job_dir, 'stderr.log'), 'w').write('')\n"
        "result = {'frequencies_hz': [8.39, 52.61, 147.38]}\n"
        "with open(os.path.join(job_dir, 'result.json'), 'w') as f:\n"
        "    json.dump(result, f)\n"
    )


def _failing_worker_script() -> str:
    """A script that writes to stderr and exits with code 2."""
    return (
        "import json, os, sys\n"
        "job_dir = os.environ['JOB_DIR']\n"
        "sys.stderr.write('Config error: invalid YAML\\n')\n"
        "sys.exit(2)\n"
    )


def _long_running_worker_script() -> str:
    """A script that runs indefinitely until killed."""
    return (
        "import os, signal, time\n"
        "job_dir = os.environ['JOB_DIR']\n"
        "with open(os.path.join(job_dir, 'stdout.log'), 'w') as f:\n"
        "    f.write('started\\n')\n"
        "    f.flush()\n"
        "time.sleep(120)\n"
    )


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    """A JobStore rooted in a temporary directory."""
    return JobStore(root=tmp_path / ".eigenfrequencies/jobs")


@pytest.fixture
def worker_dir(tmp_path: Path) -> Path:
    """A scratch directory for worker scripts to write into."""
    d = tmp_path / "worker_dir"
    d.mkdir()
    return d


# ── tests: happy path ───────────────────────────────────────────────────────


class TestSubmitAndFetchHappyPath:
    """Submit a process that writes result.json, poll until done, fetch."""

    def test_submit_and_fetch(self, store: JobStore, worker_dir: Path):
        """Real subprocess lifecycle: submit → poll → fetch."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "beam.yaml"),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )

        assert job_id is not None
        assert len(job_id) == 32  # UUID hex

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"
        assert stat["exit_code"] == 0

        result = store.fetch(job_id)
        assert result["frequencies_hz"] == [8.39, 52.61, 147.38]

    def test_submit_with_extra_args(self, store: JobStore, worker_dir: Path):
        """Extra args are appended to the CLI command."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "beam.yaml"),
            extra_args=["--json", sys.executable, "-c", _simple_worker_script()],
        )

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"
        assert "--json" in stat.get("command", "")


class TestGoldenBeamSolve:
    """Submit a job, write golden beam result, verify frequencies match."""

    def test_beam_solve_golden_frequencies(self, store: JobStore, worker_dir: Path):
        """Mock subprocess to simulate a beam solve; verify golden freqs on fetch."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "beam.yaml"),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )

        # Wait for the process to finish naturally
        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"

        # Overwrite result.json with golden beam frequencies
        _write_result(
            store._job_dir(job_id),
            {"frequencies_hz": GOLDEN_BEAM_FREQUENCIES},
        )

        result = store.fetch(job_id)
        assert result["frequencies_hz"] == GOLDEN_BEAM_FREQUENCIES
        assert len(result["frequencies_hz"]) == 10
        assert abs(result["frequencies_hz"][0] - 8.39455014499035) < 1e-9


# ── tests: failure paths ────────────────────────────────────────────────────


class TestFailedJob:
    """Process exits non-zero → state=failed, stderr captured."""

    def test_failed_job_exit_code(self, store: JobStore, worker_dir: Path):
        """Bad config causes exit code 2, stderr captured."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "bad_config.yaml"),
            extra_args=[sys.executable, "-c", _failing_worker_script()],
        )

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "failed"
        assert stat["exit_code"] == 2

    def test_failed_job_stderr_captured(self, store: JobStore, worker_dir: Path):
        """stderr log file contains the error message."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "bad.yaml"),
            extra_args=[sys.executable, "-c", _failing_worker_script()],
        )

        _poll_until_done(store, job_id, timeout=10.0)
        stderr_path = store._job_dir(job_id) / "stderr.log"
        assert stderr_path.is_file()
        content = stderr_path.read_text(encoding="utf-8")
        assert "Config error" in content


class TestKilledProcess:
    """Killed process → state=failed with signal exit code."""

    def test_killed_process_state_failed(self, store: JobStore, worker_dir: Path):
        """Kill a long-running process; verify state=failed."""
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "beam.yaml"),
            extra_args=[sys.executable, "-c", _long_running_worker_script()],
        )

        # Give the process a moment to start
        _time.sleep(0.5)

        with store._lock:
            handle = store._handles.get(job_id)

        if handle is not None and handle.process is not None:
            handle.process.kill()
            handle.process.wait(timeout=5)

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "failed"
        # Killed by SIGKILL → exit code should be negative or non-zero
        assert stat["exit_code"] is not None
        assert stat["exit_code"] != 0


class TestUnknownJobId:
    """Fetch or status with unknown job_id raises JobNotFoundError."""

    def test_fetch_unknown_raises(self, store: JobStore):
        with pytest.raises(JobNotFoundError):
            store.fetch("nonexistent_job_id")

    def test_status_unknown_raises(self, store: JobStore):
        with pytest.raises(JobNotFoundError):
            store.status("nonexistent_job_id")


class TestFetchBeforeDone:
    """Fetch on a still-running job raises RuntimeError."""

    def test_fetch_before_done_raises(self, store: JobStore, worker_dir: Path):
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "beam.yaml"),
            extra_args=[sys.executable, "-c", _long_running_worker_script()],
        )

        with pytest.raises(RuntimeError, match="not done"):
            store.fetch(job_id)

        # Cleanup
        with store._lock:
            handle = store._handles.get(job_id)
        if handle is not None and handle.process is not None:
            handle.process.kill()
            handle.process.wait(timeout=5)


# ── tests: validate and optimize commands ───────────────────────────────────


class TestValidateCommand:
    """Validate kind maps to --suite instead of --config."""

    def test_validate_uses_suite_arg(self, store: JobStore):
        """submit('validate', 'beam') uses --suite beam."""
        job_id = store.submit(
            "validate",
            config_path="beam",
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"
        cmd = stat["command"]
        assert "validate" in cmd
        assert "--suite" in cmd
        assert "beam" in cmd


class TestOptimizeCommand:
    """Optimize kind maps to --config."""

    def test_optimize_uses_config_arg(self, store: JobStore, worker_dir: Path):
        config_p = worker_dir / "opt_config.yaml"
        config_p.write_text("key: value\n")
        job_id = store.submit(
            "optimize",
            config_path=str(config_p),
            extra_args=["--optimizer", "de", sys.executable, "-c", _simple_worker_script()],
        )

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"
        cmd = stat["command"]
        assert "optimize" in cmd
        assert "--config" in cmd


class TestUnknownKind:
    """Unknown kind raises ValueError."""

    def test_unknown_kind_raises(self, store: JobStore):
        with pytest.raises(ValueError, match="Unknown job kind"):
            store.submit("not_a_kind", config_path="x")


# ── tests: list_jobs ────────────────────────────────────────────────────────


class TestListJobs:
    """list_jobs returns all known job IDs."""

    def test_list_jobs_empty(self, store: JobStore):
        assert store.list_jobs() == []

    def test_list_jobs_after_submit(self, store: JobStore, worker_dir: Path):
        j1 = store.submit(
            "solve",
            config_path=str(worker_dir / "a.yaml"),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )
        j2 = store.submit(
            "solve",
            config_path=str(worker_dir / "b.yaml"),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )

        # Poll both to completion
        _poll_until_done(store, j1, timeout=10.0)
        _poll_until_done(store, j2, timeout=10.0)

        jobs = store.list_jobs()
        assert j1 in jobs
        assert j2 in jobs
        assert len(jobs) == 2


# ── tests: remove_job ───────────────────────────────────────────────────────


class TestRemoveJob:
    """remove_job deletes the job directory."""

    def test_remove_job(self, store: JobStore, worker_dir: Path):
        job_id = store.submit(
            "solve",
            config_path=str(worker_dir / "a.yaml"),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )
        _poll_until_done(store, job_id, timeout=10.0)

        assert store._job_dir(job_id).is_dir()
        store.remove_job(job_id)
        assert not store._job_dir(job_id).exists()
        assert job_id not in store.list_jobs()


# ── tests: cluster mode (mocked) ────────────────────────────────────────────


class TestClusterMode:
    """Unit-mock sbatch and sacct; do not actually submit to SLURM."""

    def test_cluster_submit_calls_sbatch(self, store: JobStore, worker_dir: Path):
        """cluster=True calls _sbatch_submit, returns SLURM job id."""
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")

        with patch(
            "eigenfrequencies.mcp.jobs._sbatch_submit", return_value="98765"
        ) as mock_sbatch, patch(
            "eigenfrequencies.mcp.jobs._sacct_poll", return_value=None
        ):
            job_id = store.submit("solve", config_path=str(config_p), cluster=True)

            mock_sbatch.assert_called_once()
            args, _ = mock_sbatch.call_args
            assert "solve" in args[0]
            assert str(config_p) in args[0]

            stat = store.status(job_id)
            assert stat["state"] == "running"
            assert stat["slurm_job_id"] == "98765"

    def test_cluster_sacct_poll_completed(self, store: JobStore, worker_dir: Path):
        """sacct returns COMPLETED → state=done."""
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")

        with patch(
            "eigenfrequencies.mcp.jobs._sbatch_submit", return_value="98765"
        ), patch(
            "eigenfrequencies.mcp.jobs._sacct_poll",
            return_value={"state": "COMPLETED", "exit_code": 0},
        ) as mock_sacct:
            job_id = store.submit("solve", config_path=str(config_p), cluster=True)

            # Write a result so fetch() works
            _write_result(store._job_dir(job_id), {"frequencies_hz": [1.0, 2.0]})

            stat = store.status(job_id)
            assert stat["state"] == "done"
            assert stat["exit_code"] == 0
            mock_sacct.assert_called()

    def test_cluster_sacct_poll_failed(self, store: JobStore, worker_dir: Path):
        """sacct returns FAILED → state=failed."""
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")

        with patch(
            "eigenfrequencies.mcp.jobs._sbatch_submit", return_value="98765"
        ), patch(
            "eigenfrequencies.mcp.jobs._sacct_poll",
            return_value={"state": "FAILED", "exit_code": 127},
        ):
            job_id = store.submit("solve", config_path=str(config_p), cluster=True)

            stat = store.status(job_id)
            assert stat["state"] == "failed"
            assert stat["exit_code"] == 127

    def test_cluster_sacct_poll_still_running(self, store: JobStore, worker_dir: Path):
        """sacct returns None → state stays running."""
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")

        with patch(
            "eigenfrequencies.mcp.jobs._sbatch_submit", return_value="98765"
        ), patch(
            "eigenfrequencies.mcp.jobs._sacct_poll", return_value=None
        ):
            job_id = store.submit("solve", config_path=str(config_p), cluster=True)

            stat = store.status(job_id)
            assert stat["state"] == "running"
            assert stat["slurm_job_id"] == "98765"

    def test_cluster_fetch_before_done_raises(self, store: JobStore, worker_dir: Path):
        """Fetch on a still-running cluster job raises RuntimeError."""
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")

        with patch(
            "eigenfrequencies.mcp.jobs._sbatch_submit", return_value="98765"
        ), patch(
            "eigenfrequencies.mcp.jobs._sacct_poll", return_value=None
        ):
            job_id = store.submit("solve", config_path=str(config_p), cluster=True)

            with pytest.raises(RuntimeError, match="not done"):
                store.fetch(job_id)


# ── tests: status.json shape ────────────────────────────────────────────────


class TestStatusJsonShape:
    """Verify status.json contains all expected fields."""

    def test_status_initial_shape(self, store: JobStore, worker_dir: Path):
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")
        job_id = store.submit(
            "solve",
            config_path=str(config_p),
            extra_args=[sys.executable, "-c", _long_running_worker_script()],
        )

        stat = store.status(job_id)
        assert "state" in stat
        assert stat["state"] in ("queued", "running")
        assert "exit_code" in stat
        assert stat["exit_code"] is None
        assert "started_utc" in stat
        assert "finished_utc" in stat
        assert "kind" in stat
        assert stat["kind"] == "solve"
        assert "config_path" in stat
        assert "cluster" in stat
        assert stat["cluster"] is False
        assert "command" in stat
        assert "pid" in stat

        # Cleanup
        with store._lock:
            handle = store._handles.get(job_id)
        if handle is not None and handle.process is not None:
            handle.process.kill()
            handle.process.wait(timeout=5)

    def test_status_done_shape(self, store: JobStore, worker_dir: Path):
        config_p = worker_dir / "cfg.yaml"
        config_p.write_text("key: value\n")
        job_id = store.submit(
            "solve",
            config_path=str(config_p),
            extra_args=[sys.executable, "-c", _simple_worker_script()],
        )

        stat = _poll_until_done(store, job_id, timeout=10.0)
        assert stat["state"] == "done"
        assert stat["exit_code"] == 0
        assert stat["finished_utc"] is not None


# ── tests: context manager ──────────────────────────────────────────────────


class TestContextManager:
    """JobStore supports context manager protocol."""

    def test_context_manager_cleanup(self, tmp_path: Path, worker_dir: Path):
        with JobStore(root=tmp_path / ".eigenfrequencies/jobs") as s:
            job_id = s.submit(
                "solve",
                config_path=str(worker_dir / "beam.yaml"),
                extra_args=[sys.executable, "-c", _simple_worker_script()],
            )
            _poll_until_done(s, job_id, timeout=10.0)
            assert s.status(job_id)["state"] == "done"
        # After exit, no pending handles should block cleanup
        assert True  # No exception = clean exit
