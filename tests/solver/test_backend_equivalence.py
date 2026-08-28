"""The two eigensolver backends must be a choice of numerics, not of physics.

``solver_backend`` is a config knob: scipy slices the constrained DOFs out of
the CSR matrices, SLEPc keeps the sparsity and pushes them to an infinite
eigenvalue by assembly. Both solve the same problem, so both must return the
same frequencies. If they ever drift apart, one of them is wrong and the choice
stops being free.
"""

import numpy as np
import pytest

from eigenfrequencies.config import BCConfig, MaterialConfig, MeshConfig, SolverConfig

pytest.importorskip("dolfinx", reason="requires the FEniCSx environment")
pytest.importorskip("slepc4py", reason="requires SLEPc")

from eigenfrequencies.io import load_and_prepare_mesh  # noqa: E402
from eigenfrequencies.solver import ModalSolver  # noqa: E402

_FIXTURE = "tests/fixtures/unit_box_coarse.msh"

#: The two paths agreed to 6e-14 % when this was written. A tolerance of 1e-6 %
#: leaves room for a different MUMPS or LAPACK build without letting a real
#: divergence through.
_REL_TOL_PERCENT = 1e-6


@pytest.fixture(scope="module")
def domain(pytestconfig):
    path = pytestconfig.rootpath / _FIXTURE
    if not path.is_file():
        pytest.skip(f"fixture mesh missing: {path}")
    return load_and_prepare_mesh(MeshConfig(msh_path=str(path)))


def _frequencies(domain, bc_config, backend):
    solver = ModalSolver(
        domain,
        MaterialConfig(),
        bc_config,
        SolverConfig(num_eigenvalues=5, element_degree=2, solver_backend=backend),
    )
    eigenvalues, _ = solver.solve()
    assert solver.backend_used == backend
    return solver.compute_frequencies(eigenvalues)


@pytest.mark.requires_container
class TestBackendEquivalence:
    def test_backends_agree_on_the_clamped_problem(self, domain):
        bc = BCConfig(mode="axial_plane", axis="z", plane_value=0.0)
        scipy_hz = _frequencies(domain, bc, "scipy")
        slepc_hz = _frequencies(domain, bc, "slepc")

        assert len(slepc_hz) == len(scipy_hz)
        deviation = np.abs(slepc_hz - scipy_hz) / scipy_hz * 100
        assert deviation.max() < _REL_TOL_PERCENT, (
            f"backends disagree by {deviation.max():.3g} %: "
            f"scipy={scipy_hz}, slepc={slepc_hz}"
        )

    def test_the_clamped_spectrum_has_no_rigid_body_modes(self, domain):
        bc = BCConfig(mode="axial_plane", axis="z", plane_value=0.0)
        assert np.all(_frequencies(domain, bc, "slepc") > 1.0)

    def test_free_free_still_finds_its_rigid_body_modes(self, domain):
        """The path that existed before the clamp support, unchanged.

        A free-floating body has six zero-frequency rigid-body modes; their
        presence is what says the assembly was not accidentally constrained.
        """
        frequencies = _frequencies(domain, BCConfig(mode="free"), "slepc")
        assert np.sum(frequencies < 1e-3) >= 1
