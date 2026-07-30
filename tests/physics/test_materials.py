"""Tests for eigenfrequencies.materials — verify preset values."""

from eigenfrequencies.materials import laval_bronze, structural_steel


def test_structural_steel_values():
    """Structural steel preset matches the original turbine_runner defaults."""
    mat = structural_steel()
    assert mat.youngs_modulus == 210e9
    assert mat.density == 7850.0
    assert mat.poisson_ratio == 0.30


def test_laval_bronze_values():
    """Laval bronze preset matches the test-case validation material."""
    mat = laval_bronze()
    assert mat.youngs_modulus == 75.854e9
    assert mat.density == 8910.0
    assert mat.poisson_ratio == 0.34


def test_laval_bronze_is_distinct_from_steel():
    """The two presets are not accidentally identical."""
    steel = structural_steel()
    bronze = laval_bronze()
    assert steel.youngs_modulus != bronze.youngs_modulus
    assert steel.density != bronze.density
    assert steel.poisson_ratio != bronze.poisson_ratio
