#!/usr/bin/env python3
"""Measure peak memory of the modal solve against problem size.

    python3 cluster/measure_modal_memory.py [--target-dofs N] [--max-gb G]

Sizing a run means answering one question: how many modal solves fit on a node
at once? ``concurrent_evaluations`` in the cluster configs rests on ~28.6 GB
per solve, a number inherited from the validation case and never measured on
tistos. Getting it wrong costs a 48-hour job to OOM kills.

This walks a sequence of box meshes of increasing size, solves each with both
backends in a **subprocess** — so the peak is that of one solve, uncontaminated
by anything measured before it — and fits a power law to extrapolate to the
target problem. tistos at P2 is 3 x 181749 = 545247 DOFs, the default target.

Each child reports its own ``ru_maxrss``, which on Linux is the peak resident
set in kilobytes: the number that decides whether a node swaps, not the virtual
reservation.

A runaway solve must fail on its own rather than drag the machine down, so the
budget is enforced twice. Where systemd is available the child runs in its own
scope with a ``MemoryMax``, which confines the kill to the solve; ``RLIMIT_AS``
in the child is the portable net for everywhere else. Neither helps if the
budget exceeds what the machine can actually spare -- the global OOM killer
fires first, and it takes whole cgroups with it -- so ``--max-gb`` is clamped
against ``MemAvailable`` before anything runs.

An extrapolation is not a measurement. The output says how far past the largest
measured point the target sits; beyond roughly 3x, treat the number as an
indication and give the first real run room.
"""

from __future__ import annotations

import argparse
import functools
import json
import math
import os
import resource
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: tistos: 181749 nodes on quadratic tets, 3 displacement components each.
DEFAULT_TARGET_DOFS = 545_247

#: Cells per edge of the unit box. P2 on N^3 cells gives 3*(2N+1)^3 DOFs:
#: 15k, 47k, 108k, 207k, 353k.
DEFAULT_SIZES = (8, 12, 16, 20, 24)

RESULT_MARKER = "MEMRESULT "

#: What to leave for the rest of the machine: the shell driving the sweep, the
#: session it runs in, and the system services. Measured in GB.
HEADROOM_GB = 1.5


# ── budget: what the machine can actually spare ───────────────────────────


