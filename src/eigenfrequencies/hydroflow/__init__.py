"""hydroflow-opt case plugin and evaluation worker.

`hydroflow-opt` owns the optimization loop; this package supplies the case: the
parameter space it searches and the worker that turns one candidate into an
objective. The contract is defined in hydroflow_opt.cases.CasePlugin and
documented in .omo/notes/hydroflow-contract.md.

The case classes are re-exported lazily. ``case`` imports ``hydroflow_opt``,
which lives only in the hydroflow venv (T8/Q9 keeps it out of the conda env),
while ``physics`` and ``worker`` are needed in both — an eager re-export would
make importing either of them fail wherever the optimizer is not installed.
"""

from typing import Any

__all__ = [
    "MachineCasePlugin",
    "NacaCase",
    "TistosCase",
    "machines_dir",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from eigenfrequencies.hydroflow import case

        return getattr(case, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
