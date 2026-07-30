"""Pyro5 evaluation worker for cluster-distributed eigenfrequency optimisation.

Each SLURM task runs one instance of this worker:

    eigenfrequencies cluster worker <id> --uri-dir /pfs/.../uris [--config cfg.yaml]

The worker:
  1. Starts a Pyro5 daemon on the local hostname.
  2. Registers an ``Evaluator`` that runs dtOO + FEniCSx + penalty per call.
  3. Writes its Pyro5 URI to ``uri_dir/worker_<id>.uri`` on the shared filesystem.
  4. Enters ``daemon.requestLoop()`` — blocks until SLURM kills the job.

The coordinator (``eigenfrequencies optimize ... --evaluator pyro5``) discovers
workers by polling the URI directory via ``Pyro5Pool``.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

FAIL_PENALTY = 1e6


def run_worker(
    worker_id: int,
    uri_dir: str,
    config_path: str | None = None,
) -> None:
    """Start the Pyro5 worker daemon and block until killed.

    Args:
        worker_id: unique integer per SLURM task (passed from CLI).
        uri_dir:   shared-filesystem directory where the URI file is written.
        config_path: path to YAML RunConfig (optional; falls back to env-based
                     OptimizationConfig / ObjectiveConfig defaults).
    """
    import Pyro5.api
    import Pyro5.server

    from eigenfrequencies.adapters.cluster.runner import run_dtoo, run_fenicsx

    if config_path is not None:
        from eigenfrequencies.config_yaml import load_config

        run_cfg = load_config(Path(config_path))
        opt_cfg = run_cfg.optimization
        obj_cfg = run_cfg.objective
    else:
        from eigenfrequencies.config import ObjectiveConfig, OptimizationConfig

        opt_cfg = OptimizationConfig()
        obj_cfg = ObjectiveConfig()

    from eigenfrequencies.penalty.objective import resonance_term

    @Pyro5.api.expose
    class Evaluator:
        def evaluate(self, x_list: list, labels: list) -> tuple:
            """Evaluate one design vector.

            Args:
                x_list: list of float parameter values.
                labels: list of parameter name strings (same order as x_list).

            Returns:
                (objective_float, breakdown_dict)
            """
            design = {lab: float(v) for lab, v in zip(labels, x_list)}

            if not run_dtoo(design, worker_id):
                return float(FAIL_PENALTY), {
                    "error": "dtoo_build_failed",
                    "worker_id": worker_id,
                }

            result = run_fenicsx(worker_id)
            if not result.get("ok"):
                return float(FAIL_PENALTY), {
                    "error": "modal_solve_failed",
                    "worker_id": worker_id,
                }

            freqs = result["frequencies_hz"]
            f_res = resonance_term(freqs, opt_cfg, obj_cfg)
            return float(f_res), {
                "total": float(f_res),
                "f_resonance": float(f_res),
                "freqs": freqs,
                "worker_id": worker_id,
            }

    host = socket.gethostname()
    Pyro5.config.HOST = host
    daemon = Pyro5.server.Daemon(host=host)
    uri = daemon.register(Evaluator, f"eigenfreq.worker.{worker_id}")

    os.makedirs(uri_dir, exist_ok=True)
    uri_file = os.path.join(uri_dir, f"worker_{worker_id}.uri")
    with open(uri_file, "w") as fh:
        fh.write(str(uri))

    print(
        f"[worker {worker_id}] ready on {host} — URI written to {uri_file}",
        flush=True,
    )
    daemon.requestLoop()
