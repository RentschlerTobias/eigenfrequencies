#!/usr/bin/env python3
"""STAGE 1: build the tistos runner mech mesh with dtOO and export a .msh.

Runs INSIDE the dtOO container (atismer/dtoo-opensuse:stable). Self-contained:
no FEniCSx/turbine_runner.config imports (those do not exist in this container).

Geometry-only: it does NOT run the CFD case (dC.runCurrentState()). Only the
parametric geometry + the structural mechanical mesh ruWithRounding_mechMesh are
built, which is all the eigenfrequency analysis needs and keeps each evaluation
cheap (seconds-minutes, not a CFD run).

Parametric: design parameters are read from a JSON file ({label: value}) and
applied with cV.get(label).setValue(value) before the geometry is created. The
labels are dtOO const-value names, e.g. cV_ru_bladeLength_0.5, cV_ru_alpha_1_ex_0.5
(see tistos/build.py in the block_structured_meshing reference). An empty/missing
JSON just builds the template (baseline) geometry.

Environment notes (discovered for atismer/dtoo-opensuse:stable):
  * interpreter MUST be python3.12 (has numpy 2.x that OCC needs; python3.6 fails)
  * LD_LIBRARY_PATH must include /dtOO-install/lib (OpenCASCADE) and
    /dtOO-install/lib64 (gmsh); run under a login shell so OpenFOAM env is sourced
  * the working dir must be a dtOO case dir holding machine.xml + machineSave.xml
    + xml/ (default /dtOO/test/tistos)

Usage (from the repo root; data/ is the shared volume):

    docker run --rm \
        -v "$PWD/turbine_runner/data:/work" \
        -v "$PWD/turbine_runner:/src" \
        -w /dtOO/test/tistos \
        atismer/dtoo-opensuse:stable \
        bash -lc 'export LD_LIBRARY_PATH=/dtOO-install/lib:/dtOO-install/lib64:$LD_LIBRARY_PATH \
                  && python3.12 /src/dtoo_export.py'

Override via env vars: DTOO_CASE_DIR, DTOO_MACHINE_XML, DTOO_STATE_XML,
DTOO_STATE, DTOO_MECH_VOLUME, DTOO_ADJUST_PLUGIN, DTOO_DESIGN_JSON, DTOO_OUTPUT_MSH.
"""

import json
import os


CASE_DIR = os.environ.get("DTOO_CASE_DIR", "/dtOO/test/tistos")
MACHINE_XML = os.environ.get("DTOO_MACHINE_XML", "machine.xml")
STATE_XML = os.environ.get("DTOO_STATE_XML", "machineSave.xml")
STATE = os.environ.get("DTOO_STATE", "templateState")
MECH_VOLUME = os.environ.get("DTOO_MECH_VOLUME", "ruWithRounding_mechMesh")
ADJUST_PLUGIN = os.environ.get("DTOO_ADJUST_PLUGIN", "ru_adjustDomain")

DESIGN_JSON = os.environ.get("DTOO_DESIGN_JSON", "/work/design.json")
OUTPUT_MSH = os.environ.get("DTOO_OUTPUT_MSH", "/work/runner.msh")


def _load_design() -> dict:
    """Read the {label: value} design dict, or {} for the baseline geometry."""
    if DESIGN_JSON and os.path.isfile(DESIGN_JSON):
        with open(DESIGN_JSON) as fh:
            design = json.load(fh)
        print(f"[dtoo] loaded {len(design)} design parameters from {DESIGN_JSON}")
        return design
    print("[dtoo] no design JSON -> building baseline (template) geometry")
    return {}


def main() -> None:
    os.chdir(CASE_DIR)
    design = _load_design()

    from dtOOPythonSWIG import (
        logMe,
        dtXmlParser,
        baseContainer,
        labeledVectorHandlingConstValue,
        labeledVectorHandlingAnalyticFunction,
        labeledVectorHandlingAnalyticGeometry,
        labeledVectorHandlingBoundedVolume,
        labeledVectorHandlingDtCase,
        labeledVectorHandlingDtPlugin,
    )

    logMe.initLog("/work/dtoo_build.log")
    parser = dtXmlParser.init(MACHINE_XML, STATE_XML).reference()
    parser.parse()

    bC = baseContainer()
    cV = labeledVectorHandlingConstValue()
    aF = labeledVectorHandlingAnalyticFunction()
    aG = labeledVectorHandlingAnalyticGeometry()
    bV = labeledVectorHandlingBoundedVolume()
    dC = labeledVectorHandlingDtCase()
    dP = labeledVectorHandlingDtPlugin()

    parser.createConstValue(cV)
    parser.loadStateToConst(STATE, cV)

    # Apply the design vector onto the const values before geometry creation.
    for label, value in design.items():
        cV.get(label).setValue(float(value))
    if design:
        print(f"[dtoo] applied {len(design)} parameter overrides")

    parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)

    # The domain-adjust plugin finalizes the runner geometry (matches build.py).
    try:
        dP.get(ADJUST_PLUGIN).apply()
        parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
        print(f"[dtoo] plugin {ADJUST_PLUGIN} applied")
    except Exception as exc:  # noqa: BLE001 - plugin is optional
        print(f"[dtoo] plugin {ADJUST_PLUGIN} skipped ({type(exc).__name__}: {exc})")

    print(f"[dtoo] makeGrid on {MECH_VOLUME} ...")
    bV.get(MECH_VOLUME).makeGrid()
    model = bV.get(MECH_VOLUME).getModel()

    os.makedirs(os.path.dirname(OUTPUT_MSH), exist_ok=True)
    model.writeMSH(OUTPUT_MSH)
    print(f"[dtoo] mesh written: {OUTPUT_MSH}")


if __name__ == "__main__":
    main()
