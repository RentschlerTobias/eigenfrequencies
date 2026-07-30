"""Demonstrate failure when a penalty band bound is perturbed."""
import json
import os

from eigenfrequencies.config import CFDConfig, ObjectiveConfig, OptimizationConfig
from eigenfrequencies.penalty.objective import combined_objective, resonance_term

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLDEN_PATH = os.path.join(_HERE, "golden", "objective_cases.json")

with open(_GOLDEN_PATH) as fh:
    cases = json.load(fh)

case = cases[0]
inputs = case["inputs"]
frozen = case["frozen"]

frequencies = inputs["frequencies"]
cfd_dict = inputs["cfd"]

opt_cfg = OptimizationConfig(n_rpm=72.0)
cfd_cfg = CFDConfig(n_rpm=72.0)
obj_cfg = ObjectiveConfig()

# Perturb margin_hz by -1.0 Hz (narrower band)
opt_cfg.margin_hz = opt_cfg.margin_hz - 1.0

f_res = resonance_term(frequencies, opt_cfg, obj_cfg)
total, _ = combined_objective(cfd_dict, frequencies, cfd_cfg, opt_cfg, obj_cfg)

print(f"Frozen resonance_term: {frozen['resonance_term']}")
print(f"Replay  resonance_term: {f_res}")
print(f"Frozen combined total:   {frozen['combined_objective']['total']}")
print(f"Replay  combined total:  {total}")

# Assert they are different (this is the "failure" demonstration)
assert f_res != frozen["resonance_term"], (
    f"Expected perturbed margin_hz to change resonance_term, but got same value {f_res}"
)
assert total != frozen["combined_objective"]["total"], (
    f"Expected perturbed margin_hz to change combined total, but got same value {total}"
)

print("\nFAILURE PATH VERIFIED: perturbed bound produces different values.")
