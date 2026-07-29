"""Typed exception for solver configuration errors."""


class SolverConfigError(ValueError):
    """Raised when solver configuration is invalid or unsupported.

    Examples:
        - Unknown solver_backend value
        - SLEPc backend requested with a clamped boundary condition
        - Element degree / backend combination that is not supported
    """

    pass
