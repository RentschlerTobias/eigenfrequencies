#!/usr/bin/env python3
"""Pyro5 server for DE worker evaluation.

Starts once, registers with Name Server, waits for RPC calls.
Each call evaluates one design vector (dtOO build + FEniCSx + optional CFD).
"""

import sys
import os
import json
import socket

import Pyro5.api
# Pyro5.config is implicitly available after Pyro5.api import

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from config import OptimizationConfig, ObjectiveConfig, CFDConfig
from objective import combined_objective, resonance_term, cfd_scalar
from optimize import _run_dtoo, _run_fenicsx, _run_cfd, DTOO_FAIL_PENALTY

host = socket.gethostname()
worker_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0

# A2 discovery: no Name Server. Each worker writes its own Pyro5 URI to a file
# on the shared filesystem; the client reads them. This bypasses the NS
# broadcast / hostname discovery that fails across bwUniCluster nodes.
DEFAULT_URI_DIR = os.path.join(os.path.dirname(HERE), "server_logs", "uris")
URI_DIR = os.environ.get("DE_URI_DIR", DEFAULT_URI_DIR)

# Bind and advertise by the FQDN of this node, as de_framework/server.py does.
# de_framework proves that cross-node RPC to an FQDN resolves fine — only NS
# *discovery* was broken, which A2 removes entirely.
Pyro5.config.HOST = host

CFD_CASE_DIR = os.environ.get("CFD_CASE_DIR", "")


@Pyro5.api.expose
class Evaluator(object):
    def evaluate(self, x_list, labels):
        """Evaluate a single design vector.

        Branching on ObjectiveConfig.eval_mode (env EVAL_MODE):
          - "combined"      : dtOO + FEniCSx + CFD, objective = cfd + w_res*resonance
          - "cfd_only"      : dtOO + CFD only, objective = cfd_scalar
          - "resonance_only": dtOO + FEniCSx only, objective = resonance_term

        Returns (objective_float, breakdown_dict).
        """
        x = {lab: float(v) for lab, v in zip(labels, x_list)}

        obj_cfg = ObjectiveConfig()
        opt_cfg = OptimizationConfig()
        cfd_cfg = CFDConfig()
        eval_mode = obj_cfg.eval_mode

        # CFD runs in "combined" and "cfd_only" modes. Legacy CFD_ENABLED=0 env
        # forces "resonance_only" behavior regardless of eval_mode setting.
        cfd_enabled_env = os.environ.get("CFD_ENABLED", "1") == "1"
        run_cfd = cfd_enabled_env and eval_mode in ("combined", "cfd_only")
        run_modal = eval_mode in ("combined", "resonance_only")

        # ── dtOO build (runner.msh) — needed whenever modal analysis runs ──
        if run_modal:
            if not _run_dtoo(x, worker_id=worker_id):
                return float(DTOO_FAIL_PENALTY), {
                    "error": "dtoo_build_failed",
                    "worker_id": worker_id,
                    "eval_mode": eval_mode,
                }

        # ── Modal analysis (FEniCSx eigenfrequencies) ──
        freqs = None
        if run_modal:
            fre = _run_fenicsx(worker_id=worker_id)
            if not fre.get("ok"):
                return float(DTOO_FAIL_PENALTY), {
                    "error": "modal_solve_failed",
                    "worker_id": worker_id,
                    "eval_mode": eval_mode,
                }
            freqs = fre["frequencies_hz"]

        # ── CFD (OpenFOAM simpleFoam) ──
        cfd = None
        if run_cfd:
            case_dir = _run_cfd(x, worker_id=worker_id)
            if not case_dir:
                return float(DTOO_FAIL_PENALTY), {
                    "error": "cfd_failed",
                    "worker_id": worker_id,
                    "eval_mode": eval_mode,
                }
            from cfd_eval import evaluate_cfd
            cfd = evaluate_cfd(case_dir, cfd_cfg)
            if not cfd.get("ok"):
                return float(DTOO_FAIL_PENALTY), {
                    "error": "cfd_read_failed",
                    "detail": cfd.get("error"),
                    "worker_id": worker_id,
                    "eval_mode": eval_mode,
                }

        # ── Objective dispatch by eval_mode ──
        if eval_mode == "combined":
            total, breakdown = combined_objective(cfd, freqs, cfd_cfg, opt_cfg, obj_cfg)
            breakdown["worker_id"] = worker_id
            breakdown["eval_mode"] = eval_mode
            return float(total), breakdown

        if eval_mode == "cfd_only":
            total = cfd_scalar(cfd, cfd_cfg, obj_cfg)
            return float(total), {
                "total": float(total),
                "f_cfd": float(total),
                "f_resonance": None,
                "eta": float(cfd["eta"]),
                "vcav": float(cfd["vcav"]),
                "dH": float(cfd["dH"]),
                "note": "resonance skipped (EVAL_MODE=cfd_only)",
                "worker_id": worker_id,
                "eval_mode": eval_mode,
            }

        # eval_mode == "resonance_only"
        f_res = resonance_term(freqs, opt_cfg, obj_cfg)
        return float(f_res), {
            "total": float(f_res),
            "f_cfd": None,
            "f_resonance": float(f_res),
            "freqs": freqs,
            "note": "CFD skipped (EVAL_MODE=resonance_only)",
            "worker_id": worker_id,
            "eval_mode": eval_mode,
        }


os.makedirs(URI_DIR, exist_ok=True)
daemon = Pyro5.server.Daemon(host)
uri = str(daemon.register(Evaluator))

# Atomic publish: write to a temp file then rename, so the client never reads
# a partially written URI.
uri_path = os.path.join(URI_DIR, f"worker_{worker_id}.uri")
tmp_path = uri_path + ".tmp"
with open(tmp_path, "w") as fh:
    fh.write(uri)
os.replace(tmp_path, uri_path)

print(f"Worker {worker_id} ready on {host}: {uri}", flush=True)
sys.stdout.flush()
daemon.requestLoop()
