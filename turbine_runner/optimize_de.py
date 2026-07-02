#!/usr/bin/env python3
"""Differential Evolution (DE) parallel optimizer for runner design.

Population-based: each generation evaluates pop_size designs independently.
Runs embarrassingly parallel via ThreadPoolExecutor (threads, not processes)
so workers share the same Python interpreter and avoid enroot spawn issues.

Supports both resonance-only (CFD_CASE_DIR="") and full CFD+resonance modes.
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from config import (
    DesignConfig, OptimizationConfig, CFDConfig, ObjectiveConfig, DEConfig,
)
from objective import combined_objective, resonance_term
from cfd_eval import evaluate_cfd
from optimize import _run_dtoo, _run_fenicsx, DTOO_FAIL_PENALTY, HERE

CFD_CASE_DIR = os.environ.get("CFD_CASE_DIR", os.path.join(HERE, "data", "of_case"))


def _evaluate_design_worker(args):
    """Thread worker: evaluate one design in an isolated $TMPDIR.

    Args:
        args = (worker_id, x, labels, cfd_cfg, opt_cfg, obj_cfg)

    Returns:
        (objective_value, breakdown_dict)
    """
    worker_id, x, labels, cfd_cfg, opt_cfg, obj_cfg = args

    design = {lab: float(v) for lab, v in zip(labels, x)}
    if not _run_dtoo(design, worker_id=worker_id):
        return DTOO_FAIL_PENALTY, {"error": "dtoo_build_failed", "worker_id": worker_id}

    fre = _run_fenicsx(worker_id=worker_id)
    if not fre.get("ok"):
        return DTOO_FAIL_PENALTY, {"error": "modal_solve_failed", "worker_id": worker_id}
    freqs = fre["frequencies_hz"]

    # CFD objectives are optional; degrade to resonance-only if no case dir present.
    if CFD_CASE_DIR and os.path.isdir(CFD_CASE_DIR):
        # Each worker needs a unique CFD case dir to avoid collisions
        worker_cfd_dir = os.path.join(CFD_CASE_DIR, f"worker_{worker_id}")
        if os.path.isdir(worker_cfd_dir):
            cfd = evaluate_cfd(worker_cfd_dir, cfd_cfg)
            if not cfd.get("ok"):
                return DTOO_FAIL_PENALTY, {
                    "error": f"cfd_failed: {cfd.get('error')}",
                    "worker_id": worker_id,
                }
            total, breakdown = combined_objective(cfd, freqs, cfd_cfg, opt_cfg, obj_cfg)
            breakdown["worker_id"] = worker_id
            return total, breakdown

    f_res = resonance_term(freqs, opt_cfg, obj_cfg)
    return float(f_res), {
        "total": float(f_res),
        "f_cfd": None,
        "f_resonance": float(f_res),
        "freqs": freqs,
        "note": "CFD skipped (no case dir) - resonance only",
        "worker_id": worker_id,
    }


def de_optimize(bounds, pop_size, F, CR, max_generations, tol, seed,
                labels, cfd_cfg, opt_cfg, obj_cfg,
                max_workers=None):
    """Custom DE/rand/1 loop with parallel evaluation.

    Returns dict with best_design, best_objective, history, generations.
    """
    rng = np.random.default_rng(seed)
    n_dim = len(bounds)
    lower = np.array([b[0] for b in bounds])
    upper = np.array([b[1] for b in bounds])

    # Initialize population uniformly in bounds
    population = lower + rng.random((pop_size, n_dim)) * (upper - lower)
    objectives = np.full(pop_size, np.inf)
    breakdowns = [None] * pop_size

    history = []

    print(f"[DE] pop_size={pop_size} F={F} CR={CR} max_gen={max_generations} tol={tol}")
    print(f"[DE] bounds={bounds} n_dim={n_dim}")

    for gen in range(max_generations):
        # --- evaluate current population in parallel ---
        worker_args = [
            (i % pop_size, population[i], labels, cfd_cfg, opt_cfg, obj_cfg)
            for i in range(pop_size)
        ]
        # Reuse worker_id i (same as population index) for I/O isolation

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_evaluate_design_worker, wa): idx
                       for idx, wa in enumerate(worker_args)}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    objectives[idx], breakdowns[idx] = future.result(timeout=1800)
                except Exception as exc:
                    objectives[idx] = DTOO_FAIL_PENALTY
                    breakdowns[idx] = {"error": str(exc), "worker_id": idx}

        # Log generation
        gen_best = int(np.argmin(objectives))
        print(f"[gen {gen+1}/{max_generations}] best={objectives[gen_best]:.4g} "
              f"mean={objectives.mean():.4g} std={objectives.std():.4g}")
        for i in range(pop_size):
            history.append({
                "generation": gen + 1,
                "individual": i,
                "x": list(map(float, population[i])),
                "objective": float(objectives[i]),
                **(breakdowns[i] or {}),
            })

        # Convergence check
        if objectives.std() < tol * max(1.0, abs(objectives.mean())):
            print(f"[DE] Converged at generation {gen+1} (std < tol)")
            break

        # --- DE/rand/1 mutation + crossover ---
        new_population = np.empty_like(population)
        for i in range(pop_size):
            # Pick 3 random distinct indices != i
            candidates = [j for j in range(pop_size) if j != i]
            a, b, c = rng.choice(candidates, size=3, replace=False)
            mutant = population[a] + F * (population[b] - population[c])
            # Clamp to bounds
            mutant = np.clip(mutant, lower, upper)

            # Binomial crossover
            trial = np.empty(n_dim)
            j_rand = rng.integers(n_dim)
            for j in range(n_dim):
                if rng.random() < CR or j == j_rand:
                    trial[j] = mutant[j]
                else:
                    trial[j] = population[i][j]
            new_population[i] = trial

        # Greedy selection: evaluate new population in next generation loop
        population = new_population

    best_idx = int(np.argmin(objectives))
    best_design = {lab: float(v) for lab, v in zip(labels, population[best_idx])}
    return {
        "best_design": best_design,
        "best_objective": float(objectives[best_idx]),
        "best_breakdown": breakdowns[best_idx],
        "history": history,
        "generations": gen + 1,
        "population": [list(map(float, p)) for p in population],
        "objectives": list(map(float, objectives)),
    }


def main() -> None:
    design_cfg = DesignConfig()
    opt_cfg = OptimizationConfig()
    cfd_cfg = CFDConfig()
    obj_cfg = ObjectiveConfig()
    de_cfg = DEConfig()

    # Env overrides (handy for smoke runs)
    de_cfg.pop_size = int(os.environ.get("DE_POP_SIZE", de_cfg.pop_size))
    de_cfg.mutation = float(os.environ.get("DE_MUTATION", de_cfg.mutation))
    de_cfg.crossover = float(os.environ.get("DE_CROSSOVER", de_cfg.crossover))
    de_cfg.max_generations = int(os.environ.get("DE_MAX_GEN", de_cfg.max_generations))
    de_cfg.tol = float(os.environ.get("DE_TOL", de_cfg.tol))
    if os.environ.get("DE_SEED"):
        de_cfg.seed = int(os.environ["DE_SEED"])

    opt_cfg.f_min = float(os.environ.get("OPT_FMIN", opt_cfg.f_min))
    opt_cfg.f_max = float(os.environ.get("OPT_FMAX", opt_cfg.f_max))

    labels = design_cfg.labels
    bounds = design_cfg.bounds

    print("=" * 60)
    print("Runner DE optimization (parallel)")
    print("=" * 60)
    print(f"Design params : {labels}")
    print(f"Forbidden band: [{opt_cfg.f_min}, {opt_cfg.f_max}] Hz")
    print(f"CFD case dir  : {CFD_CASE_DIR or '(none -> resonance-only)'}")
    print(f"DE params     : pop={de_cfg.pop_size} F={de_cfg.mutation} "
          f"CR={de_cfg.crossover} max_gen={de_cfg.max_generations}")
    print(f"Workers       : {de_cfg.pop_size} (1 core each)")
    print()

    result = de_optimize(
        bounds=bounds,
        pop_size=de_cfg.pop_size,
        F=de_cfg.mutation,
        CR=de_cfg.crossover,
        max_generations=de_cfg.max_generations,
        tol=de_cfg.tol,
        seed=de_cfg.seed,
        labels=labels,
        cfd_cfg=cfd_cfg,
        opt_cfg=opt_cfg,
        obj_cfg=obj_cfg,
        max_workers=de_cfg.pop_size,
    )

    print("\n" + "=" * 60)
    print("Optimization finished")
    print(f"Generations   : {result['generations']}")
    print(f"Best design   : {result['best_design']}")
    print(f"Best objective: {result['best_objective']:.4g}")

    out_path = os.path.join(HERE, "output", "optimization_de.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(result, fh, indent=2)
    print(f"History       : {out_path}")


if __name__ == "__main__":
    main()
