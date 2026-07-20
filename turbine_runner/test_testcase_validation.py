"""Full experimental-validation test for the test-case disc (heavyweight, opt-in).

Runs the complete free-free pipeline (tet10 mesh, SLEPc backend, ~1.96M DOFs;
~3 min wall, ~29 GB peak RAM) and asserts that every experimentally measured
mode (1ND/2ND/3ND/4ND) lands within 5% of the measured frequency.

Skipped unless RUN_TESTCASE_VALIDATION=1 (resource-heavy). Runs only inside the
fenicsx container:

    docker run --rm -i -e PYTHONUNBUFFERED=1 -e RUN_TESTCASE_VALIDATION=1 \
      -v "$PWD:/workspace" -w /workspace/turbine_runner \
      eigenfrequencies-fenicsx:latest \
      python3 -m pytest test_testcase_validation.py -v
"""

import json
import os

import pytest

pytest.importorskip("dolfinx", reason="fenicsx container only")

from stl_to_msh import DEFAULT_MSH, DEFAULT_STL  # noqa: E402
from validate_testcase import EXPERIMENT_HZ, run_validation  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_TESTCASE_VALIDATION") != "1",
    reason="heavyweight (~3 min, ~29 GB RAM); set RUN_TESTCASE_VALIDATION=1",
)

TOLERANCE_PCT = 5.0


def test_testcase_matches_experiment():
    msh_path = os.environ.get("TESTCASE_MSH", DEFAULT_MSH)
    stl_path = os.environ.get("TESTCASE_STL", DEFAULT_STL)
    if not (os.path.isfile(msh_path) or os.path.isfile(stl_path)):
        pytest.skip("test-case geometry (prebuilt .msh or STL) not present")

    result = run_validation()

    assert result["rigid_modes_removed"] == 6, (
        "one connected free body must yield exactly 6 rigid-body modes"
    )
    elastic = result["elastic_frequencies_hz"]
    assert len(elastic) >= 9, f"expected >=9 elastic modes, got {len(elastic)}"

    comparison = result["comparison"]
    for label, exp_hz in EXPERIMENT_HZ.items():
        if exp_hz is None:  # torsion was not measured experimentally
            continue
        entry = comparison[label]
        assert abs(entry["error_pct"]) <= TOLERANCE_PCT, (
            f"{label}: computed {entry['computed_mean_hz']:.2f} Hz vs experiment "
            f"{exp_hz} Hz -> {entry['error_pct']:+.2f}% (limit {TOLERANCE_PCT}%)"
        )

    with open(result["json_path"]) as fh:
        stored = json.load(fh)
    assert stored["rigid_modes_removed"] == 6
    assert "comparison" in stored
