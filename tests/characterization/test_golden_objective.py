"""Characterization test: freeze penalty/objective golden values from de_history.

Replays resonance_term, cfd_scalar, and combined_objective against frozen
outputs derived from de_history_resonance_only.jsonl (generation 0, rows 0-4)
and de_history_combined.jsonl (CFD scalars).  Any refactor that changes the
math (tanh mapping, penalty depth, band intervals) is caught immediately.

Imports ONLY from the eigenfrequencies package (no turbine_runner path hack).
"""

import json
import os

import pytest

from eigenfrequencies.config import CFDConfig, ObjectiveConfig, OptimizationConfig
from eigenfrequencies.penalty.objective import (
    cfd_scalar,
    combined_objective,
    resonance_term,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLDEN_PATH = os.path.join(_HERE, "golden", "objective_cases.json")


def _load_golden():
    with open(_GOLDEN_PATH) as fh:
        return json.load(fh)


def _rel_close(a, b, rtol=1e-9):
    """Relative tolerance check that handles zero."""
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale <= rtol


@pytest.fixture(scope="module")
def golden_cases():
    return _load_golden()


@pytest.fixture(scope="module")
def configs():
    """Fresh config instances (same defaults as when golden was generated)."""
    return {
        "opt_cfg": OptimizationConfig(n_rpm=72.0),
        "cfd_cfg": CFDConfig(n_rpm=72.0),
        "obj_cfg": ObjectiveConfig(),
    }


@pytest.mark.parametrize("case_index", list(range(5)))
def test_replay_matches_golden(case_index, golden_cases, configs):
    """Replay each case and assert all three outputs match frozen values."""
    case = golden_cases[case_index]
    inputs = case["inputs"]
    frozen = case["frozen"]

    frequencies = inputs["frequencies"]
    cfd_dict = inputs["cfd"]

    opt_cfg = configs["opt_cfg"]
    cfd_cfg = configs["cfd_cfg"]
    obj_cfg = configs["obj_cfg"]

    # 1. resonance_term
    f_res = resonance_term(frequencies, opt_cfg, obj_cfg)
    assert _rel_close(f_res, frozen["resonance_term"]), (
        f"case {case_index}: resonance_term mismatch: "
        f"replay={f_res} != frozen={frozen['resonance_term']}"
    )

    # 2. cfd_scalar
    f_cfd = cfd_scalar(cfd_dict, cfd_cfg, obj_cfg)
    assert _rel_close(f_cfd, frozen["cfd_scalar"]), (
        f"case {case_index}: cfd_scalar mismatch: "
        f"replay={f_cfd} != frozen={frozen['cfd_scalar']}"
    )

    # 3. combined_objective
    total, breakdown = combined_objective(cfd_dict, frequencies, cfd_cfg, opt_cfg, obj_cfg)
    assert _rel_close(total, frozen["combined_objective"]["total"]), (
        f"case {case_index}: combined_objective total mismatch: "
        f"replay={total} != frozen={frozen['combined_objective']['total']}"
    )
    assert _rel_close(breakdown["f_cfd"], frozen["combined_objective"]["breakdown"]["f_cfd"])
    assert _rel_close(breakdown["f_resonance"], frozen["combined_objective"]["breakdown"]["f_resonance"])
    assert breakdown["resonance"] == frozen["combined_objective"]["breakdown"]["resonance"]


def test_perturbed_band_bound_produces_different_value(golden_cases, configs):
    """Perturb margin_hz so the replay diverges from the golden value."""
    case = golden_cases[0]
    inputs = case["inputs"]
    frozen = case["frozen"]

    frequencies = inputs["frequencies"]
    cfd_dict = inputs["cfd"]

    opt_cfg = configs["opt_cfg"]
    cfd_cfg = configs["cfd_cfg"]
    obj_cfg = configs["obj_cfg"]

    # Perturb the forbidden-band margin so the penalty changes
    original_margin = opt_cfg.margin_hz
    opt_cfg.margin_hz = original_margin - 1.0  # narrower band -> different penalty

    f_res = resonance_term(frequencies, opt_cfg, obj_cfg)
    total, _ = combined_objective(cfd_dict, frequencies, cfd_cfg, opt_cfg, obj_cfg)

    # Must produce a different value than the frozen one
    assert not _rel_close(f_res, frozen["resonance_term"]), (
        f"Perturbed margin_hz should change resonance_term, but got same value {f_res}"
    )
    assert not _rel_close(total, frozen["combined_objective"]["total"]), (
        f"Perturbed margin_hz should change combined total, but got same value {total}"
    )
