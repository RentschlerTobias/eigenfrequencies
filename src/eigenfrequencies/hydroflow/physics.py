"""Physics behind one hydroflow-opt evaluation: geometry, modal solve, CFD.

:mod:`eigenfrequencies.hydroflow.worker` turns a candidate into an objective;
this module does the actual work and is imported lazily so the worker, the case
plugin and the contract stay testable without dtOO or dolfinx installed.

Two stages, called once per candidate:

* :func:`run_modal_stage` — dtOO builds the mechanical mesh, FEniCSx solves the
  modal problem, the eigenfrequencies come back in Hz.
* :func:`run_cfd_stage` — dtOO builds the OpenFOAM case, ``simpleFoam`` runs the
  steady solve, :func:`eigenfrequencies.io.cfd_eval.evaluate_cfd` reads the
  hydraulic objectives out of ``postProcessing/``.

Ported from the paths that have actually run on the cluster
(``turbine_runner/legacy/optimize.py``: ``_run_dtoo``, ``_run_fenicsx``,
``_run_cfd``) with three changes:

1. **Per-candidate working directory.** hydroflow-opt hands every candidate its
   own ``context.scratch_dir``; nothing is shared between evaluations. The
   frozen CFD objective of runs 6039132/6039133 came from a shared, never
   cleaned case directory (see ``.omo/evidence/task-cfd-freeze-diagnosis.md``),
   so on top of the isolation every stale artifact is removed before the solve:
   the mesh, the whole case directory, every written time step and
   ``postProcessing/``. simpleFoam skips the solve when ``endTime`` already
   exists, and a skipped solve reports the *previous* design's numbers.
2. **Runtime selection instead of hardcoded enroot.** Each stage runs
   in-process, in a plain shell, in docker, or in enroot — chosen per
   ``options`` or auto-detected from what imports. The same worker therefore
   runs on this workstation (docker) and on bwUniCluster (enroot).
3. **Configuration from the machine YAML,** not from module-level env reads.
   The boundary condition follows ``bc_template``, so naca gets its foil clamp
   and tistos its hub clamp without a second code path.

The dtOO container (``atismer/dtoo-opensuse:stable``) needs **both**
environments sourced before ``import dtOOPythonSWIG`` — OpenFOAM supplies
``libPstream.so``, ``env.sh`` sets ``CASROOT`` for ``libTKFeat``. Its
interpreter is python3.13, not 3.12. Verified against image
``sha256:25ef00d004de``; see ``.omo/notepads/phd-repo-next-steps/learnings.md``.

Host paths are mounted at their own path inside the container, so no path
translation is needed anywhere: a mesh written to ``/tmp/x/y.msh`` in the
container is at ``/tmp/x/y.msh`` on the host.

Options (the ``[case.options]`` table of the hydroflow-opt TOML)::

    work_dir      = "/scratch/eval"   # default: context.scratch_dir
    [case.options.dtoo]
    runtime  = "auto"                 # auto|inprocess|native|docker|enroot
    image    = "atismer/dtoo-opensuse:stable"
    container= "pyxis_dtoo"           # enroot container name
    case_dir = "/dtOO/build/test/tistos"
    timeout  = 900
    keep_build_log = false           # dtOO's own trace, ~39 MB per candidate
    [case.options.modal]
    runtime  = "auto"                 # auto|inprocess|native|docker|enroot
    image    = "dolfinx/dolfinx:stable"
    container= "pyxis_fenicsx"
    element_degree = 2
    num_eigenvalues = 10
    solver_backend = "scipy"
    [case.options.cfd]
    stage_dir = "…/turbine_runner/cfd"   # tistos_files/ + xml/ + boundaryData/
    state     = "hydroflow"
    procs     = 4                        # default: context.resources.mpi_ranks
    timeout   = 1800

This module also serves as the in-container entry point
(``physics.py dtoo-export SPEC`` / ``physics.py modal SPEC``), so its
module-level imports stay stdlib-only: inside the containers the package is not
installed and is reached through a ``sys.path`` bootstrap.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

#: dtOO + OpenFOAM image. Same image on the cluster, imported as an enroot
#: container by ``cluster/export_dtoo_enroot.sh``.
DTOO_IMAGE = "atismer/dtoo-opensuse:stable"
DTOO_CONTAINER = "pyxis_dtoo"

#: FEniCSx image for the modal solve. The image has to carry the ``gmsh``
#: Python module on top of dolfinx — ``docker/fenicsx.Dockerfile`` builds
#: exactly that; point ``options.modal.image`` at the built tag.
FENICSX_IMAGE = "dolfinx/dolfinx:stable"
FENICSX_CONTAINER = "pyxis_fenicsx"

#: Both sources are required — with neither, ``import dtOOPythonSWIG`` fails on
#: ``libPstream.so``; with only OpenFOAM, on ``libTKFeat.so.7.9``.
DTOO_SETUP = (
    "source /usr/lib/openfoam/openfoam2606/etc/bashrc",
    "source /dtOO-install/bin/env.sh",
)

#: DOLFINx/PMIx falls back to /run/user/$UID otherwise, which is unwritable in
#: a batch allocation — that is what made every worker fail on uc2n601.
FENICSX_SETUP = (
    "export HOME=/tmp",
    "export DOLFINX_CACHE_DIR=/tmp",
    "export XDG_RUNTIME_DIR=/tmp",
    "export TMPDIR=/tmp",
)

#: The dtOO image ships python3.13; ``python3`` resolves to the same binary.
CONTAINER_PYTHON = "python3.13"

#: dtOO case directories inside the image: ``/dtOO/build/test/{tistos,naca}``.
#: The machine YAML records the *cluster* path (``~/dtOO/build/test/…``), which
#: does not exist inside the container.
CONTAINER_CASE_ROOT = "/dtOO/build/test"

#: Marker line the in-container entry points print for the host to parse.
RESULT_MARKER = "RESULT_JSON "

_RUNTIME_KINDS = ("auto", "inprocess", "native", "docker", "enroot")

#: Keys under ``[case.options.cfd]`` that belong to *this* module rather than to
#: :class:`eigenfrequencies.config.CFDConfig`. The table has two readers — the
#: worker fills the physical operating point from it, the CFD stage its
#: plumbing — and without this list neither could tell a foreign key from a
#: typo. A silently ignored ``w_resonanc`` is how a comparison run ends up
#: incomparable without anyone noticing.
CFD_STAGE_KEYS = frozenset(
    {
        "stage_dir",
        "state",
        "case_name",
        "procs",
        "timeout",
        "solve_script",
        "mpi_launcher",
        "env",
    }
)


class StageError(RuntimeError):
    """A physics stage failed. The worker reports it as ``status: failed``."""


# ── Runtime ───────────────────────────────────────────────────────────────


@dataclass
class Runtime:
    """Where a stage runs: this interpreter, a shell, docker, or enroot.

    Attributes:
        kind: ``inprocess`` (call the code directly), ``native`` (a login shell
            on this host), ``docker``, or ``enroot``.
        image: docker image (``kind == "docker"``).
        container: enroot container name (``kind == "enroot"``).
        python: interpreter used inside the container.
        setup: shell lines sourced/exported before the command.
        args: extra arguments for ``docker run`` / ``enroot start``.
        timeout: seconds before the stage is killed.
    """

    kind: str
    image: str = ""
    container: str = ""
    python: str = CONTAINER_PYTHON
    setup: tuple[str, ...] = ()
    args: tuple[str, ...] = ()
    timeout: float = 900.0

    @property
    def containerized(self) -> bool:
        return self.kind in ("docker", "enroot")

    @classmethod
    def resolve(
        cls,
        section: dict[str, Any],
        *,
        probe_module: str,
        image: str,
        container: str,
        setup: Sequence[str],
        timeout: float,
        python: str = CONTAINER_PYTHON,
    ) -> "Runtime":
        """Build a runtime from an options section.

        ``runtime = "auto"`` (the default) picks ``inprocess`` when
        *probe_module* imports here — dolfinx in the conda env, dtOO inside the
        container — and ``docker`` otherwise. The cluster sets ``enroot``
        explicitly; no auto-detection guesses at a scheduler.
        """
        kind = str(section.get("runtime", "auto"))
        if kind not in _RUNTIME_KINDS:
            raise StageError(
                f"unknown runtime {kind!r}; expected one of {', '.join(_RUNTIME_KINDS)}"
            )
        if kind == "auto":
            kind = "inprocess" if _module_available(probe_module) else "docker"
        return cls(
            kind=kind,
            image=str(section.get("image", image)),
            container=str(section.get("container", container)),
            python=str(section.get("python", python)),
            setup=tuple(section.get("setup", setup)),
            args=tuple(section.get("args", ())),
            timeout=float(section.get("timeout", timeout)),
        )

    def command(
        self,
        argv: Sequence[str],
        *,
        workdir: str | Path,
        mounts: Sequence[str | Path] = (),
        env: dict[str, str] | None = None,
    ) -> list[str]:
        """Wrap *argv* into the command that runs it in this runtime.

        Every mount maps a host path onto the identical container path, so
        paths in *argv* and in the produced artifacts mean the same thing on
        both sides. Nonexistent mount sources are skipped: the dtOO case
        directory lives inside the image, not on the host.
        """
        if self.kind == "inprocess":
            raise StageError("in-process runtime has no shell command")

        lines = list(self.setup)
        for key, value in (env or {}).items():
            lines.append(f"export {key}={shlex.quote(str(value))}")
        lines.append(shlex.join(str(a) for a in argv))
        # ';' rather than '&&': sourcing an OpenFOAM bashrc reports a non-zero
        # status on a noisy shell, and the exit code that matters is the last
        # command's.
        script = "; ".join(lines)

        if self.kind == "native":
            return ["bash", "-lc", f"cd {shlex.quote(str(workdir))}; {script}"]

        bind = _existing_paths(mounts)
        if self.kind == "docker":
            cmd = ["docker", "run", "--rm", "-w", str(workdir)]
            for path in bind:
                cmd += ["-v", f"{path}:{path}"]
            cmd += list(self.args)
            cmd += [self.image, "bash", "-lc", script]
            return cmd

        cmd = ["enroot", "start"]
        for path in bind:
            cmd += ["-m", f"{path}:{path}"]
        extra = list(self.args)
        # Both images run as root internally — dtOO sources its environment from
        # /dtOO-install, dolfinx keeps its packages in /usr. Without --root
        # enroot cannot drop privileges and refuses to mount the image at all:
        # "mount: drop permissions failed" and the container never starts.
        if "--root" not in extra:
            extra.insert(0, "--root")
        cmd += extra
        # Same reason as the mounts: "~/enroot-images/x.sqsh" reaches execve
        # unexpanded and enroot then reports a container it cannot find.
        cmd += [
            _expand(self.container),
            "bash",
            "-c",
            f"cd {shlex.quote(str(workdir))}; {script}",
        ]
        return cmd


def _module_available(name: str) -> bool:
    """True if *name* can be imported here, without importing it."""
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _expand(path: str | Path) -> str:
    """Expand ``~`` and ``$VARS`` in a path written by hand into a TOML.

    Neither TOML nor execve does this: a config saying ``$WS/enroot-images/x.sqsh``
    reaches enroot verbatim and it reports a container it cannot find.
    """
    return os.path.expandvars(os.path.expanduser(str(path)))


def _existing_paths(paths: Sequence[str | Path]) -> list[str]:
    """Absolute, deduplicated, order-preserving list of the paths that exist."""
    seen: list[str] = []
    for path in paths:
        if not path:
            continue
        # expanduser: these come from a TOML written by hand, and there is no
        # shell between here and execve to expand a leading ~.
        resolved = str(Path(_expand(path)).resolve())
        if resolved not in seen and os.path.exists(resolved):
            seen.append(resolved)
    return seen


def _run(cmd: Sequence[str], *, stage: str, timeout: float, log_path: Path) -> str:
    """Run *cmd*, tee stdout+stderr into *log_path*, return the output.

    Raises:
        StageError: on a non-zero exit or a timeout, with the log tail attached
            — the message ends up in ``result.json``'s ``error`` field, which is
            all the orchestrator ever shows of a failed candidate.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            list(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise StageError(f"{stage}: cannot execute {cmd[0]!r} ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        output = exc.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        log_path.write_text(output, encoding="utf-8")
        raise StageError(f"{stage}: timed out after {timeout:g} s") from exc

    log_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise StageError(
            f"{stage}: exit {proc.returncode}\n{_tail(proc.stdout)}"
        )
    return proc.stdout


def _tail(text: str, limit: int = 4000) -> str:
    """Last *limit* characters — enough to see the error, short enough to log."""
    return text[-limit:] if len(text) > limit else text


def _parse_result_line(output: str, *, stage: str) -> dict:
    """Return the payload of the last ``RESULT_JSON`` line in *output*."""
    for line in reversed(output.splitlines()):
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])
    raise StageError(f"{stage}: no {RESULT_MARKER.strip()} line in output\n{_tail(output)}")


