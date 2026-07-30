"""CLI entry point for eigenfrequencies analysis.

Provides ``solve`` (modal analysis from YAML config) and ``validate``
(beam / testcase validation suites) subcommands.
"""

import dataclasses
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import typer

from eigenfrequencies import provenance
from eigenfrequencies.config import (
    BCConfig,
    MaterialConfig,
    MeshConfig,
    OutputConfig,
    SolverConfig,
)
from eigenfrequencies.config_yaml import ConfigError, load_config
from eigenfrequencies.io.results import write_results_json
from eigenfrequencies.validation.beam.analytical import (
    analytical_frequencies_cantilever,
    classify_mode,
)

try:
    from eigenfrequencies.optimize import create as create_optimizer
except ImportError:
    create_optimizer = None  # type: ignore[misc,assignment]

# Lazy imports for container-only dependencies so the CLI is importable locally.
try:
    from eigenfrequencies.io import load_and_prepare_mesh
except ImportError:
    load_and_prepare_mesh = None  # type: ignore[misc,assignment]

try:
    from eigenfrequencies.io.results import write_results_xdmf_vtk
except ImportError:
    write_results_xdmf_vtk = None  # type: ignore[misc,assignment]

try:
    from eigenfrequencies.solver import ModalSolver, SolverConfigError
except ImportError:
    ModalSolver = None  # type: ignore[misc,assignment]
    SolverConfigError = None  # type: ignore[misc,assignment]

app = typer.Typer(help="Eigenfrequencies analysis CLI")

# Exit codes
EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
EXIT_SOLVE_ERROR = 3
EXIT_VALIDATION_DEVIATION = 4

TOLERANCE_PCT = 5.0


