"""Provenance tracking for reproducible runs.

Intended for later integration with dtOO design-state hashes,
container image digests, and solver version pinning.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Provenance:
    """Capture metadata about a single evaluation or optimization run."""

    package_version: str = "0.1.0"
    container_image: Optional[str] = None
    dtoo_state_hash: Optional[str] = None
    git_commit: Optional[str] = None
    timestamp: Optional[str] = None
    notes: list = field(default_factory=list)
