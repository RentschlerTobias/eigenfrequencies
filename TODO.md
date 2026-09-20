# TODO: Rotation-axis detection for single flow channel meshes

**Status:** idea / not yet implemented — no code changes yet.

## Context

`inspect_mesh` (`src/eigenfrequencies/io/axis.py`) currently identifies the
rotation axis with a **"longest span" heuristic**: the coordinate axis with the
largest bbox span is assumed to be the machine's rotation axis.

This works for axial machines, but is wrong in general:

| Machine type        | Rotation axis                              | "longest span" heuristic      |
|---------------------|--------------------------------------------|-------------------------------|
| Axial (runner)      | longitudinal axis                          | usually correct               |
| Francis / radial    | axis perpendicular to main flow, wheel in transverse plane | can be wrong |

**Key constraint:** we always mesh **one single flow channel** (one periodic
sector of the machine), not the full 360° body.

```
Full annulus (mental model):          Our mesh = one wedge only:

      /  ch3  |  ch4  \                       φ1 ╱╲
     |────────┼────────|                 ....  ╱    ╲  ....
      \  ch2  |  ch1  /                  φ2  ╱ HUB    ╲
                                          ╲  SHROUD  ╱
          rotation axis at center           ╲______╱
```

Consequences for detection:

- Material is **not** distributed over all angles φ — only over the sector
  wedge with opening angle `Δ = 2π/Z`.
- The hub and shroud surfaces are **surfaces of revolution**: within the wedge,
  their radial distance `r` depends only on axial position, **not on φ**.
- Bonus: the sector angle Δ directly yields the **blade count
  `Z = round(2π/Δ)`** — derivable from geometry alone (no dtOO metadata).

## Why previous approaches don't apply

1. **Inertia tensor eigenvalue degeneracy** — only valid for (approximately)
   rotationally symmetric *closed* bodies. A single wedge segment has no
   eigenvalue degeneracy; symmetry only appears after periodic replication.
2. **Polar-histogram uniformity score** — must be reformulated: the occupied
   angular range is the wedge Δ, not the full circle.

## Planned approach (`resolve_rotation_axis(mesh_cfg)`)

For each candidate axis `a` ∈ {+x̂, +ŷ, +ẑ} (sign irrelevant, φ is modulo π
orientation — check both orientations or normalize):

```
1. Project nodes:   r_i = |x_i - (x_i·â)â|
                    φ_i = atan2 around â  ∈ [0, 2π)
2. Determine occupied φ-bins (bins with > N_min nodes)
   → wedge angle Δ = angular extent, with gap detection
3. Per occupied φ-bin:  r_min(bin), r_max(bin)
4. Score = CV(r_min over bins) + CV(r_max over bins)
   → correct axis:   hub/shroud radii constant over φ  → score ≈ 0
   → wrong axis:     profiles drift                    → score large
5. Plausibility bonus: Δ close to 2π/Z for small integer Z ∈ {1..24}
```

```
correct axis:                     wrong axis:

r_max(φ)                          r_max(φ)
   │ ──────────────  constant       │       ____
   │                                │    ╱╱    ╲╲   ← drifts
   └───────────────► φ              └───────────────► φ
     score ≈ 0.01                      score ≈ 0.4
```

Output analogous to `inspect_mesh`:

```python
{
  "rotation_axis": "z",           # winning candidate
  "confidence": <score gap to runner-up>,
  "wedge_angle_deg": <Δ>,
  "suggested_z": <round(2π/Δ)>,
}
```

## Edge cases to handle

- **Δ interpretation**: only report `suggested_z = round(2π/Δ)` if the distance
  from Δ to the nearest `2π/Z` is below a tolerance (sectors can be meshed
  slightly distorted).
- **Score gap**: if the gap between best and second-best axis is small
  (< ε), do NOT auto-select — report "axis not unambiguous" and require an
  explicit `BCConfig.axis` value.
- **Extra domains attached to the channel** (inlet/outlet domains, nose):
  optionally restrict scoring to a configurable r/z window covering only the
  actual channel region.

## Where it should live

- `src/eigenfrequencies/io/axis.py`: new public function
  `resolve_rotation_axis(mesh_cfg) -> dict`, keep `inspect_mesh` as-is (or have
  it call the new function to replace the "longest span" hint text).

## Open questions (decide before implementation)

- [ ] Candidate axes: Cartesian only (x/y/z), or also free axes from PCA?
- [ ] Extract blade count `Z` as part of the result, or separate function?
- [ ] Tolerances: ε for the score gap, N_min per bin, Z plausibility window.