def _generate_beam_msh(
    output_dir: str,
    length: float = 1.0,
    width: float = 0.1,
    height: float = 0.01,
    lc: float = 0.1,
) -> str:
    """Generate a rectangular beam mesh with gmsh (inline, no demo/beam import)."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.model.add("beam")

    L, B, H = length, width, height
    B2 = B / 2
    H2 = H / 2

    occ = gmsh.model.occ
    p1 = occ.addPoint(0, -B2, -H2, lc)
    p2 = occ.addPoint(L, -B2, -H2, lc)
    p3 = occ.addPoint(L, B2, -H2, lc)
    p4 = occ.addPoint(0, B2, -H2, lc)
    p5 = occ.addPoint(0, -B2, H2, lc)
    p6 = occ.addPoint(L, -B2, H2, lc)
    p7 = occ.addPoint(L, B2, H2, lc)
    p8 = occ.addPoint(0, B2, H2, lc)

    e1 = occ.addLine(p1, p2)
    e2 = occ.addLine(p2, p3)
    e3 = occ.addLine(p3, p4)
    e4 = occ.addLine(p4, p1)
    e5 = occ.addLine(p5, p6)
    e6 = occ.addLine(p6, p7)
    e7 = occ.addLine(p7, p8)
    e8 = occ.addLine(p8, p5)
    e9 = occ.addLine(p1, p5)
    e10 = occ.addLine(p2, p6)
    e11 = occ.addLine(p3, p7)
    e12 = occ.addLine(p4, p8)

    bottom_loop = occ.addCurveLoop([e1, e2, e3, e4])
    bottom = occ.addSurfaceFilling(bottom_loop)
    top_loop = occ.addCurveLoop([e5, e6, e7, e8])
    top = occ.addSurfaceFilling(top_loop)
    front_loop = occ.addCurveLoop([e1, e10, e5, e9])
    front = occ.addSurfaceFilling(front_loop)
    back_loop = occ.addCurveLoop([e3, e11, e7, e12])
    back = occ.addSurfaceFilling(back_loop)
    left_loop = occ.addCurveLoop([e4, e12, e8, e9])
    left = occ.addSurfaceFilling(left_loop)
    right_loop = occ.addCurveLoop([e2, e10, e6, e11])
    right = occ.addSurfaceFilling(right_loop)

    surfaces = [bottom, top, front, back, left, right]
    surface_loop = occ.addSurfaceLoop(surfaces)
    volume_tag = occ.addVolume([surface_loop])
    occ.synchronize()

    gmsh.model.addPhysicalGroup(3, [volume_tag])
    gmsh.model.setPhysicalName(3, volume_tag, "Beam")
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)

    msh_path = os.path.join(output_dir, "beam.msh")
    gmsh.write(msh_path)
    gmsh.finalize()
    return msh_path


def _run_beam_validation() -> tuple:
    """Run cantilever beam FEM vs analytical validation.

    Returns (ok: bool, details: dict).
    """
    import numpy as np
    from dolfinx.io import gmsh as dgmsh
    from mpi4py import MPI

    output_dir = tempfile.mkdtemp(prefix="beam_validate_")
    mesh_file = _generate_beam_msh(
        output_dir, length=1.0, width=0.1, height=0.01, lc=0.1
    )

    mesh_data = dgmsh.read_from_msh(mesh_file, MPI.COMM_WORLD, rank=0, gdim=3)
    domain = mesh_data.mesh

    material = MaterialConfig(
        youngs_modulus=210e9,
        density=7850.0,
        poisson_ratio=0.0,
    )
    bc_config = BCConfig(
        mode="axial_plane",
        axis="x",
        plane_value=0.0,
        plane_tol=1e-6,
    )
    solver_config = SolverConfig(
        num_eigenvalues=10,
        tolerance=1e-6,
        element_degree=2,
        solver_backend="scipy",
    )

    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    mesh_coords = domain.geometry.x
    mode_info = []
    for i, (freq, ev) in enumerate(zip(frequencies, eigenvectors)):
        info = classify_mode(ev, mesh_coords)
        info["fem_freq"] = float(freq)
        info["mode_num"] = i + 1
        mode_info.append(info)

    bending_z_modes = [m for m in mode_info if m["type"] == "bending_z"]

    # Analytical reference (cantilever, bending about y-axis -> displacement in z)
    class _Beam:
        youngs_modulus = 210e9
        density = 7850.0
        length = 1.0
        cross_section_area = 0.1 * 0.01
        moment_of_inertia_y = (0.1 * 0.01**3) / 12
        moment_of_inertia_z = (0.01 * 0.1**3) / 12

    analytical_freqs = analytical_frequencies_cantilever(
        _Beam(), solver_config.num_eigenvalues, axis="y"
    )

    num_compare = min(len(analytical_freqs), len(bending_z_modes))
    if num_compare < 2:
        return False, {
            "error": f"Expected >= 2 bending_z modes, got {len(bending_z_modes)}",
            "frequencies": [float(f) for f in frequencies],
        }

    deviations = []
    ok = True
    for i in range(num_compare):
        fem_freq = bending_z_modes[i]["fem_freq"]
        ana_freq = float(analytical_freqs[i])
        error_percent = abs(fem_freq - ana_freq) / ana_freq * 100 if ana_freq != 0 else 0.0
        deviations.append({
            "mode": i + 1,
            "fem_hz": fem_freq,
            "analytical_hz": ana_freq,
            "error_pct": error_percent,
        })
        if error_percent >= TOLERANCE_PCT:
            ok = False

    return ok, {
        "frequencies": [float(f) for f in frequencies],
        "deviations": deviations,
        "num_bending_z_modes": len(bending_z_modes),
    }


def _run_testcase_validation(full: bool = False) -> tuple:
    """Run Laval disc validation.

    Returns (ok: bool, details: dict).
    """
    try:
        import dolfinx  # noqa: F401
    except ImportError:
        return None, {"skip": "dolfinx not available; skipping testcase validation"}

    if os.environ.get("RUN_TESTCASE_VALIDATION") != "1":
        return None, {
            "skip": "Set RUN_TESTCASE_VALIDATION=1 to run testcase validation (heavyweight)"
        }

    if full:
        from eigenfrequencies.validation.testcase.laval import (
            EXPERIMENT_HZ,
            run_validation,
        )

        result = run_validation()
        ok = True
        deviations = []
        for label, exp_hz in EXPERIMENT_HZ.items():
            if exp_hz is None:
                continue
            entry = result["comparison"][label]
            err_pct = abs(entry["error_pct"])
            deviations.append({
                "label": label,
                "computed_hz": entry["computed_mean_hz"],
                "experiment_hz": exp_hz,
                "error_pct": entry["error_pct"],
            })
            if err_pct > TOLERANCE_PCT:
                ok = False

        return ok, {
            "rigid_modes_removed": result["rigid_modes_removed"],
            "elastic_frequencies_hz": result["elastic_frequencies_hz"],
            "deviations": deviations,
        }

    # Lightweight coarse-mesh sanity check
    import numpy as np

    from eigenfrequencies.io import load_and_prepare_mesh

    _REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
    msh_path = os.path.join(_REPO_ROOT, "turbine_runner", "data", "testcase_coarse.msh")
    if not os.path.isfile(msh_path):
        return False, {"error": f"Coarse mesh not found at {msh_path}"}

    mesh_config = MeshConfig(msh_path=msh_path)
    material = MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
    bc_config = BCConfig(mode="free")
    solver_config = SolverConfig(
        num_eigenvalues=16,
        tolerance=1e-6,
        element_degree=1,
        solver_backend="scipy",
    )

    domain = load_and_prepare_mesh(mesh_config)
    solver = ModalSolver(domain, material, bc_config, solver_config)
    eigenvalues, eigenvectors = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)

    rigid_threshold_hz = 1.0
    keep = [i for i, f in enumerate(frequencies) if f >= rigid_threshold_hz]
    elastic_frequencies = [float(frequencies[i]) for i in keep]

    if len(elastic_frequencies) < 9:
        return False, {
            "error": f"Expected >= 9 elastic modes, got {len(elastic_frequencies)}",
            "elastic_frequencies_hz": elastic_frequencies,
        }

    # Load golden reference and compare within 5%
    golden_path = os.path.join(
        _REPO_ROOT, "tests", "characterization", "golden", "testcase_coarse.json"
    )
    with open(golden_path) as fh:
        golden = json.load(fh)

    golden_freqs = golden["frequencies"]
    first_10 = elastic_frequencies[:10]
    ok = True
    deviations = []
    for i, (computed, expected) in enumerate(zip(first_10, golden_freqs)):
        rel_err = abs(computed - expected) / abs(expected) if expected != 0 else abs(computed)
        err_pct = rel_err * 100
        deviations.append({
            "mode": i + 1,
            "computed_hz": computed,
            "golden_hz": expected,
            "error_pct": err_pct,
        })
        if err_pct > TOLERANCE_PCT:
            ok = False

    return ok, {
        "rigid_modes_removed": len(frequencies) - len(elastic_frequencies),
        "elastic_frequencies_hz": elastic_frequencies,
        "deviations": deviations,
    }


@app.command()
def solve(
    config: Path = typer.Option(..., "--config", help="Path to YAML config file"),
    mesh: Optional[Path] = typer.Option(None, "--mesh", help="Override mesh path from config"),
    out: Optional[Path] = typer.Option(None, "--out", help="Override output directory from config"),
    json_output: bool = typer.Option(False, "--json", help="Emit compact JSON to stdout"),
) -> None:
    """Run modal analysis from a YAML config file."""
    try:
        run_cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"Config error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)
    except Exception as exc:
        typer.echo(f"Failed to load config: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    # Override mesh path if provided
    if mesh is not None:
        run_cfg.mesh.msh_path = str(mesh)

    # Override output directory if provided
    if out is not None:
        run_cfg.output.output_dir = str(out)

    try:
        domain = load_and_prepare_mesh(run_cfg.mesh)
    except Exception as exc:
        typer.echo(f"Mesh error: {exc}", err=True)
        raise typer.Exit(EXIT_SOLVE_ERROR)

    try:
        solver = ModalSolver(domain, run_cfg.material, run_cfg.bc, run_cfg.solver)
        eigenvalues, eigenvectors = solver.solve()
        frequencies = solver.compute_frequencies(eigenvalues)
    except Exception as exc:
        if SolverConfigError is not None and isinstance(exc, SolverConfigError):
            typer.echo(f"Solver config error: {exc}", err=True)
        else:
            typer.echo(f"Solve error: {exc}", err=True)
        raise typer.Exit(EXIT_SOLVE_ERROR)

    # Write results
    os.makedirs(run_cfg.output.output_dir, exist_ok=True)
    json_path = os.path.join(run_cfg.output.output_dir, run_cfg.output.results_json)
    prov = provenance.generate(run_cfg)
    write_payload = {
        "frequencies_hz": [float(f) for f in frequencies],
        "eigenvalues": [float(ev) for ev in eigenvalues],
        "provenance": prov,
    }
    with open(json_path, "w") as fh:
        json.dump(write_payload, fh, indent=2)

    if run_cfg.output.save_xdmf and write_results_xdmf_vtk is not None:
        try:
            write_results_xdmf_vtk(solver, frequencies, eigenvectors, run_cfg.output)
        except Exception as exc:
            typer.echo(f"XDMF/VTK write warning: {exc}", err=True)

    if json_output:
        typer.echo(
            json.dumps(
                {"frequencies_hz": [float(f) for f in frequencies]}, separators=(",", ":")
            )
        )
    else:
        typer.echo("Frequencies (Hz):")
        for i, f in enumerate(frequencies):
            typer.echo(f"  Mode {i + 1}: {f:.4f} Hz")

    raise typer.Exit(EXIT_OK)


@app.command()
def validate(
    suite: str = typer.Option(..., "--suite", help="Validation suite: beam or testcase"),
    full: bool = typer.Option(False, "--full", help="Force the big-RAM Laval case"),
) -> None:
    """Run a validation suite and report pass/fail."""
    if suite not in ("beam", "testcase"):
        typer.echo(f"Unknown suite: {suite!r}. Choose 'beam' or 'testcase'.", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if suite == "beam":
        try:
            ok, details = _run_beam_validation()
        except Exception as exc:
            typer.echo(f"Beam validation error: {exc}", err=True)
            raise typer.Exit(EXIT_SOLVE_ERROR)

        if ok:
            typer.echo("Beam validation PASSED (all modes within 5% tolerance)")
            raise typer.Exit(EXIT_OK)
        else:
            typer.echo("Beam validation FAILED (deviation exceeds 5% tolerance)")
            for d in details.get("deviations", []):
                typer.echo(
                    f"  Mode {d['mode']}: FEM={d['fem_hz']:.4f} Hz, "
                    f"Analytical={d['analytical_hz']:.4f} Hz, "
                    f"Error={d['error_pct']:.2f}%"
                )
            raise typer.Exit(EXIT_VALIDATION_DEVIATION)

    if suite == "testcase":
        try:
            ok, details = _run_testcase_validation(full=full)
        except Exception as exc:
            typer.echo(f"Testcase validation error: {exc}", err=True)
            raise typer.Exit(EXIT_SOLVE_ERROR)

        if ok is None:
            typer.echo(details["skip"])
            raise typer.Exit(EXIT_OK)

        if ok:
            typer.echo("Testcase validation PASSED (all modes within 5% tolerance)")
            raise typer.Exit(EXIT_OK)
        else:
            typer.echo("Testcase validation FAILED (deviation exceeds 5% tolerance)")
            for d in details.get("deviations", []):
                label = d.get("label")
                if label is None:
                    label = f"Mode {d.get('mode', '?')}"
                computed = d.get("computed_hz", d.get("fem_hz"))
                reference = d.get("experiment_hz", d.get("analytical_hz", d.get("golden_hz")))
                typer.echo(
                    f"  {label}: "
                    f"Computed={computed:.4f} Hz, "
                    f"Reference={reference:.4f} Hz, "
                    f"Error={d['error_pct']:.2f}%"
                )
            raise typer.Exit(EXIT_VALIDATION_DEVIATION)


@app.command()
def optimize(
    config: Path = typer.Option(..., "--config", help="Path to YAML config file"),
    optimizer: str = typer.Option(..., "--optimizer", help="Optimizer name: de|pso|cmaes|bo|rl"),
    islands: int = typer.Option(1, "--islands", help="Number of islands (default 1)"),
    workers: int = typer.Option(1, "--workers", help="Parallel evaluation workers (default 1)"),
    evaluator: str = typer.Option(
        "process_pool",
        "--evaluator",
        help="Evaluator backend: process_pool (local) | pyro5 (cluster)",
    ),
    uri_dir: Optional[Path] = typer.Option(
        None,
        "--uri-dir",
        help="Directory with worker_N.uri files (required for --evaluator pyro5)",
    ),
    resume: Optional[Path] = typer.Option(None, "--resume", help="Path to prior state dict JSON"),
    budget: Optional[int] = typer.Option(None, "--budget", help="Evaluation budget"),
    out: Optional[Path] = typer.Option(None, "--out", help="Override output directory from config"),
) -> None:
    """Run design optimization from a YAML config file.

    For cluster runs, start workers first:

        eigenfrequencies cluster worker 0 --uri-dir /path/to/uris &

    Then run the coordinator:

        eigenfrequencies optimize --config tistos.yaml --optimizer de \\
            --evaluator pyro5 --uri-dir /path/to/uris --workers N
    """
    try:
        run_cfg = load_config(config)
    except ConfigError as exc:
        typer.echo(f"Config error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)
    except Exception as exc:
        typer.echo(f"Failed to load config: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if islands > 1:
        typer.echo("Island optimization not implemented yet", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if create_optimizer is None:
        typer.echo("Optimization package not available", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    bounds = run_cfg.design.bounds
    if not bounds:
        typer.echo("Config has no design parameters (design.params is empty)", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    de_cfg = run_cfg.de
    opt_config = {
        "bounds": bounds,
        "pop_size": de_cfg.pop_size,
        "F": de_cfg.mutation,
        "CR": de_cfg.crossover,
        "max_generations": de_cfg.max_generations,
        "seed": de_cfg.seed,
        "x0": run_cfg.design.x0,
    }

    try:
        opt = create_optimizer(optimizer, opt_config)
    except (ValueError, RuntimeError) as exc:
        msg = str(exc)
        if "not installed" in msg.lower() or "unavailable" in msg.lower():
            typer.echo(f"Optimizer '{optimizer}' not installed/not implemented yet: {msg}", err=True)
        else:
            typer.echo(msg, err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if resume is not None:
        if not resume.is_file():
            typer.echo(f"Resume file not found: {resume}", err=True)
            raise typer.Exit(EXIT_CONFIG_ERROR)
        try:
            with open(resume) as fh:
                state = json.load(fh)
            opt.load_state(state)
        except Exception as exc:
            typer.echo(f"Failed to load resume state: {exc}", err=True)
            raise typer.Exit(EXIT_CONFIG_ERROR)

    if budget is None:
        budget = de_cfg.pop_size * de_cfg.max_generations

    # ── Build evaluator pool ────────────────────────────────────────────────
    labels = run_cfg.design.labels

    if evaluator == "pyro5":
        if uri_dir is None:
            uri_dir_str = os.environ.get("DE_URI_DIR")
            if not uri_dir_str:
                typer.echo(
                    "pyro5 evaluator requires --uri-dir or DE_URI_DIR env var", err=True
                )
                raise typer.Exit(EXIT_CONFIG_ERROR)
        else:
            uri_dir_str = str(uri_dir)
        try:
            from eigenfrequencies.optimize.evaluators.pyro_pool import Pyro5Pool
        except ImportError as exc:
            typer.echo(f"Pyro5 not installed: {exc}", err=True)
            raise typer.Exit(EXIT_CONFIG_ERROR)
        pool = Pyro5Pool(uri_dir=uri_dir_str, n_workers=workers, labels=labels)
        typer.echo(f"[optimize] using Pyro5Pool  uri_dir={uri_dir_str}  workers={workers}")
    elif evaluator == "process_pool":
        from eigenfrequencies.optimize.evaluators.process_pool import ProcessPool

        def _local_eval(design):
            return sum(v * v for v in design.vector)

        pool = ProcessPool(n_workers=workers, evaluator=_local_eval)
        typer.echo(f"[optimize] using ProcessPool  workers={workers}  (dummy evaluator)")
    else:
        typer.echo(f"Unknown evaluator '{evaluator}'. Choose: process_pool | pyro5", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    # ── Optimisation loop ────────────────────────────────────────────────────
    history: list[dict] = []
    evaluations = 0
    try:
        while evaluations < budget:
            n = min(de_cfg.pop_size, budget - evaluations)
            designs = opt.ask(n)
            try:
                objectives = pool.evaluate(designs)
            except Exception as exc:
                typer.echo(f"Evaluation error (generation {len(history)}): {exc}", err=True)
                raise typer.Exit(EXIT_SOLVE_ERROR)
            opt.tell(designs, objectives)
            evaluations += n
            best = min(objectives)
            typer.echo(
                f"[gen {len(history)}] best={best:.6f}  mean={sum(objectives)/len(objectives):.6f}"
            )
            history.append({
                "generation": len(history),
                "designs": [d.vector for d in designs],
                "objectives": objectives,
            })
    finally:
        pool.shutdown()

    result = {
        "best_design": opt.state_dict().get("best_vec", []),
        "best_objective": opt.state_dict().get("best_obj", float("inf")),
        "evaluations": evaluations,
        "budget": budget,
        "optimizer": optimizer,
        "history": history,
    }

    prov = provenance.generate(run_cfg)
    result["provenance"] = prov

    out_dir = Path(out if out is not None else run_cfg.output.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / "optimization_result.json"
    with open(result_path, "w") as fh:
        json.dump(result, fh, indent=2)

    typer.echo(f"Optimization complete. Best objective: {result['best_objective']:.6f}")
    typer.echo(f"Result written to {result_path}")
    raise typer.Exit(EXIT_OK)


@app.command()
def report(
    run_dir: Path = typer.Option(..., "--run-dir", help="Path to optimization run directory"),
) -> None:
    """Print summary report from an optimization run."""
    if not run_dir.is_dir():
        typer.echo(f"Run directory not found: {run_dir}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    result_path = run_dir / "optimization_result.json"
    if not result_path.is_file():
        typer.echo(f"Result file not found: {result_path}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    try:
        with open(result_path) as fh:
            result = json.load(fh)
    except Exception as exc:
        typer.echo(f"Failed to read result file: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    best_design = result.get("best_design", [])
    best_obj = result.get("best_objective", float("inf"))
    evaluations = result.get("evaluations", 0)
    budget = result.get("budget", 0)

    typer.echo("Optimization Report")
    typer.echo("=" * 40)
    typer.echo(f"Best design vector: {best_design}")
    typer.echo(f"Best objective value: {best_obj:.6f}")
    typer.echo(f"Evaluations: {evaluations} / {budget}")

    # Objective breakdown (placeholder for real CFD + resonance terms)
    typer.echo("\nObjective Breakdown")
    typer.echo("-" * 40)
    typer.echo(f"  combined:     {best_obj:.6f}")
    typer.echo("  resonance_term: 0.000000 (not computed in this run)")
    typer.echo("  cfd_scalar:     0.000000 (not computed in this run)")

    # Frequency table vs forbidden band (placeholder)
    typer.echo("\nFrequency Table vs Forbidden Band")
    typer.echo("-" * 40)
    typer.echo("  (Frequencies not available for sphere-function test runs)")

    # Validation reference comparison if available
    ref_path = run_dir / "validation_reference.json"
    if ref_path.is_file():
        try:
            with open(ref_path) as fh:
                ref = json.load(fh)
            typer.echo("\nValidation Reference Comparison")
            typer.echo("-" * 40)
            ref_design = ref.get("best_design", [])
            ref_obj = ref.get("best_objective", float("inf"))
            typer.echo(f"  reference design:   {ref_design}")
            typer.echo(f"  reference obj:    {ref_obj:.6f}")
            if ref_obj != 0:
                diff_pct = abs(best_obj - ref_obj) / abs(ref_obj) * 100
                typer.echo(f"  difference:       {diff_pct:.2f}%")
        except Exception:
            typer.echo("\nValidation reference present but could not be parsed.")

    raise typer.Exit(EXIT_OK)


@app.command()
def rl_export(
    history: Path = typer.Option(
        ..., "--history", help="Path to de_history*.jsonl file"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output path (default: <history>.d3)"
    ),
    reward: str = typer.Option(
        "improvement", "--reward", help="Reward mode: raw | improvement"
    ),
    bounds: Optional[str] = typer.Option(
        None, "--bounds", help="Normalisation bounds: 'lo1,lo2,... hi1,hi2,...'"
    ),
) -> None:
    """Export DE history JSONL to a d3rlpy-compatible offline RL dataset."""
    from eigenfrequencies.optimize.rl.offline_export import export_dataset

    if reward not in ("raw", "improvement"):
        typer.echo(
            f"Invalid reward mode: {reward!r}. Choose 'raw' or 'improvement'.", err=True
        )
        raise typer.Exit(EXIT_CONFIG_ERROR)

    bounds_low = None
    bounds_high = None
    if bounds is not None:
        parts = [p.strip() for p in bounds.split(",")]
        mid = len(parts) // 2
        bounds_low = [float(v) for v in parts[:mid]]
        bounds_high = [float(v) for v in parts[mid:]]
        if len(bounds_low) != len(bounds_high):
            typer.echo(
                "--bounds must have equal low and high halves (e.g. '0,0 1,1')",
                err=True,
            )
            raise typer.Exit(EXIT_CONFIG_ERROR)

    try:
        n_rows, skipped = export_dataset(
            history_path=history,
            out_path=out,
            reward_mode=reward,
            bounds_low=bounds_low,
            bounds_high=bounds_high,
        )
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    out_path = out or history.with_suffix(".d3")
    typer.echo(f"Exported {n_rows} rows -> {out_path}")
    if skipped:
        typer.echo(f"Skipped {skipped} malformed line(s)")


dtoo_app = typer.Typer(help="dtOO mesh helper utilities")
app.add_typer(dtoo_app, name="dtoo")


@dtoo_app.command()
def discover_axis(
    mesh: Path = typer.Option(..., "--mesh", help="Path to mesh (.msh) file"),
) -> None:
    """Print the discovered rotation axis and confidence from a mesh file.

    Uses the mesh bounding-box spans to identify which axis is the rotation
    axis (longest span = rotation axis) and reports a confidence score based
    on the ratio of longest to shortest span.
    """
    if not mesh.exists():
        typer.echo(f"Mesh file not found: {mesh}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    try:
        from eigenfrequencies.config import MeshConfig
        from eigenfrequencies.io.axis import inspect_mesh

        mesh_cfg = MeshConfig(msh_path=str(mesh), gdim=3)
        result = inspect_mesh(mesh_cfg, verbose=False)
    except Exception as exc:  # pragma: no cover — covers dolfinx/mpi4py not present
        typer.echo(f"Mesh error: {exc}", err=True)
        raise typer.Exit(EXIT_SOLVE_ERROR)

    axes = result["axes"]
    spans = {name: info["span"] for name, info in axes.items()}
    longest = max(spans, key=spans.__getitem__)
    shortest = min(spans, key=spans.__getitem__)
    confidence = spans[longest] / spans[shortest] if spans[shortest] > 0 else 0.0

    typer.echo(f"rotation_axis: {longest}")
    typer.echo(f"confidence: {confidence:.4f}")
    typer.echo("axis_details:")
    for name in "xyz":
        info = axes[name]
        marker = " <-- rotation_axis" if name == longest else ""
        typer.echo(
            f"  {name}: min={info['min']:+.4f}  max={info['max']:+.4f}"
            f"  span={info['span']:.4f}{marker}"
        )

    raise typer.Exit(EXIT_OK)


@dtoo_app.command()
def measure_scale(
    mesh: Path = typer.Option(..., "--mesh", help="Path to mesh (.msh) file"),
    physical_length: float = typer.Option(
        ...,
        "--physical-length",
        help="Known physical length of the feature (in metres)",
    ),
    feature_desc: str = typer.Option(
        ...,
        "--feature-desc",
        help="Human-readable description of the measured feature",
    ),
) -> None:
    """Measure a mesh bbox dimension and propose a mesh_scale_factor.

    Loads the mesh, finds the longest axis span, computes
    ``mesh_scale_factor = physical_length / mesh_length``, and prints a YAML
    snippet ready to paste into the machine YAML ``mesh_scale_factor`` field.
    """
    if physical_length <= 0:
        typer.echo(
            f"Physical length must be positive, got {physical_length}", err=True
        )
        raise typer.Exit(EXIT_CONFIG_ERROR)

    if not mesh.exists():
        typer.echo(f"Mesh file not found: {mesh}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    try:
        from eigenfrequencies.config import MeshConfig
        from eigenfrequencies.io.axis import inspect_mesh

        mesh_cfg = MeshConfig(msh_path=str(mesh), gdim=3)
        result = inspect_mesh(mesh_cfg, verbose=False)
    except Exception as exc:  # pragma: no cover
        typer.echo(f"Mesh error: {exc}", err=True)
        raise typer.Exit(EXIT_SOLVE_ERROR)

    axes = result["axes"]
    spans = {name: info["span"] for name, info in axes.items()}
    longest = max(spans, key=spans.__getitem__)
    mesh_length = spans[longest]

    if mesh_length <= 0:
        typer.echo(
            f"Mesh axis span is zero or negative for axis '{longest}':"
            f" {mesh_length}",
            err=True,
        )
        raise typer.Exit(EXIT_SOLVE_ERROR)

    scale_factor = physical_length / mesh_length

    typer.echo("# YAML snippet for machine file")
    typer.echo("# Feature measured: " + feature_desc)
    typer.echo(f"# Longest axis: {longest}  (mesh span: {mesh_length:.6f} m)")
    typer.echo(f"# Physical length: {physical_length:.6f} m")
    typer.echo(f"mesh_scale_factor: {scale_factor:.8f}  # {feature_desc}")

    raise typer.Exit(EXIT_OK)


cluster_app = typer.Typer(help="Cluster worker utilities for distributed optimisation")
app.add_typer(cluster_app, name="cluster")


@cluster_app.command()
def worker(
    worker_id: int = typer.Argument(..., help="Worker index (unique per SLURM task)"),
    uri_dir: Path = typer.Option(
        ...,
        "--uri-dir",
        help="Shared-filesystem directory where the URI file will be written",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="YAML RunConfig for OptimizationConfig / ObjectiveConfig (optional)",
    ),
) -> None:
    """Start a Pyro5 evaluation worker and register its URI on the shared filesystem.

    Run one instance per SLURM task:

        srun -n1 eigenfrequencies cluster worker $SLURM_PROCID --uri-dir $DE_URI_DIR &

    The coordinator discovers workers by reading *.uri files from --uri-dir.
    """
    try:
        from eigenfrequencies.cluster.worker import run_worker
    except ImportError as exc:
        typer.echo(f"Pyro5 not installed: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG_ERROR)

    run_worker(
        worker_id=worker_id,
        uri_dir=str(uri_dir),
        config_path=str(config) if config is not None else None,
    )


if __name__ == "__main__":
    app()
