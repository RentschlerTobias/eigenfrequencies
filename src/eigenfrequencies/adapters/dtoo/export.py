"""Generalised dtOO export pipeline.

Ported from ``turbine_runner/dtoo_export.py`` with two changes:

1. Configuration comes from a ``MachineAdapterConfig`` dataclass instead of
   module-level env-var reads.
2. ``mesh_scale_factor`` is applied to the exported mesh coordinates **after**
   dtOO writes the file but **before** the path is returned — the explicit fix
   for the non-physical-units caveat.

dtOO is imported **lazily** inside ``run_dtoo_export`` so that the module is
importable even when ``dtOOPythonSWIG`` is not installed.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from eigenfrequencies.adapters.dtoo.machine_yaml import MachineAdapterConfig

# Env vars that the original driver honoured; we preserve the same override
# matrix so existing shell scripts and Docker invocations keep working.
_ENV_OVERRIDES = {
    "case_dir": "DTOO_CASE_DIR",
    "state": "DTOO_STATE",
    "mech_volume": "DTOO_MECH_VOLUME",
    "adjust_plugin": "DTOO_ADJUST_PLUGIN",
}


def _resolve_with_env(machine_value: str, env_name: str) -> str:
    """Return the env value if set, otherwise fall back to the machine config."""
    return os.environ.get(env_name, machine_value)


def _apply_mesh_scale_factor(msh_path: str, scale: float) -> str:
    """Scale all node coordinates in a gmsh ``.msh`` by *scale* in-place.

    Uses the ``gmsh`` Python API (already a project dependency via
    ``eigenfrequencies.io.load``).  Returns the path to the scaled mesh
    (same file when ``scale == 1.0``, otherwise a sibling ``*_scaled.msh``).
    """
    if scale == 1.0:
        return msh_path

    import gmsh

    out_path = msh_path.replace(".msh", "_scaled.msh")
    gmsh.initialize()
    try:
        gmsh.open(msh_path)
        # Scale all node coordinates
        node_tags, coords, _ = gmsh.model.mesh.getNodes()
        if len(node_tags):
            scaled = [c * scale for c in coords]
            gmsh.model.mesh.setNodes(node_tags, scaled, [])
        gmsh.write(out_path)
    finally:
        gmsh.finalize()

    return out_path


def run_dtoo_export(
    machine_config: MachineAdapterConfig,
    design_values: Optional[Dict[str, float]] = None,
    output_msh: Optional[str] = None,
) -> str:
    """Run dtOO with *machine_config*, export a volume mesh, apply scaling.

    Parameters
    ----------
    machine_config:
        Parsed machine YAML (case_dir, state, mech_volume, etc.).
    design_values:
        Optional ``{label: value}`` overrides applied to dtOO const-values
        before geometry creation.  If ``None`` or empty, the baseline geometry
        is built.
    output_msh:
        Destination path for the exported ``.msh``.  If ``None``, a temporary
        file is created.

    Returns
    -------
    Path to the (possibly scaled) mesh file.

    Raises
    ------
    FileNotFoundError
        If the resolved ``case_dir`` does not exist.
    ImportError
        If ``dtOOPythonSWIG`` is not available (dtOO container only).
    """
    design_values = design_values or {}

    # Resolve configuration: machine YAML is the default, env vars override.
    case_dir = _resolve_with_env(machine_config.case_dir, "DTOO_CASE_DIR")
    state = _resolve_with_env(machine_config.state, "DTOO_STATE")
    mech_volume = _resolve_with_env(machine_config.mech_volume, "DTOO_MECH_VOLUME")
    adjust_plugin = _resolve_with_env(
        machine_config.adjust_plugin, "DTOO_ADJUST_PLUGIN"
    )

    # Legacy env vars not present in MachineAdapterConfig but still honoured.
    machine_xml = os.environ.get("DTOO_MACHINE_XML", "machine.xml")
    state_xml = os.environ.get("DTOO_STATE_XML", "machineSave.xml")

    if output_msh is None:
        output_msh = os.environ.get("DTOO_OUTPUT_MSH")
        if output_msh is None:
            output_msh = os.path.join(
                tempfile.gettempdir(), f"{machine_config.name}_export.msh"
            )

    log_file = os.environ.get(
        "DTOO_LOG_FILE",
        os.path.join(os.path.dirname(output_msh), "dtoo_build.log"),
    )

    # Write design values to a temporary JSON so the legacy dtOO path can read it.
    design_json: Optional[str] = None
    if design_values:
        design_json = os.environ.get("DTOO_DESIGN_JSON")
        if design_json is None:
            fd, design_json = tempfile.mkstemp(suffix=".json", prefix="design_")
            with os.fdopen(fd, "w") as fh:
                json.dump(design_values, fh)

    # ------------------------------------------------------------------
    # Lazy dtOO import — this module is importable without dtOO installed.
    # ------------------------------------------------------------------
    from dtOOPythonSWIG import (
        baseContainer,
        dtXmlParser,
        labeledVectorHandlingAnalyticFunction,
        labeledVectorHandlingAnalyticGeometry,
        labeledVectorHandlingBoundedVolume,
        labeledVectorHandlingConstValue,
        labeledVectorHandlingDtCase,
        labeledVectorHandlingDtPlugin,
        logMe,
    )

    original_cwd = os.getcwd()
    try:
        os.chdir(case_dir)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"DTOO case directory does not exist: {case_dir}"
        ) from exc

    try:
        logMe.initLog(log_file)
        parser = dtXmlParser.init(machine_xml, state_xml).reference()
        parser.parse()

        bC = baseContainer()
        cV = labeledVectorHandlingConstValue()
        aF = labeledVectorHandlingAnalyticFunction()
        aG = labeledVectorHandlingAnalyticGeometry()
        bV = labeledVectorHandlingBoundedVolume()
        dC = labeledVectorHandlingDtCase()
        dP = labeledVectorHandlingDtPlugin()

        parser.createConstValue(cV)
        parser.loadStateToConst(state, cV)

        # Apply design vector onto const values before geometry creation.
        for label, value in design_values.items():
            cV.get(label).setValue(float(value))
        if design_values:
            print(f"[dtoo] applied {len(design_values)} parameter overrides")

        parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)

        # Domain-adjust plugin finalises the runner geometry.
        try:
            dP.get(adjust_plugin).apply()
            parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
            print(f"[dtoo] plugin {adjust_plugin} applied")
        except Exception as exc:  # noqa: BLE001 — plugin is optional
            print(f"[dtoo] plugin {adjust_plugin} skipped ({type(exc).__name__}: {exc})")

        print(f"[dtoo] makeGrid on {mech_volume} ...")
        bV.get(mech_volume).makeGrid()
        model = bV.get(mech_volume).getModel()

        os.makedirs(os.path.dirname(output_msh) or ".", exist_ok=True)
        model.writeMSH(output_msh)
        print(f"[dtoo] mesh written: {output_msh}")
    finally:
        os.chdir(original_cwd)
        # Clean up temporary design JSON if we created it.
        if design_json and design_json != os.environ.get("DTOO_DESIGN_JSON"):
            try:
                os.unlink(design_json)
            except FileNotFoundError:
                pass

    # Apply mesh_scale_factor (explicit fix for non-physical-units caveat).
    scaled_path = _apply_mesh_scale_factor(output_msh, machine_config.mesh_scale_factor)
    if scaled_path != output_msh:
        print(f"[dtoo] mesh scaled by {machine_config.mesh_scale_factor}: {scaled_path}")

    return scaled_path
