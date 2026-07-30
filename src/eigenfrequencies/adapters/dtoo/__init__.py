"""dtOO adapter: parametric geometry → volume mesh → eigenfrequencies.

Public API
----------
* ``MachineAdapterConfig`` — dataclass describing a dtOO machine case.
* ``load_machine_yaml(path)`` — strict YAML loader.
* ``DtooAdapter`` — high-level driver (export_mesh, bc, design_bounds).
* ``run_dtoo_export`` — low-level dtOO export pipeline (lazy import).
"""

from eigenfrequencies.adapters.dtoo.adapter import DtooAdapter
from eigenfrequencies.adapters.dtoo.machine_yaml import (
    BCTemplate,
    DesignBounds,
    MachineAdapterConfig,
    load_machine_yaml,
)

__all__ = [
    "BCTemplate",
    "DesignBounds",
    "DtooAdapter",
    "MachineAdapterConfig",
    "load_machine_yaml",
]
