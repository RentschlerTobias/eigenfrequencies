"""High-level dtOO adapter: ``DtooAdapter``.

Consumes a machine YAML file and exposes three operations:

* ``export_mesh(design_values) -> mesh_path`` — run dtOO + scale
* ``bc() -> BCConfig`` — boundary condition from the template
* ``design_bounds() -> dict[str, tuple[float, float]]`` — optimizer bounds

The adapter is importable without dtOO installed because the heavy dtOO
import is deferred to ``run_dtoo_export``.
"""

from pathlib import Path
from typing import Dict, List, Tuple, Union

from eigenfrequencies.adapters.dtoo.machine_yaml import MachineAdapterConfig, load_machine_yaml
from eigenfrequencies.bc.builders import clamp, foil_clamp, free_free
from eigenfrequencies.config import BCConfig


class DtooAdapter:
    """Drive dtOO parametric geometry export for a single machine case.

    Usage::

        adapter = DtooAdapter("configs/tistos.yaml")
        mesh_path = adapter.export_mesh({"cV_ru_bladeLength_0.5": 0.75})
        bc_cfg = adapter.bc()
        bounds = adapter.design_bounds()
    """

    def __init__(self, machine_yaml_path: str | Path):
        self.config = load_machine_yaml(machine_yaml_path)

    def export_mesh(self, design_values: Dict[str, float]) -> str:
        """Run dtOO, export the volume mesh, apply ``mesh_scale_factor``.

        Parameters
        ----------
        design_values:
            ``{label: value}`` overrides for dtOO const-values.

        Returns
        -------
        Absolute path to the (possibly scaled) ``.msh`` file.
        """
        # Lazy import so the adapter class is importable without dtOO.
        from eigenfrequencies.adapters.dtoo.export import run_dtoo_export

        return run_dtoo_export(self.config, design_values)

    def bc(self) -> BCConfig:
        """Return a ``BCConfig`` derived from ``bc_template``.

        Supported templates:

        * ``hub_clamp`` → ``clamp()`` (radius band around rotation axis)
        * ``foil_clamp`` → ``foil_clamp()`` (axial plane clamp)
        * ``free_free`` → ``free_free()`` (no clamp)
        """
        template = self.config.bc_template
        t = template.type
        params = template.params

        if t == "hub_clamp":
            return clamp(**params)
        if t == "foil_clamp":
            return foil_clamp(**params)
        if t == "free_free":
            return free_free()

        raise ValueError(
            f"Unknown bc_template.type {t!r}; expected hub_clamp, foil_clamp, or free_free"
        )

    def design_bounds(self) -> Dict[str, Tuple[float, float]]:
        """Return ``{label: (min, max)}`` for every design parameter."""
        return {
            label: (bounds.min, bounds.max)
            for label, bounds in self.config.design.items()
        }

    @property
    def axis(self) -> Union[str, List[float]]:
        """Rotation axis: ``"auto"`` or an explicit 3-vector."""
        return self.config.axis
