"""Temporary failure demonstration: corrupt analytical root -> comparison fails."""

import sys
import os

# Add repo root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from eigenfrequencies.validation.beam.analytical import analytical_frequencies_cantilever

# Mock beam config with required attributes
class MockBeam:
    length = 1.0
    width = 0.1
    height = 0.01
    youngs_modulus = 210e9
    density = 7850.0
    cross_section_area = 0.1 * 0.01
    moment_of_inertia_y = 0.1 * 0.01**3 / 12
    moment_of_inertia_z = 0.01 * 0.1**3 / 12

beam = MockBeam()

# Golden FEM frequencies for this config (from tests/characterization/golden/beam.json)
fem_frequencies = np.array([
    8.39455014499035,
    53.07686426713339,
    83.07471261537489,
    157.8958968581103,
    188.84629117650178,
])

# Normal analytical frequencies
analytical_normal = analytical_frequencies_cantilever(beam, num_modes=5, axis="y")
print("Normal analytical frequencies:", analytical_normal)
print("FEM frequencies (first 5):", fem_frequencies[:5])

# Now corrupt the first analytical root by +5%
from eigenfrequencies.validation.beam import analytical as analytical_mod
original_compute_alpha = analytical_mod.compute_alpha_values

def corrupted_compute_alpha(num_modes, boundary_type="cantilever"):
    alphas = original_compute_alpha(num_modes, boundary_type)
    alphas[0] *= 1.05  # corrupt first root by +5%
    return alphas

analytical_mod.compute_alpha_values = corrupted_compute_alpha
analytical_corrupted = analytical_frequencies_cantilever(beam, num_modes=5, axis="y")
print("Corrupted analytical frequencies:", analytical_corrupted)

# Check the comparison would fail
TOLERANCE_PCT = 5.0
for i in range(min(5, len(analytical_corrupted))):
    fem_freq = fem_frequencies[i]
    ana_freq = analytical_corrupted[i]
    error_percent = abs(fem_freq - ana_freq) / ana_freq * 100
    status = "PASS" if error_percent < TOLERANCE_PCT else "FAIL"
    print(f"Mode {i+1}: FEM={fem_freq:.4f} Hz, Ana={ana_freq:.4f} Hz, Error={error_percent:.2f}% -> {status}")
    if status == "FAIL":
        print("FAILURE DEMONSTRATED: corrupted analytical root causes test failure")
        break

# Restore
analytical_mod.compute_alpha_values = original_compute_alpha
