"""Case plugin exposing a dtOO machine as a hydroflow-opt parameter space.

One class serves every machine: the parameter space is just the ``design``
block of ``adapters/machines/<name>.yaml``, which has the same
``{label: {min, max}}`` shape for tistos (30 parameters) and naca alike. The
module-level ``TistosCase`` / ``NacaCase`` are the entry points registered in
the ``hydroflow_opt.cases`` group.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hydroflow_opt.models import ParameterSpace

from eigenfrequencies.adapters.dtoo import load_machine_yaml

# The catalog lookup lives with the YAML loader: the worker needs it too, and
# importing it from here would drag hydroflow_opt into every environment that
# only runs the physics (T8/Q9 keeps the optimizer out of the conda env).
from eigenfrequencies.adapters.dtoo.machine_yaml import (  # noqa: F401 - re-export
    MACHINES_DIR_ENV,
    machine_yaml_path,
    machines_dir,
)


class MachineCasePlugin:
    """hydroflow-opt case backed by a dtOO machine YAML.

    Args:
        machine: machine name, resolved to ``<machines_dir>/<machine>.yaml``.
    """

    def __init__(self, machine: str) -> None:
        self.machine = machine

    # ── Contract ──

    def parameter_space(self, options: dict[str, Any]) -> ParameterSpace:
        """Return the design bounds of the machine as a named space.

        Options:
            machine_yaml: explicit path, bypassing the catalog lookup.
            machine: override the machine name.
            parameters: optimize only this subset, in the given order.
        """
        config = load_machine_yaml(self._yaml_path(options))
        design = config.design

        selected = options.get("parameters")
        if selected is None:
            names = tuple(design)
        else:
            names = tuple(str(name) for name in selected)
            missing = [name for name in names if name not in design]
            if missing:
                raise ValueError(
                    f"machine {self.machine!r} has no design parameter(s): "
                    f"{', '.join(missing)}"
                )
        if not names:
            raise ValueError(f"machine {self.machine!r} declares no design parameters")

        return ParameterSpace(
            names=names,
            lower_bounds=tuple(design[name].min for name in names),
            upper_bounds=tuple(design[name].max for name in names),
        )

    def worker_command(self, request_path: Path, result_path: Path) -> list[str]:
        """Command evaluating one candidate in an isolated subprocess.

        Goes through ``sys.executable -m`` rather than a console script: the
        script only resolves when its bin/ is on PATH, which does not hold for
        a non-activated conda env or inside the cluster container.
        """
        return [
            sys.executable,
            "-m",
            "eigenfrequencies.hydroflow.worker",
            "--machine",
            self.machine,
            str(request_path),
            str(result_path),
        ]

    # ── Internals ──

    def _yaml_path(self, options: dict[str, Any]) -> Path:
        explicit = options.get("machine_yaml")
        if explicit:
            return Path(explicit)
        return machine_yaml_path(options.get("machine", self.machine))


class TistosCase(MachineCasePlugin):
    """Tistos axial runner — 30 design parameters, CFD + modal."""

    def __init__(self) -> None:
        super().__init__("tistos")


class NacaCase(MachineCasePlugin):
    """NACA foil — small case used to exercise the chain before tistos."""

    def __init__(self) -> None:
        super().__init__("naca")
