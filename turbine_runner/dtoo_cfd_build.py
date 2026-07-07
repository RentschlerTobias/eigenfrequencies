#!/usr/bin/env python3
"""STAGE CFD-1: build the OpenFOAM case for a design via dtOO (tistos_ru_of).

Runs INSIDE the dtOO container / ~/pe env, next to createStatesAndMeshes.py.
Self-contained: no FEniCSx/turbine_runner.config imports.

Mirrors de_framework's tistos.pre() + createStatesAndMeshes:
  1. write <state>.xml from templateState.xml with the design const-values,
  2. CreateStates(state)   -> apply ru_adjustDomain, extract state,
  3. CreateMeshes(state, "tistos_ru_of") -> dC.get("tistos_ru_of_n").runCurrentState()
     builds the OpenFOAM case dir  tistos_ru_of_n_<state>/  (system/constant/0).

The actual simpleFoam solve is a SEPARATE step (tistos_files/sbatch.tistos_ru_of.sh),
run by turbine_runner/optimize.py::_run_cfd after this script produces the case.

CWD must contain the staged tistos_files/ and xml/ (siblings), because
createStatesAndMeshes.py loads "tistos_files/machine.xml" and machine.xml
includes "./xml/...". turbine_runner/optimize.py stages these per worker.

Usage:  python3 dtoo_cfd_build.py <design.json> <state> [caseName]
Prints: the OpenFOAM case directory (absolute) on the last stdout line as
        "CFD_CASE_DIR <path>" so the caller can parse it.
"""

import sys
import os
import json
import xml.etree.ElementTree as ET

CASE_NAME = "tistos_ru_of"
TEMPLATE = os.path.join("tistos_files", "templateState.xml")


def _write_state_xml(state: str, design: dict) -> str:
    """Write <state>.xml from templateState.xml with the design const-values."""
    tree = ET.parse(TEMPLATE)
    st = tree.find("state")
    st.set("label", state)
    for label, value in design.items():
        el = st.find(f"constValue[@label='{label}']")
        if el is None:
            print(f"[cfd] WARN: design label {label!r} not in templateState.xml")
            continue
        el.set("value", str(float(value)))
    out = state + ".xml"
    if os.path.exists(out):
        os.remove(out)
    tree.write(out)
    print(f"[cfd] wrote {out} with {len(design)} design parameters")
    return out


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: dtoo_cfd_build.py <design.json> <state> [caseName]",
              file=sys.stderr)
        sys.exit(2)
    design_json = sys.argv[1]
    state = sys.argv[2]
    case_name = sys.argv[3] if len(sys.argv) > 3 else CASE_NAME

    design = {}
    if design_json and os.path.isfile(design_json):
        with open(design_json) as fh:
            design = json.load(fh)

    # tistos_files/ must be importable as a package from CWD.
    sys.path.insert(0, os.getcwd())

    _write_state_xml(state, design)

    from tistos_files.createStatesAndMeshes import createStatesAndMeshes
    csm = createStatesAndMeshes()
    csm.CreateStates(state)
    print(f"[cfd] CreateStates done for {state}")
    csm.CreateMeshes(state, case_name)   # runCurrentState() on <case>_n
    print(f"[cfd] CreateMeshes done ({case_name}_n)")

    case_dir = os.path.abspath(f"{case_name}_n_{state}")
    if not (os.path.isdir(os.path.join(case_dir, "system"))
            and os.path.isdir(os.path.join(case_dir, "constant"))
            and os.path.isdir(os.path.join(case_dir, "0"))):
        print(f"[cfd] ERROR: OpenFOAM case not complete at {case_dir}",
              file=sys.stderr)
        sys.exit(1)
    # Machine-parseable last line for the caller.
    print(f"CFD_CASE_DIR {case_dir}")


if __name__ == "__main__":
    main()
