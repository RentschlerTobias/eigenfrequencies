#!/usr/bin/env python3
"""STAGE CFD-1: build the OpenFOAM case for a design via dtOO (tistos_ru_of).

Mirrors de_framework's sim_tistos.py:mesh() — CreateStates and CreateMeshes
run in TWO SEPARATE python3 subprocesses so dtOO SWIG/Gmsh state does not
accumulate within one process (segfault / labeledVectorHandling dt__mustCast).

CWD must contain the staged tistos_files/ and xml/ (siblings), because
createStatesAndMeshes loads "tistos_files/machine.xml" and machine.xml
includes "./xml/...". turbine_runner/optimize.py stages these per worker.

Usage:  python3 dtoo_cfd_build.py <design.json> <state> [caseName]
Prints: the OpenFOAM case directory (absolute) on the last stdout line as
        "CFD_CASE_DIR <path>" so the caller can parse it.
"""

import sys
import os
import json
import subprocess
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

    _write_state_xml(state, design)

    cmd_states = [
        "python3", "-c",
        f"from tistos_files.createStatesAndMeshes import *; "
        f"createStatesAndMeshes().CreateStates({state!r})",
    ]
    r1 = subprocess.run(cmd_states, capture_output=True, text=True, timeout=300)
    sys.stdout.write(r1.stdout)
    sys.stderr.write(r1.stderr)
    if r1.returncode != 0:
        print(f"[cfd] CreateStates FAILED (exit {r1.returncode})", file=sys.stderr)
        sys.exit(1)
    print(f"[cfd] CreateStates done for {state}")

    cmd_meshes = [
        "python3", "-c",
        f"from tistos_files.createStatesAndMeshes import *; "
        f"createStatesAndMeshes().CreateMeshes({state!r}, {case_name!r})",
    ]
    r2 = subprocess.run(cmd_meshes, capture_output=True, text=True, timeout=300)
    sys.stdout.write(r2.stdout)
    sys.stderr.write(r2.stderr)
    if r2.returncode != 0:
        print(f"[cfd] CreateMeshes FAILED (exit {r2.returncode})", file=sys.stderr)
        sys.exit(1)
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
