"""Material presets for structural modal analysis.

Provides ready-made ``MaterialConfig`` instances for common runner and
validation materials.
"""

from eigenfrequencies.config import MaterialConfig


def structural_steel() -> MaterialConfig:
    """Standard structural steel (default in ``turbine_runner/config.py``).

    E = 210 GPa, rho = 7850 kg/m^3, nu = 0.30
    """
    return MaterialConfig(
        youngs_modulus=210e9,
        density=7850.0,
        poisson_ratio=0.30,
    )


def laval_bronze() -> MaterialConfig:
    """Laval bronze used in the test-case validation disc.

    E = 75.854 GPa, rho = 8910 kg/m^3, nu = 0.34

    Source: experimental validation campaign (see turbine_runner/VALIDATION.md).
    """
    return MaterialConfig(
        youngs_modulus=75.854e9,
        density=8910.0,
        poisson_ratio=0.34,
    )
