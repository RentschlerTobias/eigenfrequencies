#!/usr/bin/env python3
"""STAGE 1: generate the tistos runner geometry with dtOO and export a .msh.

This script runs INSIDE the dtOO container (atismer/dtoo-opensuse:stable) where
dtOO is installed at /dtOO-install. It is intentionally self-contained: it does
NOT import turbine_runner.config or any FEniCSx/dolfinx module, because those
dependencies do not exist in the dtOO container.

It reproduces the driver pattern of
``block_structured_meshing/export_t2_7461.py`` and writes the structural
mechanical mesh ``ruWithRounding_mechMesh`` to the shared work directory.

NOTE: The existing ``block_structured_meshing/T1_9/T1_9_ru_gridGmsh.msh`` is the
CFD *fluid* mesh (flow channel, surface-tagged Hub/Shroud), NOT a structural
solid. Only ``ruWithRounding_mechMesh`` is a valid structural input. The fluid
mesh may be used as a read->assemble smoke-test, never for valid frequencies.

Usage (from the repo root, mounting data/ as the shared /work volume):

    docker run --rm \
        -v <repo>/turbine_runner/data:/work \
        -v <repo>:/src \
        atismer/dtoo-opensuse:stable \
        python3 /src/turbine_runner/dtoo_export.py
"""

import os
import sys

# --- configuration (plain constants; the dtOO container has no argparse needs) ---
DTOO_TOOLS = os.environ.get("DTOO_TOOLS", "/dtOO-install/tools")
DTOO_LIB = os.environ.get("DTOO_LIB", "/dtOO-install/lib")
OPENFOAM_LIBS = (
    "/usr/lib/openfoam/openfoam2406/platforms/linux64GccDPInt32Opt/lib/sys-openmpi:"
    "/usr/lib64/mpi/gcc/openmpi4/lib64:"
    "/usr/lib/hpc/gnu7/mpi/openmpi/4.1.6/lib64"
)

MACHINE_XML = os.environ.get("DTOO_MACHINE_XML", "machine.xml")
CASE_XML = os.environ.get("DTOO_CASE_XML", "tistos_ru_of.xml")
STATE = os.environ.get("DTOO_STATE", "tistos")
CASE = os.environ.get("DTOO_CASE", "tistos_ru_of_n")
MECH_VOLUME = os.environ.get("DTOO_MECH_VOLUME", "ruWithRounding_mechMesh")

OUTPUT_MSH = os.environ.get("DTOO_OUTPUT_MSH", "/work/runner.msh")
OUTPUT_STEP = os.environ.get("DTOO_OUTPUT_STEP", "/work/runner.step")


def main() -> None:
    sys.path.insert(0, DTOO_TOOLS)
    os.environ["LD_LIBRARY_PATH"] = f"{DTOO_LIB}:{OPENFOAM_LIBS}"

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

    logMe.initLog("build.log")
    dtXmlParser.init(MACHINE_XML, CASE_XML)
    parser = dtXmlParser.reference()
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
    parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)

    dC.get(CASE).runCurrentState()

    bV.get(MECH_VOLUME).makeGrid()
    model = bV.get(MECH_VOLUME).getModel()

    os.makedirs(os.path.dirname(OUTPUT_MSH), exist_ok=True)
    print(f"Exporting mechanical mesh to {OUTPUT_MSH} ...")
    model.writeMSH(OUTPUT_MSH)
    print(f"Mesh exported: {OUTPUT_MSH}")

    # Best-effort CAD export for the mesh_prep volume-meshing fallback. The
    # dtOO/gmsh model may not support BREP/STEP writing; never fail STAGE 1 on it.
    try:
        model.writeBREP(OUTPUT_STEP)
        print(f"CAD exported: {OUTPUT_STEP}")
    except Exception as exc:  # noqa: BLE001 - export is optional
        print(f"CAD export skipped ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
