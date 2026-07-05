#!/usr/bin/env python3
"""Differential Evolution (DE) parallel optimizer via Pyro5 RPC.

Follows the rl_framework schema: persistent worker servers (one per core)
registered with a Pyro5 Name Server. The client dispatches designs via RPC
and blocks on network I/O (no subprocess.pipe deadlocks).

Supports both resonance-only (CFD_CASE_DIR="") and full CFD+resonance modes.
"""

import os
import sys
import math
import random
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import Pyro5.api

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OptimizationConfig, ObjectiveConfig, CFDConfig, DEConfig, DesignConfig
from optimize import DTOO_FAIL_PENALTY


# ────────────────────────────────
# Worker discovery
# ────────────────────────────────

def _discover_servers(ns_host: str = None,
                      expected_count: int = 1,
                      timeout: int = 120) -> list[str]:
    """Discover worker servers via Pyro5 Name Server.

    Polls until expected_count workers appear because each process must import
    dtOO/FEniCSx before registering. Heavy parallel imports can take minutes.
    """
    if ns_host is None:
        import socket
        ns_host = socket.gethostname()
    deadline = time.time() + timeout
    last_error = None
    servers = []
    while True:
        try:
            ns = Pyro5.api.locate_ns(host=ns_host)
            items = ns.list()
            servers = sorted([k for k in items.keys() if "_worker_" in k])
            if len(servers) >= expected_count:
                print(f"[DE] Discovered {len(servers)} servers: {servers}")
                return servers
        except Exception as e:
            last_error = e
        if time.time() > deadline:
            break
        time.sleep(2)
    print(f"[DE] Discovered {len(servers)} servers after {timeout}s "
          f"(expected {expected_count}, last_error: {last_error})")
    return servers


# ────────────────────────────────
# Remote evaluation
# ────────────────────────────────

def _evaluate_remote(server_name, design, labels):
    """Call remote server synchronously (blocks on network I/O only).
    
    Creates a fresh proxy inside this thread to avoid Pyro5 ownership issues.
    """
    with Pyro5.api.Proxy(f"PYRONAME:{server_name}") as proxy:
        return proxy.evaluate(design.tolist(), labels)


# ────────────────────────────────
# DE main loop
# ────────────────────────────────

def main():
    de_cfg = DEConfig()
    opt_cfg = OptimizationConfig()
    obj_cfg = ObjectiveConfig()
    design_cfg = DesignConfig()
    labels = design_cfg.labels

    # Discover servers
    ns_host = os.environ.get("PYRO_NS_HOST", None)
    servers = _discover_servers(ns_host, expected_count=de_cfg.pop_size)
    n_workers = len(servers)
    if n_workers == 0:
        print("[DE] ERROR: No worker servers found. Start servers first:")
        print("       bash cluster/start_servers.sh")
        sys.exit(1)

    # Server name list (proxies created fresh inside each worker thread)
    server_names = servers

    dim = len(labels)
    bounds = np.array(design_cfg.bounds)
    low, high = bounds[:, 0], bounds[:, 1]
    span = high - low

    pop_size = min(de_cfg.pop_size, max(4, n_workers))
    mutation = de_cfg.mutation
    crossover = de_cfg.crossover
    max_gen = de_cfg.max_generations
    tol = de_cfg.tol
    seed = de_cfg.seed
    rng = np.random.default_rng(seed)

    # Initialize population uniformly in bounds
    population = np.array([
        low + rng.random(dim) * span for _ in range(pop_size)
    ])

    print(f"[DE] population={pop_size} dim={dim} mutation={mutation} "
          f"crossover={crossover} max_gen={max_gen} tol={tol} seed={seed} "
          f"workers={n_workers}")

    # ── Generation 0 ──
    objectives = np.full(pop_size, 1e9)
    breakdowns = [None] * pop_size

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_evaluate_remote, server_names[i % n_workers], population[i], labels): i
            for i in range(pop_size)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                obj, brk = future.result(timeout=900)
                objectives[i] = obj
                breakdowns[i] = brk
            except Exception as e:
                print(f"[DE] Worker error for individual {i}: {e}")
                objectives[i] = DTOO_FAIL_PENALTY

    print(f"[DE] Generation 0 best={objectives.min():.6f}")

    best_idx = int(objectives.argmin())
    best_vec = population[best_idx].copy()
    best_obj = objectives[best_idx]

    # ── Generations 1..max_gen ──
    for g in range(1, max_gen + 1):
        trial_pop = population.copy()
        trial_obj = objectives.copy()
        trial_brk = breakdowns.copy()

        for i in range(pop_size):
            a, b, c = rng.choice(pop_size, size=3, replace=False)
            mutant = population[a] + mutation * (population[b] - population[c])
            mutant = np.clip(mutant, low, high)

            cross = rng.random(dim) < crossover
            if not cross.any():
                cross[rng.integers(dim)] = True
            trial = np.where(cross, mutant, population[i])
            trial_pop[i] = trial

        # Evaluate trial population in parallel
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futures = {
                pool.submit(
                    _evaluate_remote, server_names[i % n_workers], trial_pop[i], labels
                ): i
                for i in range(pop_size)
            }
            for future in as_completed(futures):
                i = futures[future]
                try:
                    obj, brk = future.result(timeout=900)
                    trial_obj[i] = obj
                    trial_brk[i] = brk
                except Exception as e:
                    print(f"[DE] Worker error for trial {i}: {e}")
                    trial_obj[i] = DTOO_FAIL_PENALTY

        # Selection (greedy)
        improved = trial_obj < objectives
        population[improved] = trial_pop[improved]
        objectives[improved] = trial_obj[improved]
        for idx in np.where(improved)[0]:
            breakdowns[idx] = trial_brk[idx]

        if objectives.min() < best_obj:
            best_idx = int(objectives.argmin())
            best_vec = population[best_idx].copy()
            best_obj = objectives[best_idx]

        print(f"[DE] Generation {g} best={best_obj:.6f} mean={objectives.mean():.6f}")

        # Early stopping
        if span.std() < tol:
            print("[DE] Converged (population std < tol).")
            break

    # ── Final output ──
    print("\n" + "=" * 60)
    print(f"[DE] BEST  objective = {best_obj:.6f}")
    print(f"[DE] BEST  design    = {dict(zip(labels, best_vec.tolist()))}")
    print(f"[DE] BREAKDOWN      = {json.dumps(breakdowns[best_idx], indent=2)}")
    print("=" * 60)

    best_design = dict(zip(labels, best_vec.tolist()))
    with open(os.path.join(os.path.dirname(__file__), "best_design.json"), "w") as fh:
        json.dump(best_design, fh, indent=2)


if __name__ == "__main__":
    main()