def _available_gb() -> float | None:
    """Memory a new process can claim without pushing the kernel into a kill."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1024**2  # kB -> GB
    except (OSError, ValueError, IndexError):
        pass
    return None


def _clamp_budget(max_gb: float) -> float:
    """Cap the per-solve budget at what is actually free, minus headroom.

    A limit above free memory is not a limit at all: the global OOM killer
    reaches the solve first, and under systemd it takes the enclosing scope --
    the whole terminal window -- down with it.
    """
    available = _available_gb()
    if available is None:
        return max_gb
    ceiling = max(available - HEADROOM_GB, 0.5)
    if max_gb <= ceiling:
        return max_gb
    print(
        f"warning: --max-gb {max_gb:.1f} exceeds what this machine can spare "
        f"({available:.1f} GB available, {HEADROOM_GB:.1f} GB headroom); "
        f"clamping to {ceiling:.1f} GB",
        file=sys.stderr,
    )
    return ceiling


@functools.lru_cache(maxsize=1)
def _has_user_scope() -> bool:
    """Whether children can be confined to their own systemd scope.

    False on a compute node without a user manager -- under Slurm, say -- where
    the child runs directly and RLIMIT_AS is the only guard.
    """
    if not os.environ.get("XDG_RUNTIME_DIR") or not shutil.which("systemd-run"):
        return False
    try:
        probe = subprocess.run(
            ["systemd-run", "--user", "--scope", "--quiet", "--collect", "--", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


def _scope_prefix(max_gb: float) -> list[str]:
    """Command prefix confining a child to its own memory cgroup, if possible."""
    if not _has_user_scope():
        return []
    return [
        "systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        "-p",
        f"MemoryMax={max_gb:.2f}G",
        # Swapping would only distort the measurement before the kill lands.
        "-p",
        "MemorySwapMax=0",
        # Stop systemd from tearing down anything else once the kill happens.
        "-p",
        "OOMPolicy=continue",
        "--",
    ]


# ── child: one solve, one measurement ─────────────────────────────────────


def _run_one(cells: int, backend: str, max_gb: float) -> dict:
    """Solve one box problem and report peak RSS. Runs in the child process."""
    # Should the global OOM killer fire anyway, it should pick this solve over
    # the session that launched it.
    try:
        Path("/proc/self/oom_score_adj").write_text("500\n")
    except OSError:
        pass

    # A safety net, not a budget: without it a solve that outgrows the machine
    # thrashes instead of failing, and takes the measurement run with it. This
    # caps virtual address space, so it may trip before the cgroup does -- that
    # is the friendlier failure of the two, a MemoryError rather than a SIGKILL.
    limit = int(max_gb * 1024**3)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    from dolfinx import mesh as dmesh
    from mpi4py import MPI

    from eigenfrequencies.config import BCConfig, MaterialConfig, SolverConfig
    from eigenfrequencies.solver import ModalSolver

    domain = dmesh.create_unit_cube(
        MPI.COMM_WORLD, cells, cells, cells, dmesh.CellType.tetrahedron
    )
    solver = ModalSolver(
        domain,
        MaterialConfig(),
        # Same clamp as the runner hub in spirit: a plane of fixed DOFs.
        BCConfig(mode="axial_plane", axis="z", plane_value=0.0),
        SolverConfig(num_eigenvalues=10, element_degree=2, solver_backend=backend),
    )

    started = time.perf_counter()
    eigenvalues, _ = solver.solve()
    seconds = time.perf_counter() - started

    n_dofs = (
        solver.V.dofmap.index_map.size_global * solver.V.dofmap.index_map_bs
    )
    return {
        "ok": True,
        "cells": cells,
        "backend": backend,
        "n_dofs": int(n_dofs),
        "peak_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        "seconds": seconds,
        "n_frequencies": len(eigenvalues),
    }


# ── child: ask MUMPS instead of measuring ─────────────────────────────────


def _domain_and_bc(source: str, machine: str):
    """Return ``(domain, bc_config, label)`` for a mesh path or ``cube:N``.

    Two sources so the estimate can be calibrated: cubes reproduce the sizes
    whose peak RSS was measured by the sweep above, a ``.msh`` carries the real
    geometry with the clamp its machine YAML prescribes.
    """
    from eigenfrequencies.config import BCConfig, MeshConfig

    if source.startswith("cube:"):
        from dolfinx import mesh as dmesh
        from mpi4py import MPI

        cells = int(source.split(":", 1)[1])
        domain = dmesh.create_unit_cube(
            MPI.COMM_WORLD, cells, cells, cells, dmesh.CellType.tetrahedron
        )
        return domain, BCConfig(mode="axial_plane", axis="z", plane_value=0.0), source

    from eigenfrequencies.adapters.dtoo import load_machine_yaml
    from eigenfrequencies.adapters.dtoo.machine_yaml import machine_yaml_path
    from eigenfrequencies.bc.builders import from_template
    from eigenfrequencies.io import load_and_prepare_mesh

    config = load_machine_yaml(machine_yaml_path(machine))
    domain = load_and_prepare_mesh(MeshConfig(msh_path=source))
    template = config.bc_template
    return domain, from_template(template.type, template.params), f"{machine}:{source}"


def _run_mumps(source: str, machine: str, degree: int, max_gb: float, ooc: bool) -> dict:
    """Report what MUMPS says the factorization of this problem costs.

    Peak RSS can only be measured where the solve fits. MUMPS states its own
    requirement after the *analysis* phase, which is cheap, so the estimate is
    available for problems far larger than this machine can factor. INFOG(16) is
    the working space in MB per process, INFOG(17) the sum over processes.

    The operator is ``K + M`` — what shift-invert with sigma = -1 actually
    factors, assembled exactly as ``solver/slepc_backend.py`` does it, unit
    diagonal in K and zero in M on the constrained rows.
    """
    try:
        Path("/proc/self/oom_score_adj").write_text("500\n")
    except OSError:
        pass
    # max_gb <= 0 removes the cap. The estimate survives a truncated run, but
    # the *effective* figure only exists if the factorization is allowed to
    # finish — and the whole point of this mode is to reach sizes the cap
    # forbids. Ungated, so the caller owns the consequence.
    if max_gb > 0:
        limit = int(max_gb * 1024**3)
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

    import ufl
    from dolfinx import fem
    from dolfinx import mesh as dmesh
    from dolfinx.fem import petsc as fem_petsc
    from petsc4py import PETSc

    from eigenfrequencies.bc.builders import build_predicate
    from eigenfrequencies.config import MaterialConfig

    domain, bc_config, label = _domain_and_bc(source, machine)
    tdim = domain.topology.dim
    domain.topology.create_connectivity(tdim - 1, tdim)
    V = fem.functionspace(domain, ("Lagrange", degree, (3,)))

    material = MaterialConfig()
    mu = material.youngs_modulus / (2 * (1 + material.poisson_ratio))
    lmbda = (
        material.youngs_modulus
        * material.poisson_ratio
        / ((1 + material.poisson_ratio) * (1 - 2 * material.poisson_ratio))
    )

    def epsilon(w):
        return ufl.sym(ufl.grad(w))

    def sigma(w):
        return lmbda * ufl.tr(epsilon(w)) * ufl.Identity(3) + 2 * mu * epsilon(w)

    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    a_form = fem.form(ufl.inner(sigma(u), epsilon(v)) * ufl.dx)
    b_form = fem.form(material.density * ufl.dot(u, v) * ufl.dx)

    facets = dmesh.locate_entities_boundary(domain, tdim - 1, build_predicate(bc_config))
    dofs = fem.locate_dofs_topological(V, tdim - 1, facets)
    u_bc = fem.Function(V)
    u_bc.x.array[:] = 0.0
    bc = fem.dirichletbc(u_bc, dofs)
    if dofs.size == 0:
        raise RuntimeError(f"the {bc_config.mode} clamp caught no DOFs on {label}")

    K = fem_petsc.assemble_matrix(a_form, bcs=[bc], diag=1.0)
    K.assemble()
    M = fem_petsc.assemble_matrix(b_form, bcs=[bc], diag=0.0)
    M.assemble()
    A = K.copy()
    A.axpy(1.0, M)
    n_dofs = A.getSize()[0]
    assembled_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    pc = PETSc.PC().create(A.getComm())
    pc.setOperators(A)
    pc.setType("lu")
    pc.setFactorSolverType("mumps")
    # Builds the factor matrix without factoring, which is the only moment the
    # MUMPS control array can be reached. petsc4py 3.25 has no Mat.getFactor and
    # its factorSymbolicLU raises NotImplementedError, so this is the way in.
    pc.setFactorSetUpSolverType()
    F = pc.getFactorMatrix()
    if ooc:
        # Factors to disk: bounds what has to be resident, leaving the analysis
        # estimate untouched.
        F.setMumpsIcntl(22, 1)

    started = time.perf_counter()
    numeric_error = None
    try:
        pc.setUp()
    except Exception as exc:  # noqa: BLE001 — analysis already happened
        numeric_error = f"{type(exc).__name__}: {str(exc)[:200]}"
    seconds = time.perf_counter() - started

    def infog(key: int):
        try:
            return int(F.getMumpsInfog(key))
        except Exception:  # noqa: BLE001
            return None

    # INFOG(1) is the only honest witness that the factorization ran: 0 on
    # success, negative on a MUMPS error. Without it a run cut short by the
    # address-space limit reports no Python exception at all and looks like a
    # completed factorization — observed on tistos, where a truncated attempt
    # claimed 569 MB in 9 s against the 10169 MB and 217 s it really takes.
    error_flag = infog(1)
    factored = error_flag == 0 and (infog(22) or 0) > 0 and numeric_error is None

    return {
        "ok": True,
        "source": label,
        "degree": degree,
        "n_dofs": int(n_dofs),
        "clamped_dofs": int(dofs.size),
        # INFOG(16)/(17): estimated working space, MB per process and summed.
        # Set by the analysis phase, so they survive a failed factorization.
        "infog16_est_mb": infog(16),
        "infog17_est_mb": infog(17),
        # INFOG(22): what the factorization actually used. Meaningless unless
        # `factored` is true.
        "infog22_eff_mb": infog(22),
        "factor_entries": infog(9),
        "mumps_error_flag": error_flag,
        "factored": factored,
        "assembled_mb": assembled_mb,
        "peak_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
        "seconds": seconds,
        "out_of_core": ooc,
        "numeric_error": numeric_error,
    }


# ── parent: sweep, fit, extrapolate ───────────────────────────────────────


def _measure(cells: int, backend: str, max_gb: float, timeout: float) -> dict:
    """Run one child and parse its report."""
    cmd = _scope_prefix(max_gb) + [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        str(cells),
        backend,
        str(max_gb),
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "cells": cells, "backend": backend, "error": "timeout"}

    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])

    tail = (proc.stderr or proc.stdout)[-300:].replace("\n", " ").strip()
    if not tail:
        # A cgroup kill leaves no diagnostic behind, only a signalled exit.
        killed = proc.returncode < 0 or proc.returncode == 137
        tail = f"killed at the {max_gb:.1f} GB limit" if killed else "no result"
    return {"ok": False, "cells": cells, "backend": backend, "error": tail}


def _measure_mumps(
    source: str, machine: str, degree: int, max_gb: float, ooc: bool, timeout: float
) -> dict:
    """Run one MUMPS estimate in its own process and parse the report."""
    # No budget means no cgroup either: MemoryMax=0 would kill the child on its
    # first allocation.
    cmd = (_scope_prefix(max_gb) if max_gb > 0 else []) + [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child-mumps",
        source,
        machine,
        str(degree),
        str(max_gb),
        "1" if ooc else "0",
    ]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "source": source, "error": "timeout"}

    for line in reversed(proc.stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])

    tail = (proc.stderr or proc.stdout)[-300:].replace("\n", " ").strip()
    if not tail:
        killed = proc.returncode < 0 or proc.returncode == 137
        tail = f"killed at the {max_gb:.1f} GB limit" if killed else "no result"
    return {"ok": False, "source": source, "error": tail}


def _report_mumps(records: list[dict], target_dofs: int) -> None:
    """Print the estimate table and, if the target was not reached, a fit."""
    print(
        f"{'source':<34}{'DOFs':>9}{'est MB':>9}{'eff MB':>9}"
        f"{'peak MB':>9}{'sec':>7}  note"
    )
    for r in records:
        if not r.get("ok"):
            print(f"{r['source']:<34}{'—':>9}{'—':>9}{'—':>9}{'—':>9}{'—':>7}  {r['error'][:40]}")
            continue
        note = "out-of-core, " if r["out_of_core"] else ""
        if r["factored"]:
            note += "factored"
        else:
            note += f"NOT factored (INFOG1={r['mumps_error_flag']}), estimate only"
        print(
            f"{r['source']:<34}{r['n_dofs']:>9}"
            f"{r['infog16_est_mb'] or 0:>9}{(r['infog22_eff_mb'] or 0) if r['factored'] else 0:>9}"
            f"{r['peak_mb']:>9.0f}{r['seconds']:>7.0f}  {note}"
        )

    hit = [r for r in records if r.get("ok") and r["n_dofs"] >= target_dofs]
    if hit:
        best = hit[0]
        est = best["infog16_est_mb"]
        if best["factored"]:
            print(
                f"\nMUMPS needed {best['infog22_eff_mb'] / 1024:.1f} GB for "
                f"{best['n_dofs']} DOFs ({best['source']}), having estimated "
                f"{est / 1024:.1f} GB. Measured, not extrapolated."
            )
        else:
            print(
                f"\nMUMPS estimates {est / 1024:.1f} GB for {best['n_dofs']} DOFs "
                f"({best['source']}). The factorization did not run here, so this "
                f"is the analysis estimate, not an observed requirement."
            )
        return

    points = [
        (float(r["n_dofs"]), float(r["infog16_est_mb"]))
        for r in records
        if r.get("ok") and r["infog16_est_mb"]
    ]
    if len(points) < 2:
        print("\ntoo few points to say anything about the target")
        return
    a, b = _fit_power_law(points)
    largest = max(x for x, _ in points)
    print(
        f"\nThe target was not reached. Fit over the MUMPS estimates: "
        f"{a:.3g} * dofs^{b:.2f} -> {a * target_dofs**b / 1024:.1f} GB at "
        f"{target_dofs} DOFs — an EXTRAPOLATION, {target_dofs / largest:.1f}x "
        f"beyond the largest point that ran."
    )


def _fit_power_law(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least-squares fit of ``peak = a * dofs**b`` in log space."""
    xs = [math.log(x) for x, _ in points]
    ys = [math.log(y) for _, y in points]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    b = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    a = math.exp(mean_y - b * mean_x)
    return a, b


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", nargs=3, metavar=("CELLS", "BACKEND", "MAX_GB"))
    parser.add_argument(
        "--child-mumps", nargs=5, metavar=("SOURCE", "MACHINE", "DEGREE", "MAX_GB", "OOC")
    )
    parser.add_argument(
        "--mumps",
        nargs="+",
        metavar="SOURCE",
        help="ask MUMPS what it needs, per source: a .msh path or cube:N",
    )
    parser.add_argument("--machine", default="tistos", help="machine YAML for the BC template")
    parser.add_argument("--degree", type=int, default=2)
    parser.add_argument("--ooc", action="store_true", help="MUMPS out-of-core (ICNTL 22)")
    parser.add_argument(
        "--no-limit",
        action="store_true",
        help="drop the memory cap for --mumps, so the factorization can finish",
    )
    parser.add_argument("--target-dofs", type=int, default=DEFAULT_TARGET_DOFS)
    parser.add_argument("--max-gb", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--sizes", type=int, nargs="+", default=list(DEFAULT_SIZES))
    parser.add_argument("--backends", nargs="+", default=["scipy", "slepc"])
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.child:
        cells, backend, max_gb = args.child
        try:
            result = _run_one(int(cells), backend, _clamp_budget(float(max_gb)))
        except Exception as exc:  # noqa: BLE001 — an OOM is a data point
            result = {
                "ok": False,
                "cells": int(cells),
                "backend": backend,
                "error": f"{type(exc).__name__}: {exc}",
            }
        print(RESULT_MARKER + json.dumps(result))
        return 0 if result["ok"] else 1

    if args.child_mumps:
        source, machine, degree, max_gb, ooc = args.child_mumps
        try:
            result = _run_mumps(
                source, machine, int(degree), _clamp_budget(float(max_gb)), ooc == "1"
            )
        except Exception as exc:  # noqa: BLE001 — an OOM is a data point
            result = {"ok": False, "source": source, "error": f"{type(exc).__name__}: {exc}"}
        print(RESULT_MARKER + json.dumps(result))
        return 0 if result["ok"] else 1

    max_gb = _clamp_budget(args.max_gb)

    if args.mumps:
        budget = 0.0 if args.no_limit else max_gb
        records = [
            _measure_mumps(source, args.machine, args.degree, budget, args.ooc, args.timeout)
            for source in args.mumps
        ]
        _report_mumps(records, args.target_dofs)
        return 0

    records: list[dict] = []
    print(f"{'backend':<8}{'cells':>7}{'DOFs':>10}{'peak MB':>10}{'seconds':>10}  note")
    for backend in args.backends:
        for cells in args.sizes:
            record = _measure(cells, backend, max_gb, args.timeout)
            records.append(record)
            if record["ok"]:
                print(
                    f"{backend:<8}{cells:>7}{record['n_dofs']:>10}"
                    f"{record['peak_mb']:>10.0f}{record['seconds']:>10.1f}"
                )
            else:
                print(f"{backend:<8}{cells:>7}{'—':>10}{'—':>10}{'—':>10}  {record['error'][:60]}")
                break  # Larger sizes will not fit either.

    print()
    for backend in args.backends:
        points = [
            (float(r["n_dofs"]), float(r["peak_mb"]))
            for r in records
            if r["ok"] and r["backend"] == backend
        ]
        if len(points) < 2:
            print(f"{backend}: too few points to extrapolate")
            continue
        a, b = _fit_power_law(points)
        largest = max(x for x, _ in points)
        predicted_mb = a * args.target_dofs**b
        reach = args.target_dofs / largest
        print(
            f"{backend}: peak ~ {a:.3g} * dofs^{b:.2f}  ->  "
            f"{predicted_mb / 1024:.1f} GB at {args.target_dofs} DOFs "
            f"({reach:.1f}x beyond the largest measured point"
            f"{', treat as an indication' if reach > 3 else ''})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
