"""hydroflow-opt case plugin and evaluation worker.

`hydroflow-opt` owns the optimization loop; this package supplies the case: the
parameter space it searches and the worker that turns one candidate into an
objective. The contract is defined in hydroflow_opt.cases.CasePlugin and
documented in .omo/notes/hydroflow-contract.md.
"""

from eigenfrequencies.hydroflow.case import (
    MachineCasePlugin,
    NacaCase,
    TistosCase,
    machines_dir,
)

__all__ = [
    "MachineCasePlugin",
    "NacaCase",
    "TistosCase",
    "machines_dir",
]
