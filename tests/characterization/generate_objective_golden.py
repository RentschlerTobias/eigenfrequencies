"""Generate golden objective_cases.json from de_history JSONL rows."""
import json
import os

from eigenfrequencies.config import CFDConfig, ObjectiveConfig, OptimizationConfig
from eigenfrequencies.penalty.band import _forbidden_intervals
from eigenfrequencies.penalty.objective import (
    cfd_scalar,
    combined_objective,
    resonance_term,
)

# Read rows from JSONL files
_HERE = os.path.dirname(os.path.abspath(__file__))
TURBINE_RUNNER_DIR = os.path.join(_HERE, "..", "..", "turbine_runner")

resonance_rows = []
resonance_path = os.path.join(TURBINE_RUNNER_DIR, "de_history_resonance_only.jsonl")
with open(resonance_path) as fh:
    for line in fh:
        resonance_rows.append(json.loads(line))

combined_rows = []
combined_path = os.path.join(TURBINE_RUNNER_DIR, "de_history_combined.jsonl")
with open(combined_path) as fh:
    for line in fh:
        combined_rows.append(json.loads(line))

# Build configs
opt_cfg = OptimizationConfig(n_rpm=72.0)
cfd_cfg = CFDConfig(n_rpm=72.0)
obj_cfg = ObjectiveConfig()

design_preset = "full30"

# Document the design preset and band bounds
intervals = _forbidden_intervals(opt_cfg)

cases = []
for i in range(5):
    res_row = resonance_rows[i]
    comb_row = combined_rows[i]

    frequencies = [float(res_row["f1"])]
    cfd_dict = {
        "eta": float(comb_row["eta"]),
        "vcav": float(comb_row["vcav"]),
        "dH": float(comb_row["dH"]),
    }

    f_res = resonance_term(frequencies, opt_cfg, obj_cfg)
    f_cfd = cfd_scalar(cfd_dict, cfd_cfg, obj_cfg)
    total, breakdown = combined_objective(cfd_dict, frequencies, cfd_cfg, opt_cfg, obj_cfg)

    case = {
        "source": {
            "file": "turbine_runner/de_history_resonance_only.jsonl",
            "line_index": i,
            "generation": res_row["gen"],
        },
        "cfd_source": {
            "file": "turbine_runner/de_history_combined.jsonl",
            "line_index": i,
            "generation": comb_row["gen"],
        },
        "design_preset": design_preset,
        "band_bounds": {
            "intervals": intervals,
            "Z_guidevanes": opt_cfg.Z_guidevanes,
            "n_rpm": opt_cfg.n_rpm,
            "max_harmonic": opt_cfg.max_harmonic,
            "margin_hz": opt_cfg.margin_hz,
            "margin_fraction": opt_cfg.margin_fraction,
            "penalty_k": opt_cfg.penalty_k,
        },
        "inputs": {
            "frequencies": frequencies,
            "cfd": cfd_dict,
        },
        "frozen": {
            "resonance_term": float(f_res),
            "cfd_scalar": float(f_cfd),
            "combined_objective": {
                "total": float(total),
                "breakdown": {k: v for k, v in breakdown.items()},
            },
        },
    }
    cases.append(case)

# Write golden file
out_dir = os.path.join(_HERE, "golden")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "objective_cases.json")
with open(out_path, "w") as fh:
    json.dump(cases, fh, indent=2)

print(f"Wrote {len(cases)} cases to {out_path}")