# ── Shared helpers ────────────────────────────────────────────────────────


def _section(options: dict[str, Any], name: str) -> dict[str, Any]:
    """Return the ``options[name]`` sub-table, or an empty one."""
    value = options.get(name) or {}
    if not isinstance(value, dict):
        raise StageError(f"options.{name} must be a table, got {type(value).__name__}")
    return dict(value)


def work_dir(options: dict[str, Any], context: dict[str, Any] | None) -> Path:
    """Working directory for one candidate.

    hydroflow-opt creates ``<scratch_dir>/<candidate_id>`` per candidate and
    passes it as ``context.scratch_dir``; using it is what keeps two designs
    from ever sharing an OpenFOAM case.
    """
    explicit = options.get("work_dir")
    if explicit:
        path = Path(explicit)
    elif context and context.get("scratch_dir"):
        path = Path(str(context["scratch_dir"]))
    else:
        path = Path(tempfile.mkdtemp(prefix="eigenfrequencies-eval-"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _repo_root() -> Path:
    """Repository root — src/eigenfrequencies/hydroflow/physics.py → up 4."""
    override = os.environ.get("EIGENFREQUENCIES_REPO")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3]


def _case_dir(machine_cfg, dtoo_opts: dict[str, Any], runtime: Runtime) -> str:
    """dtOO case directory for this runtime.

    The machine YAML holds the path as it exists on the cluster login node
    (``~/dtOO/build/test/tistos``). Inside the image the cases sit at
    ``/dtOO/build/test/<name>``, so a containerized run falls back to that
    unless ``options.dtoo.case_dir`` says otherwise.
    """
    explicit = dtoo_opts.get("case_dir")
    if explicit:
        return _expand(explicit)
    case_dir = os.path.expanduser(machine_cfg.case_dir)
    if runtime.containerized and not os.path.isdir(case_dir):
        return f"{CONTAINER_CASE_ROOT}/{machine_cfg.name}"
    return case_dir


def _apply_overrides(cfg, overrides: dict[str, Any], *, label: str):
    """Set dataclass fields from an options table, rejecting unknown keys."""
    for key, value in overrides.items():
        if not hasattr(cfg, key):
            raise StageError(f"options.{label} has no field {key!r}")
        setattr(cfg, key, value)
    return cfg


# ── Stage 1: dtOO geometry export ─────────────────────────────────────────


def _dtoo_export(spec: dict[str, Any]) -> str:
    """Run the dtOO export described by *spec*, return the mesh path.

    Shared by the in-process path and the in-container entry point, so both
    build the geometry with exactly the same code. ``mesh_scale_factor`` is
    deliberately not applied here: scaling needs the ``gmsh`` Python module,
    which the dtOO image does not ship. The host applies it afterwards.
    """
    from eigenfrequencies.adapters.dtoo.export import run_dtoo_export
    from eigenfrequencies.adapters.dtoo.machine_yaml import MachineAdapterConfig

    config = MachineAdapterConfig(
        name=spec["name"],
        case_dir=spec["case_dir"],
        state=spec["state"],
        mech_volume=spec["mech_volume"],
        adjust_plugin=spec.get("adjust_plugin", ""),
        design={},
        mesh_scale_factor=1.0,
    )
    return run_dtoo_export(config, spec.get("design") or {}, spec["output_msh"])


def export_mesh(
    machine_cfg,
    parameters: dict[str, float],
    options: dict[str, Any],
    directory: Path,
    runtime: Runtime | None = None,
) -> tuple[str, dict[str, Any]]:
    """Build the mechanical mesh for one design.

    Args:
        machine_cfg: parsed machine YAML.
        parameters: ``{dtOO const-value label: value}`` for this candidate.
        options: the ``[case.options]`` table.
        directory: per-candidate working directory.
        runtime: override; resolved from ``options.dtoo`` when omitted.

    Returns:
        ``(msh_path, meta)``.

    Raises:
        StageError: if dtOO fails or writes no mesh.
    """
    dtoo_opts = _section(options, "dtoo")
    runtime = runtime or Runtime.resolve(
        dtoo_opts,
        probe_module="dtOOPythonSWIG",
        image=DTOO_IMAGE,
        container=DTOO_CONTAINER,
        setup=DTOO_SETUP,
        timeout=900.0,
    )

    mesh_dir = directory / "mesh"
    mesh_dir.mkdir(parents=True, exist_ok=True)
    msh_path = mesh_dir / f"{machine_cfg.name}.msh"
    # A stale mesh from a previous candidate would be read as this one's.
    if msh_path.exists():
        msh_path.unlink()

    case_dir = _case_dir(machine_cfg, dtoo_opts, runtime)
    spec = {
        "name": machine_cfg.name,
        "case_dir": case_dir,
        "state": str(dtoo_opts.get("state", machine_cfg.state)),
        "mech_volume": str(dtoo_opts.get("mech_volume", machine_cfg.mech_volume)),
        "adjust_plugin": str(dtoo_opts.get("adjust_plugin", machine_cfg.adjust_plugin)),
        "design": {str(k): float(v) for k, v in parameters.items()},
        "output_msh": str(msh_path),
    }

    if runtime.kind == "inprocess":
        try:
            _dtoo_export(spec)
        except Exception as exc:  # noqa: BLE001 — every dtOO failure is a failed candidate
            raise StageError(f"dtoo export: {type(exc).__name__}: {exc}") from exc
    else:
        spec_path = mesh_dir / "dtoo_spec.json"
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        argv = [runtime.python, str(Path(__file__).resolve()), "dtoo-export", str(spec_path)]
        _run(
            runtime.command(
                argv,
                workdir=directory,
                mounts=[_repo_root(), directory, case_dir],
            ),
            stage="dtoo export",
            timeout=runtime.timeout,
            log_path=directory / "logs" / "dtoo_export.log",
        )

    if not msh_path.is_file():
        raise StageError(f"dtoo export: no mesh at {msh_path}")

    # dtOO's own trace is ~39 MB per tistos evaluation, twice the mesh it
    # produced. A DE run of a few hundred candidates would leave tens of GB of
    # scratch nobody reads — but the trace of a *failed* export is exactly what
    # one does read, and that path never gets here.
    build_log = mesh_dir / "dtoo_build.log"
    build_log_bytes = build_log.stat().st_size if build_log.is_file() else 0
    if build_log_bytes and not dtoo_opts.get("keep_build_log"):
        build_log.unlink()

    final_path = str(msh_path)
    scale = float(machine_cfg.mesh_scale_factor)
    if scale != 1.0:
        # Host-side: the scaling helper needs the gmsh Python module.
        from eigenfrequencies.adapters.dtoo.export import _apply_mesh_scale_factor

        final_path = _apply_mesh_scale_factor(final_path, scale)

    meta = {
        "msh_path": final_path,
        "case_dir": case_dir,
        "state": spec["state"],
        "mech_volume": spec["mech_volume"],
        "runtime": runtime.kind,
        "mesh_scale_factor": scale,
        "msh_bytes": os.path.getsize(final_path),
        "dtoo_log_bytes": build_log_bytes,
    }
    return final_path, meta


# ── Stage 2: modal solve ──────────────────────────────────────────────────


def _modal_solve(spec: dict[str, Any]) -> dict:
    """Solve the modal problem described by *spec*.

    Shared by the in-process path and the in-container entry point. Returns the
    payload that the entry point prints as ``RESULT_JSON``.
    """
    from eigenfrequencies.config import BCConfig, MaterialConfig, MeshConfig, SolverConfig
    from eigenfrequencies.io import load_and_prepare_mesh
    from eigenfrequencies.solver import ModalSolver

    material = MaterialConfig(**spec.get("material", {}))
    bc = BCConfig(**spec.get("bc", {}))
    mesh_cfg = MeshConfig(msh_path=spec["msh_path"], **spec.get("mesh", {}))
    solver_cfg = SolverConfig(**spec.get("solver", {}))

    domain = load_and_prepare_mesh(mesh_cfg)
    solver = ModalSolver(domain, material, bc, solver_cfg)
    eigenvalues, _ = solver.solve()
    frequencies = solver.compute_frequencies(eigenvalues)
    return {
        "ok": True,
        "frequencies_hz": [float(f) for f in frequencies],
        "n_nodes": int(domain.geometry.x.shape[0]),
    }


def solve_modal(
    msh_path: str,
    machine_cfg,
    options: dict[str, Any],
    directory: Path,
    runtime: Runtime | None = None,
) -> tuple[list[float], dict[str, Any]]:
    """Compute the eigenfrequencies of the exported mesh.

    The boundary condition comes from the machine's ``bc_template`` — foil clamp
    for naca, hub clamp for tistos — and can be overridden field by field with
    ``options.modal.bc``.

    Returns:
        ``(frequencies_hz, meta)``.

    Raises:
        StageError: if the mesh cannot be read or the solve fails.
    """
    from eigenfrequencies.bc.builders import from_template

    modal_opts = _section(options, "modal")
    runtime = runtime or Runtime.resolve(
        modal_opts,
        probe_module="dolfinx",
        image=FENICSX_IMAGE,
        container=FENICSX_CONTAINER,
        setup=FENICSX_SETUP,
        timeout=1800.0,
        python="python3",  # the dolfinx image is not on the dtOO interpreter
    )

    # Extra host directories to mount, and Python packages to reach from them.
    # This is what lets the *stock* dolfinx image serve the modal stage: it has
    # no gmsh, but a 17 MB `pip install --target` directory mounted from the
    # shared filesystem supplies it, and then no custom image has to be built,
    # pushed or copied to the cluster at all.
    extra_mounts = [str(m) for m in (modal_opts.get("mounts") or [])]
    pythonpath = modal_opts.get("pythonpath") or []
    if isinstance(pythonpath, str):
        pythonpath = [pythonpath]
    pythonpath = [_expand(p) for p in pythonpath]
    if pythonpath:
        extra_mounts += pythonpath
        # Appended, never assigned: the dolfinx image keeps its own dolfinx on
        # PYTHONPATH, and overwriting it makes `import dolfinx` fail inside an
        # image that plainly has it.
        runtime = dataclasses.replace(
            runtime,
            setup=tuple(runtime.setup)
            + (f"export PYTHONPATH={':'.join(pythonpath)}:$PYTHONPATH",),
        )

    template = machine_cfg.bc_template
    bc_cfg = from_template(template.type, template.params)
    _apply_overrides(bc_cfg, _section(modal_opts, "bc"), label="modal.bc")

    from eigenfrequencies.config import MaterialConfig, SolverConfig

    material = _apply_overrides(
        MaterialConfig(), _section(modal_opts, "material"), label="modal.material"
    )
    solver_cfg = _apply_overrides(
        SolverConfig(), _section(modal_opts, "solver"), label="modal.solver"
    )

    spec = {
        "msh_path": str(msh_path),
        "bc": vars(bc_cfg),
        "material": vars(material),
        "mesh": _section(modal_opts, "mesh"),
        "solver": vars(solver_cfg),
    }

    if runtime.kind == "inprocess":
        try:
            result = _modal_solve(spec)
        except Exception as exc:  # noqa: BLE001 — a bad geometry is a failed candidate
            raise StageError(f"modal solve: {type(exc).__name__}: {exc}") from exc
    else:
        spec_path = directory / "mesh" / "modal_spec.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        argv = [runtime.python, str(Path(__file__).resolve()), "modal", str(spec_path)]
        output = _run(
            runtime.command(
                argv,
                workdir=directory,
                mounts=[_repo_root(), directory, Path(msh_path).parent, *extra_mounts],
            ),
            stage="modal solve",
            timeout=runtime.timeout,
            log_path=directory / "logs" / "modal.log",
        )
        result = _parse_result_line(output, stage="modal solve")

    if not result.get("ok"):
        raise StageError(f"modal solve: {result.get('error', 'unknown failure')}")
    frequencies = [float(f) for f in result.get("frequencies_hz", [])]
    if not frequencies:
        raise StageError("modal solve: no eigenfrequencies returned")

    meta = {
        "modal_runtime": runtime.kind,
        "bc_mode": bc_cfg.mode,
        "element_degree": solver_cfg.element_degree,
        "solver_backend": solver_cfg.solver_backend,
        "num_eigenvalues": solver_cfg.num_eigenvalues,
    }
    if "n_nodes" in result:
        meta["mesh_nodes"] = result["n_nodes"]
    return frequencies, meta


def run_modal_stage(
    machine_cfg,
    parameters: dict[str, float],
    options: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> tuple[list[float], dict[str, Any]]:
    """dtOO geometry + FEniCSx modal solve for one candidate.

    Args:
        machine_cfg: parsed machine YAML.
        parameters: candidate design vector, ``{label: value}``.
        options: the ``[case.options]`` table.
        context: the request's ``context`` block (``scratch_dir``, resources).

    Returns:
        ``(frequencies_hz, meta)``. ``meta`` carries ``mesh_seconds`` and
        ``modal_seconds`` — each stage times itself, so the worker never has to
        derive one duration by subtracting the other.

    Raises:
        StageError: on any failure — the worker turns it into ``status: failed``.
    """
    directory = work_dir(options, context)
    started = time.perf_counter()
    msh_path, meta = export_mesh(machine_cfg, parameters, options, directory)
    meta["mesh_seconds"] = time.perf_counter() - started

    started = time.perf_counter()
    frequencies, modal_meta = solve_modal(msh_path, machine_cfg, options, directory)
    meta.update(modal_meta)
    meta["modal_seconds"] = time.perf_counter() - started
    meta["work_dir"] = str(directory)
    return frequencies, meta


# ── Stage 3: CFD ──────────────────────────────────────────────────────────

#: Case inputs staged next to the OpenFOAM case. ``boundaryData_RU_INLET`` is a
#: MappedFieldFixedValue source and must be a *sibling* of the case directory.
CFD_STAGE_SUBDIRS = ("tistos_files", "xml", "boundaryData_RU_INLET")

#: de_framework's two-step solve: laminar to 100, turbulent restart to 500.
CFD_SOLVE_SCRIPT = os.path.join("tistos_files", "sbatch.tistos_ru_of.sh")
CFD_BUILD_SCRIPT = os.path.join("turbine_runner", "dtoo_cfd_build.py")
CFD_CASE_MARKER = "CFD_CASE_DIR "


def _stage_dir(options_cfd: dict[str, Any]) -> Path:
    """Directory holding ``tistos_files/``, ``xml/`` and the inlet boundary data."""
    explicit = options_cfd.get("stage_dir")
    path = Path(_expand(explicit)) if explicit else _repo_root() / "turbine_runner" / "cfd"
    if not path.is_dir():
        raise StageError(f"cfd stage directory not found: {path}")
    return path


def _stage_case_inputs(stage: Path, directory: Path) -> None:
    """Copy the case inputs into the candidate's working directory.

    dtOO reads ``tistos_files/machine.xml``, which includes ``./xml/…`` relative
    to the working directory, so the inputs have to sit next to the case.
    """
    for sub in CFD_STAGE_SUBDIRS:
        source = stage / sub
        target = directory / sub
        if not source.is_dir():
            raise StageError(f"cfd stage directory is missing {sub}/: {source}")
        if not target.exists():
            shutil.copytree(source, target)


def _clear_stale_results(case_dir: Path) -> list[str]:
    """Remove every written time step, ``postProcessing/`` and decomposition.

    This is the fix for the frozen CFD objective: simpleFoam resumes from the
    latest time, so with ``500/`` already present it reports "completed" without
    solving, and ``evaluate_cfd`` then reads the *previous* design's
    ``postProcessing/``. Time ``0/`` holds the initial conditions and stays.

    ``processor*`` goes too. The de_framework script deletes the decomposition
    on its way out, so it only survives a run that did *not* finish — a
    timeout, an OOM kill, a crash. decomposePar then refuses outright ("Case is
    already decomposed with N domains"), and on a rerun with the same rank
    count it would instead silently reuse a decomposition of the *previous*
    candidate's mesh. Same failure as the frozen results, one directory over.
    """
    removed = []
    for entry in sorted(case_dir.iterdir()) if case_dir.is_dir() else []:
        if not entry.is_dir():
            continue
        stale = (
            entry.name == "postProcessing"
            or entry.name.startswith("processor")
            or (_is_time_dir(entry.name) and float(entry.name) != 0.0)
        )
        if stale:
            shutil.rmtree(entry)
            removed.append(entry.name)
    return removed


def _is_time_dir(name: str) -> bool:
    """True for an OpenFOAM time directory name (``100``, ``0.5``)."""
    try:
        float(name)
    except ValueError:
        return False
    return True


def _cfd_procs(options_cfd: dict[str, Any], context: dict[str, Any] | None) -> int:
    """MPI ranks for the solve.

    The contract lets the worker use ``context.resources.mpi_ranks`` but never
    choose global parallelism itself, so the orchestrator's number wins over any
    ambient SLURM variable.
    """
    if options_cfd.get("procs"):
        return max(1, int(options_cfd["procs"]))
    resources = (context or {}).get("resources") or {}
    if resources.get("mpi_ranks"):
        return max(1, int(resources["mpi_ranks"]))
    return max(1, int(os.environ.get("SLURM_CPUS_PER_TASK", "1")))


def build_cfd_case(
    machine_cfg,
    parameters: dict[str, float],
    options: dict[str, Any],
    directory: Path,
    runtime: Runtime | None = None,
) -> Path:
    """Build the OpenFOAM case for one design with dtOO.

    Mirrors de_framework's ``tistos.pre() + mesh()``: ``dtoo_cfd_build.py``
    writes ``<state>.xml`` from the template, then runs ``CreateStates`` and
    ``CreateMeshes`` in two separate interpreters (dtOO SWIG/Gmsh state does not
    survive both in one process).

    Returns:
        The OpenFOAM case directory.

    Raises:
        StageError: if the build fails or leaves an incomplete case.
    """
    cfd_opts = _section(options, "cfd")
    dtoo_opts = _section(options, "dtoo")
    runtime = runtime or Runtime.resolve(
        dtoo_opts,
        probe_module="dtOOPythonSWIG",
        image=DTOO_IMAGE,
        container=DTOO_CONTAINER,
        setup=DTOO_SETUP,
        timeout=900.0,
    )
    if runtime.kind == "inprocess":
        # dtoo_cfd_build.py spawns its own interpreters; a bare shell is the
        # in-process equivalent and keeps one code path for the subprocess call.
        runtime = Runtime(kind="native", python=sys.executable, timeout=runtime.timeout)

    _stage_case_inputs(_stage_dir(cfd_opts), directory)

    design_json = directory / "design.json"
    design_json.write_text(
        json.dumps({str(k): float(v) for k, v in parameters.items()}, indent=2),
        encoding="utf-8",
    )

    state = str(cfd_opts.get("state", "hydroflow"))
    case_name = str(cfd_opts.get("case_name", "tistos_ru_of"))
    case_dir = directory / f"{case_name}_n_{state}"
    # Rebuild from scratch: a case left over from an earlier candidate in the
    # same scratch directory would keep its mesh and its results.
    if case_dir.exists():
        shutil.rmtree(case_dir)

    build_script = _repo_root() / CFD_BUILD_SCRIPT
    argv = [
        runtime.python if runtime.containerized else sys.executable,
        str(build_script),
        str(design_json),
        state,
        case_name,
    ]
    output = _run(
        runtime.command(
            argv,
            workdir=directory,
            mounts=[_repo_root(), directory, _case_dir(machine_cfg, dtoo_opts, runtime)],
        ),
        stage="cfd build",
        timeout=runtime.timeout,
        log_path=directory / "logs" / "cfd_build.log",
    )

    reported = None
    for line in output.splitlines():
        if line.startswith(CFD_CASE_MARKER):
            reported = line[len(CFD_CASE_MARKER):].strip()
    if reported:
        case_dir = Path(reported)
    if not (case_dir / "system").is_dir() or not (case_dir / "constant").is_dir():
        raise StageError(f"cfd build: incomplete OpenFOAM case at {case_dir}")
    return case_dir


def solve_cfd(
    case_dir: Path,
    options: dict[str, Any],
    directory: Path,
    context: dict[str, Any] | None = None,
    runtime: Runtime | None = None,
) -> dict[str, Any]:
    """Run checkMesh + decomposePar + simpleFoam + reconstructPar on *case_dir*.

    Every stale time step is removed first; see :func:`_clear_stale_results`.

    Returns:
        Metadata about the solve (ranks, removed artifacts, log path).

    Raises:
        StageError: on a non-zero exit or a timeout.
    """
    cfd_opts = _section(options, "cfd")
    dtoo_opts = _section(options, "dtoo")
    runtime = runtime or Runtime.resolve(
        dtoo_opts,
        probe_module="dtOOPythonSWIG",
        image=DTOO_IMAGE,
        container=DTOO_CONTAINER,
        setup=DTOO_SETUP,
        timeout=float(cfd_opts.get("timeout", os.environ.get("CFD_TIMEOUT", 1800))),
    )
    if runtime.kind == "inprocess":
        # simpleFoam is a binary, never an import: "in-process" means the
        # ambient shell, whose OpenFOAM environment this process inherited.
        runtime = Runtime(kind="native", timeout=runtime.timeout)

    removed = _clear_stale_results(case_dir)
    procs = _cfd_procs(cfd_opts, context)
    script = directory / str(cfd_opts.get("solve_script", CFD_SOLVE_SCRIPT))
    if not script.is_file():
        raise StageError(f"cfd solve script not found: {script}")

    # bwUniCluster provides mpiexec, the dtOO container only mpirun (openmpi4);
    # the solve script honours MPI_LAUNCHER and defaults to mpiexec, so the
    # cluster path stays the de_framework original.
    env = {}
    if cfd_opts.get("mpi_launcher"):
        env["MPI_LAUNCHER"] = str(cfd_opts["mpi_launcher"])
    # Free-form passthrough for whatever the local MPI insists on — OpenMPI
    # wants OMPI_ALLOW_RUN_AS_ROOT inside a root container, a cluster build may
    # want its own pinning or fabric variables.
    for key, value in (cfd_opts.get("env") or {}).items():
        env[str(key)] = str(value)

    _run(
        runtime.command(
            ["sh", "-e", str(script), str(case_dir), str(procs)],
            workdir=directory,
            mounts=[_repo_root(), directory],
            env=env,
        ),
        stage="cfd solve",
        timeout=runtime.timeout,
        log_path=directory / "logs" / "cfd_solve.log",
    )
    return {
        "cfd_runtime": runtime.kind,
        "mpi_launcher": env.get("MPI_LAUNCHER", "mpiexec"),
        "mpi_ranks": procs,
        "cleared_artifacts": removed,
        "case_dir": str(case_dir),
    }


def run_cfd_stage(
    machine_cfg,
    parameters: dict[str, float],
    options: dict[str, Any],
    cfd_cfg,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """dtOO case build + simpleFoam + result extraction for one candidate.

    Args:
        machine_cfg: parsed machine YAML.
        parameters: candidate design vector.
        options: the ``[case.options]`` table.
        cfd_cfg: :class:`eigenfrequencies.config.CFDConfig` — omega, rho, g,
            design head, ``end_time`` and ``post_folder`` for the reader.
        context: the request's ``context`` block.

    Returns:
        The dict from :func:`~eigenfrequencies.io.cfd_eval.evaluate_cfd`
        (``ok``, ``eta``, ``vcav``, ``dH``, ``P``, ``Q``, plus ``error`` when it
        failed), enriched with solve metadata. A failed build or solve is
        reported the same way rather than raised, so the worker records one
        failure shape whatever went wrong.
    """
    from eigenfrequencies.io.cfd_eval import evaluate_cfd

    directory = work_dir(options, context)
    try:
        case_dir = build_cfd_case(machine_cfg, parameters, options, directory)
        meta = solve_cfd(case_dir, options, directory, context)
    except StageError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "eta": 0.0,
            "vcav": 0.0,
            "dH": 0.0,
            "P": 0.0,
            "Q": 0.0,
            "work_dir": str(directory),
        }

    result = evaluate_cfd(str(case_dir), cfd_cfg)
    result.update(meta)
    result["work_dir"] = str(directory)
    return result


# ── In-container entry points ─────────────────────────────────────────────


def _bootstrap_package_path() -> None:
    """Make ``eigenfrequencies`` importable when this file is run by path.

    Inside the dtOO and FEniCSx containers the package is not installed; the
    repository is mounted and this file is invoked as
    ``python3 <repo>/src/eigenfrequencies/hydroflow/physics.py``.
    """
    src = str(Path(__file__).resolve().parents[2])
    if src not in sys.path:
        sys.path.insert(0, src)


def main(argv: list[str] | None = None) -> int:
    """``physics.py {dtoo-export,modal} SPEC`` — the in-container entry point.

    Prints one ``RESULT_JSON`` line, which the host parses. Failures are
    reported on that same line so the message survives into ``result.json``.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in ("dtoo-export", "modal"):
        print("usage: physics.py {dtoo-export,modal} SPEC_JSON", file=sys.stderr)
        return 2

    _bootstrap_package_path()
    stage, spec_path = args
    try:
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        if stage == "dtoo-export":
            result = {"ok": True, "msh_path": _dtoo_export(spec)}
        else:
            result = _modal_solve(spec)
    except Exception as exc:  # noqa: BLE001 — the host needs the message, not a traceback
        import traceback

        traceback.print_exc()
        print(RESULT_MARKER + json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1

    print(RESULT_MARKER + json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
