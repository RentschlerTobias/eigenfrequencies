#!/usr/bin/env python3
"""Differential Evolution (DE) parallel optimizer via Pyro5 RPC.

Persistent worker servers (one per core) publish their Pyro5 URIs to a shared
filesystem directory; the client reads them and dispatches designs via RPC,
blocking on network I/O only (no subprocess.pipe deadlocks, no Name Server).

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

try:
    from tqdm import tqdm
    _HAVE_TQDM = True
except ImportError:  # tqdm optional — fall back to plain per-generation logs
    _HAVE_TQDM = False

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import OptimizationConfig, ObjectiveConfig, CFDConfig, DEConfig, DesignConfig
from optimize import DTOO_FAIL_PENALTY


# ────────────────────────────────
# Worker discovery
# ────────────────────────────────

def _discover_servers(expected_count: int = 1,
                      timeout: int = 120) -> list[str]:
    """Discover worker URIs from the shared-filesystem URI directory (A2).

    Each worker writes worker_<id>.uri once its Pyro5 daemon is registered.
    Poll until expected_count files appear because every process must import
    dtOO/FEniCSx before publishing — heavy parallel imports take minutes.

    No Name Server, no broadcast, no hostname discovery: workers on any node
    become reachable as soon as their URI file lands on the shared filesystem.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    default_dir = os.path.join(os.path.dirname(here), "server_logs", "uris")
    uri_dir = os.environ.get("DE_URI_DIR", default_dir)
    deadline = time.time() + timeout
    uris: list[str] = []
    while True:
        if os.path.isdir(uri_dir):
            uris = []
            for f in sorted(os.listdir(uri_dir)):
                if not f.endswith(".uri"):
                    continue
                try:
                    with open(os.path.join(uri_dir, f)) as fh:
                        u = fh.read().strip()
                except OSError:
                    continue
                if u.startswith("PYRO:"):
                    uris.append(u)
            if len(uris) >= expected_count:
                print(f"[DE] Discovered {len(uris)} workers from {uri_dir}")
                return uris
        if time.time() > deadline:
            break
        time.sleep(2)
    print(f"[DE] Discovered {len(uris)} workers after {timeout}s "
          f"(expected {expected_count}) in {uri_dir}")
    return uris


# ────────────────────────────────
# Remote evaluation
# ────────────────────────────────

def _evaluate_remote(server_uri, design, labels):
    """Call remote worker synchronously via its direct Pyro5 URI.

    Creates a fresh proxy inside this thread to avoid Pyro5 ownership issues.
    """
    with Pyro5.api.Proxy(server_uri) as proxy:
        return proxy.evaluate(design.tolist(), labels)


# ────────────────────────────────
# Checkpoint / resume
# ────────────────────────────────

def _state_path() -> str:
    """Path of the DE checkpoint file (survives across jobs).

    Lives outside server_logs/ (which submit_de.sh wipes per job) so a killed
    run can be resumed by simply resubmitting.
    """
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "de_state.json")
    return os.environ.get("DE_STATE_FILE", default)


def _save_checkpoint(path, gen, population, objectives, breakdowns,
                     best_vec, best_obj, labels, bounds, rng):
    """Atomically write the DE state so a cancelled run keeps its results.

    Analogous to de_framework's archi_save.json, but for our hand-rolled loop.
    """
    state = {
        "gen": int(gen),
        "population": population.tolist(),
        "objectives": objectives.tolist(),
        "breakdowns": breakdowns,
        "best_vec": best_vec.tolist(),
        "best_obj": float(best_obj),
        "labels": list(labels),
        "pop_size": int(population.shape[0]),
        "bounds": np.asarray(bounds).tolist(),
        "rng_state": rng.bit_generator.state,
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh)
    os.replace(tmp, path)


def _load_checkpoint(path, labels, pop_size, bounds):
    """Return a compatible checkpoint dict, or None for a fresh run.

    Skips resume if DE_FRESH=1, the file is missing, or the saved
    labels/pop_size/bounds do not match the current config (guards against
    silently resuming a different experiment).
    """
    if os.environ.get("DE_FRESH") == "1" or not os.path.isfile(path):
        return None
    try:
        with open(path) as fh:
            state = json.load(fh)
    except (OSError, ValueError) as e:
        print(f"[DE] Ignoring unreadable checkpoint {path}: {e}")
        return None

    if (list(state.get("labels", [])) != list(labels)
            or state.get("pop_size") != pop_size
            or state.get("bounds") != np.asarray(bounds).tolist()):
        print(f"[DE] Checkpoint {path} incompatible with current config "
              f"(labels/pop_size/bounds) — starting fresh. Set DE_FRESH=1 to silence.")
        return None
    return state


# ────────────────────────────────
# Live view (progress bar + history)
# ────────────────────────────────

def _history_path() -> str:
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "de_history.jsonl")
    return os.environ.get("DE_HISTORY_FILE", default)


def _append_history(path, gen, best_obj, mean_obj, n_ok, n, t_gen):
    """Append one compact JSON line per generation (cheap, plot-friendly)."""
    rec = {"gen": int(gen), "best": float(best_obj), "mean": float(mean_obj),
           "ok": int(n_ok), "n": int(n), "t_gen_s": round(float(t_gen), 1)}
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _make_bar(total, desc):
    """tqdm bar throttled so the shared-FS .out is not hammered (DE_TQDM_INTERVAL,
    default 10s). Returns None if tqdm is unavailable."""
    if not _HAVE_TQDM:
        return None
    return tqdm(total=total, desc=desc, file=sys.stdout,
                mininterval=float(os.environ.get("DE_TQDM_INTERVAL", "10")),
                dynamic_ncols=True, leave=True)


