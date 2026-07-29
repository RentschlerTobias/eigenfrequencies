"""Generate golden objective_cases.json from de_history JSONL rows."""
import json
import os
import sys

# Must set N_RPM before importing turbine_runner.config
os.environ["N_RPM"] = "72"

# Add turbine_runner to path so 'import objective' and 'import optimization' work
_HERE = os.path.dirname(os.path.abspath(__file__))
TURBINE_RUNNER_DIR = os.path.join(_HERE, "..", "..", "turbine_runner")
sys.path.insert(0, os.path.abspath(TURBINE_RUNNER_DIR))

from objective import cfd_scalar, resonance_term, combined_objective
from config import OptimizationConfig, ObjectiveConfig, CFDConfig

# Read rows from JSONL files
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
opt_cfg = OptimizationConfig()
cfd_cfg = CFDConfig()
obj_cfg = ObjectiveConfig()

# Document the design preset and band bounds
design_preset = os.environ.get("DESIGN_PRESET", "full30")

# Build forbidden intervals for documentation
import optimization
intervals = optimization._forbidden_intervals(opt_cfg)

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
