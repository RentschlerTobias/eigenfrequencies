"""Axis discovery diagnostic.

Ported from ``turbine_runner/mesh_prep.py`` as an importable function that
returns structured data instead of only printing to stdout.
"""

from eigenfrequencies.config import MeshConfig
from eigenfrequencies.io.load import _read_msh


def inspect_mesh(mesh_cfg: MeshConfig, verbose: bool = True) -> dict:
    """Axis-discovery diagnostic: return coordinate bbox and per-axis spread.

    Run this once after the first dtOO export to identify the rotation axis and
    hub location, then set BCConfig accordingly (do NOT assume x=0 like the
    beam).

    Args:
        mesh_cfg: Mesh configuration (path + gdim).
        verbose: If ``True``, print the diagnostic table to stdout.

    Returns:
        Dict with keys ``file``, ``topology_dim``, ``num_nodes``, and
        ``axes`` (a dict of ``{"x": {"min", "max", "span"}, ...}``).
    """
    domain = _read_msh(mesh_cfg.msh_path, mesh_cfg.gdim)
    x = domain.geometry.x
    result = {
        "file": mesh_cfg.msh_path,
        "topology_dim": domain.topology.dim,
        "num_nodes": int(x.shape[0]),
        "axes": {},
    }
    for i, name in enumerate("xyz"):
        col = x[:, i]
        result["axes"][name] = {
            "min": float(col.min()),
            "max": float(col.max()),
            "span": float(col.max() - col.min()),
        }

    if verbose:
        print("=" * 60)
        print("Mesh axis-discovery diagnostic")
        print("=" * 60)
        print(f"file:          {mesh_cfg.msh_path}")
        print(f"topology.dim:  {domain.topology.dim}")
        print(f"num nodes:     {x.shape[0]}")
        for i, name in enumerate("xyz"):
            col = x[:, i]
            print(
                f"  {name}: min={col.min():+.4f}  max={col.max():+.4f}  "
                f"span={col.max() - col.min():.4f}"
            )
        print("Hint: the rotation axis is usually the longest span; the hub bore is")
        print(
            "near the axis at one axial end. Set BCConfig.axis / hub_radius / "
            "axial_min / axial_max from these ranges."
        )

    return result