def _evaluate_population(server_uris, pop, labels, n_workers, desc):
    """Evaluate every individual in parallel via the workers, with a live bar.

    Returns (objectives, breakdowns). Failed/errored evals get
    DTOO_FAIL_PENALTY. Shared by generation 0 and the trial generations.
    """
    n = len(pop)
    objectives = np.full(n, float(DTOO_FAIL_PENALTY))
    breakdowns = [None] * n
    n_ok = 0
    bar = _make_bar(n, desc)
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_evaluate_remote, server_uris[i % n_workers], pop[i], labels): i
            for i in range(n)
        }
        for future in as_completed(futures):
            i = futures[future]
            try:
                obj, brk = future.result(timeout=900)
                objectives[i] = obj
                breakdowns[i] = brk
                if obj < DTOO_FAIL_PENALTY:
                    n_ok += 1
            except Exception as e:
                print(f"[DE] Worker error for individual {i}: {e}")
                objectives[i] = DTOO_FAIL_PENALTY
            if bar is not None:
                bar.set_postfix_str(f"ok={n_ok}/{n} best={float(np.min(objectives)):.4g}")
                bar.update(1)
    if bar is not None:
        bar.close()
    return objectives, breakdowns


# ────────────────────────────────
# DE main loop
# ────────────────────────────────

def main():
    # Line-buffer stdout so progress lands in the .out even if SLURM kills the
    # job mid-run (default block buffering would lose it on SIGKILL).
    sys.stdout.reconfigure(line_buffering=True)

    de_cfg = DEConfig()
    opt_cfg = OptimizationConfig()
    obj_cfg = ObjectiveConfig()
    design_cfg = DesignConfig()
    labels = design_cfg.labels

    # Discover worker URIs from the shared-filesystem URI directory
    server_uris = _discover_servers(expected_count=de_cfg.pop_size)
    n_workers = len(server_uris)
    if n_workers == 0:
        print("[DE] ERROR: No worker servers found. Start servers first:")
        print("       bash cluster/start_servers.sh")
        sys.exit(1)

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
    state_path = _state_path()
    history_path = _history_path()

    print(f"[DE] population={pop_size} dim={dim} mutation={mutation} "
          f"crossover={crossover} max_gen={max_gen} tol={tol} seed={seed} "
          f"workers={n_workers}")

    # ── Resume from checkpoint if compatible, else run fresh Generation 0 ──
    state = _load_checkpoint(state_path, labels, pop_size, bounds)
    if state is not None:
        population = np.array(state["population"])
        objectives = np.array(state["objectives"])
        breakdowns = state["breakdowns"]
        best_vec = np.array(state["best_vec"])
        best_obj = state["best_obj"]
        rng.bit_generator.state = state["rng_state"]
        # Greedy selection keeps the best in the population, so best == argmin.
        best_idx = int(np.argmin(objectives))
        start_gen = state["gen"] + 1
        print(f"[DE] Resuming from {state_path} at generation {start_gen} "
              f"(best={best_obj:.6f}).")
    else:
        # Initialize population uniformly in bounds
        population = np.array([
            low + rng.random(dim) * span for _ in range(pop_size)
        ])

        # ── Generation 0 ──
        t0 = time.time()
        objectives, breakdowns = _evaluate_population(
            server_uris, population, labels, n_workers, "gen 0")

        best_idx = int(objectives.argmin())
        best_vec = population[best_idx].copy()
        best_obj = objectives[best_idx]
        n_ok = int(np.sum(objectives < DTOO_FAIL_PENALTY))
        print(f"[DE] Generation 0 best={best_obj:.6f} mean={objectives.mean():.6f} "
              f"ok={n_ok}/{pop_size}")
        _save_checkpoint(state_path, 0, population, objectives, breakdowns,
                         best_vec, best_obj, labels, bounds, rng)
        _append_history(history_path, 0, best_obj, objectives.mean(),
                        n_ok, pop_size, time.time() - t0)
        start_gen = 1

    # ── Generations start_gen..max_gen ──
    for g in range(start_gen, max_gen + 1):
        t0 = time.time()
        trial_pop = population.copy()

        for i in range(pop_size):
            a, b, c = rng.choice(pop_size, size=3, replace=False)
            mutant = population[a] + mutation * (population[b] - population[c])
            mutant = np.clip(mutant, low, high)

            cross = rng.random(dim) < crossover
            if not cross.any():
                cross[rng.integers(dim)] = True
            trial = np.where(cross, mutant, population[i])
            trial_pop[i] = trial

        # Evaluate trial population in parallel (with live progress bar)
        trial_obj, trial_brk = _evaluate_population(
            server_uris, trial_pop, labels, n_workers, f"gen {g}")

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

        n_ok = int(np.sum(objectives < DTOO_FAIL_PENALTY))
        print(f"[DE] Generation {g} best={best_obj:.6f} mean={objectives.mean():.6f} "
              f"ok={n_ok}/{pop_size}")
        _append_history(history_path, g, best_obj, objectives.mean(),
                        n_ok, pop_size, time.time() - t0)
        _save_checkpoint(state_path, g, population, objectives, breakdowns,
                         best_vec, best_obj, labels, bounds, rng)

        # Early stopping: converge on the spread of *successful* objectives.
        # Failed designs sit at DTOO_FAIL_PENALTY (1e6); including them would
        # keep std huge forever, so they are excluded. (Previously this checked
        # span.std(), the constant bounds width, which never changed.)
        finite = objectives[objectives < DTOO_FAIL_PENALTY]
        if finite.size > 1 and finite.std() < tol:
            print(f"[DE] Converged (std(objectives)={finite.std():.4g} < tol={tol}).")
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
