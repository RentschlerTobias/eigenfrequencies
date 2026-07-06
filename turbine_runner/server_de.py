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
from objective import combined_objective, resonance_term
from optimize import _run_dtoo, _run_fenicsx, DTOO_FAIL_PENALTY

host = socket.gethostname()
worker_id = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ns_host = sys.argv[2] if len(sys.argv) > 2 else host

Pyro5.config.HOST = host

name = f"{host}_worker_{worker_id}"

CFD_CASE_DIR = os.environ.get("CFD_CASE_DIR", "")


@Pyro5.api.expose
class Evaluator(object):
    def evaluate(self, x_list, labels):
        """Evaluate a single design vector.

        Returns (objective_float, breakdown_dict).
        """
        x = {lab: float(v) for lab, v in zip(labels, x_list)}

        # dtOO build
        if not _run_dtoo(x, worker_id=worker_id):
            return float(DTOO_FAIL_PENALTY), {
                "error": "dtoo_build_failed",
                "worker_id": worker_id,
            }

        # Modal analysis
        fre = _run_fenicsx(worker_id=worker_id)
        if not fre.get("ok"):
            return float(DTOO_FAIL_PENALTY), {
                "error": "modal_solve_failed",
                "worker_id": worker_id,
            }
        freqs = fre["frequencies_hz"]

        # Optional CFD
        CFD_ENABLED = os.environ.get("CFD_ENABLED", "0") == "1"
        if CFD_ENABLED and CFD_CASE_DIR and os.path.isdir(CFD_CASE_DIR):
            worker_cfd_dir = os.path.join(CFD_CASE_DIR, f"worker_{worker_id}")
            if os.path.isdir(worker_cfd_dir):
                from cfd_eval import evaluate_cfd
                cfd_cfg = CFDConfig()
                cfd = evaluate_cfd(worker_cfd_dir, cfd_cfg)
                if not cfd.get("ok"):
                    return float(DTOO_FAIL_PENALTY), {
                        "error": "cfd_failed",
                        "worker_id": worker_id,
                    }
                opt_cfg = OptimizationConfig()
                obj_cfg = ObjectiveConfig()
                total, breakdown = combined_objective(cfd, freqs, cfd_cfg, opt_cfg, obj_cfg)
                breakdown["worker_id"] = worker_id
                return float(total), breakdown

        # Fallback: resonance only
        opt_cfg = OptimizationConfig()
        obj_cfg = ObjectiveConfig()
        f_res = resonance_term(freqs, opt_cfg, obj_cfg)
        return float(f_res), {
            "total": float(f_res),
            "f_cfd": None,
            "f_resonance": float(f_res),
            "freqs": freqs,
            "note": "CFD skipped",
            "worker_id": worker_id,
        }


daemon = Pyro5.server.Daemon(host)
ns = Pyro5.api.locate_ns(host=ns_host)
uri = daemon.register(Evaluator)
ns.register(name, uri)
print(f"Server {name} ready on {host}.", flush=True)
sys.stdout.flush()
daemon.requestLoop()
