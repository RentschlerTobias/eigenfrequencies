# Speaker & Q&A Companion — *Eigenfrequency-Aware CFD Shape Optimization of Hydraulic Turbines*

Detailed, per-slide explanations with every formula unpacked in plain prose, plus
anticipated audience questions and answers. Read top-to-bottom to rehearse; jump
to a slide during Q&A. One-line summary of the whole talk:

> We taught our in-house hydraulic shape optimizer (**dtOO**) a new, **structural**
> objective — keep the runner's natural frequencies away from the excitation the
> guide vanes impose — validated the modal solver against analytics and real
> measurements, wrapped it in a parallel evolutionary optimizer, and ran it on a
> cluster.

---

# 1 · Introduction

## 1.1 Motivation

**Shown:** a cycle graph — *Design → CFD → Stresses → Frequencies →* (back to Design),
with a central *coupled optimizer* driving all three at once.

**The story.** Classical turbine design is *siloed and sequential*. The
fluid-mechanics group runs the CFD and hands a geometry to the structural group,
who compute stresses and eigenfrequencies, then hand corrections back. Each loop
is a slow, manual hand-off — "one discipline at a time". The dashed grey ring is
this traditional hand-off; the dark hub with coloured spokes is the thesis: a
single optimizer that optimizes **fluid performance, stresses and frequencies
simultaneously**.

**Why it matters:** the three objectives are coupled — a shape change that helps
efficiency can move an eigenfrequency into a dangerous band. Optimizing them
separately means endless back-and-forth; optimizing them jointly finds a design
that satisfies all three at once.

**Likely questions**

- *Why not just optimize sequentially?* Because the objectives conflict; a
  sequential loop can oscillate and never converge to a joint optimum, and every
  hand-off costs days.
- *What does this project actually add?* The **frequency** node — the structural
  eigenfrequency objective — into an optimizer that previously only saw fluid
  objectives.

## 1.2 Project context & goal

**Shown:** DFG SPP 2335 context, the goal, dtOO's existing objectives, the new
objective, and the scope.

**In depth.** This is the final report of a three-month Stuttgart–Laval exchange
inside DFG Priority Programme **SPP 2335** ("Daring More Intelligence — Design
Assistants in Mechanics and Dynamics"). The programme theme is AI-driven shape
optimization and island-model parallelization for hydraulic machines.

**dtOO** is IHS's in-house shape optimizer for hydraulic machines. Until now it
only optimized **hydraulic** objectives:

- **η (efficiency)** — how much of the water's energy the runner converts.
- **V_cav (cavitation volume)** — volume where pressure drops below vapour
  pressure and bubbles form (erosion, noise, losses); want it small.
- **ΔH (design head)** — the pressure head the machine is designed for; the
  design must hit a target head.

This project adds a **structural eigenfrequency objective**: avoid resonance of
the runner under blade-passing excitation. Deliverable: a **standalone,
open-source, pip-installable** modal-analysis framework that works on its own and
couples cleanly to dtOO. **Scope:** three optimization modes — CFD-only,
modal-only, combined — validated on Laval Francis-runner reference data.

**Likely questions**

- *What is a Francis runner?* The rotating bladed wheel of a Francis turbine
  (radial-inflow reaction turbine), the workhorse of medium-head hydropower.
- *Why open-source / standalone?* So the modal objective is reusable beyond dtOO
  and by non-dtOO users.

## 1.3 Why eigenfrequencies matter

**Shown (left):** excitation & resonance, with the blade-passing frequency
formula. **(right):** the role of the still fluid.

### The formula: \( f_{bp} = \dfrac{Z\,n}{60} \)

Read it as: **blade-passing frequency = (number of guide vanes × rotational
speed) ÷ 60**.

- **Z** = number of guide vanes (the stationary blades upstream that meter the
  flow). Each time a runner blade passes a guide vane, it feels a pressure pulse.
- **n** = rotational speed in **revolutions per minute (RPM)**.
- **÷ 60** converts RPM to revolutions **per second (Hz)**.

So in one second the runner turns *n/60* times, and each turn it passes *Z*
vanes, giving *Z·n/60* pressure pulses per second — a forcing frequency in Hz.
For the **Tistos runner**: Z = 18, n = 90 RPM → f_bp = 18·90/60 = **27 Hz**, plus
its integer **harmonics** (2×, 3×, 4× → 54, 81, 108 Hz).

**Key point:** this excitation frequency is **kinematic** — fixed purely by vane
count and speed. **No CFD is needed** to know it. That is what makes the
frequency objective cheap to evaluate relative to a full flow simulation.

**Resonance** = an eigenfrequency (natural frequency) of the runner lands inside
an excitation band around f_bp or a harmonic. At resonance, small periodic forces
produce large vibration amplitudes → fatigue, cracks, possibly failure. The
optimizer's job: keep every modal frequency **out of the forbidden bands**.

### The role of the still fluid (right column)

- **Added mass:** a runner vibrating in water drags surrounding water with it.
  The effective mass rises, so **wet** eigenfrequencies are **lower** than **dry**
  (in-air) ones — typically by **20–40 %**, and the amount depends on geometry.
- **Static (still) fluid has no resonance of its own** — resonance needs a
  *time-varying* excitation (the blade passing). Standing water only adds mass.
- **Full fluid–structure interaction (FSI)** — coupling Helmholtz acoustics of
  the water with the elasticity of the structure — is the long-term goal. **This
  exchange delivers the dry-mode foundation** on which the wet coupling is built.

**Likely questions**

- *Why work with dry modes if wet modes are what matter in operation?* Dry modes
  are the validated baseline; the wet correction (added mass) is a known,
  monotonic shift (~15–40 % down) added on top. You must trust the dry solver
  first.
- *Isn't 27 Hz very low?* Yes — low-speed machine (90 RPM). The runner's first
  structural modes are hundreds of Hz, so we mostly worry about higher harmonics
  and specific mode families falling into bands.
- *What sets the band width?* A safety margin around f_bp and harmonics; the code
  can use a fixed band or the kinematic band derived from f_bp.

## 1.4 Project roadmap

**Shown:** a three-node timeline — **① Modal in vacuum (we are here) → ② Fluid–
structure interaction → ③ Data-driven surrogate**.

- **Stage 1 — Modal in vacuum (current):** dry eigenfrequencies of the runner;
  solver validated (beam + experiment + reference solvers); dry modes wired into
  the optimizer cost function; runs executing on the cluster.
- **Stage 2 — FSI:** linear elasticity + Helmholtz acoustics + coupling; wet
  added-mass and pre-stress enter the modal solve.
- **Stage 3 — Data-driven surrogate:** a surrogate model + transfer learning to
  accelerate the coupled optimization (replace expensive evaluations with fast
  predictions).

**Likely questions**

- *What is "pre-stress"?* Static loads (centrifugal, pressure) stiffen or soften
  the structure and shift eigenfrequencies; a stress-stiffening term in the modal
  solve. Minor effect here, larger in some machines.
- *Why a surrogate later?* Each combined evaluation is a full CFD + modal run;
  a surrogate learns the objective landscape to cut the number of true runs.

---

# 2 · Beam Testcase (validating the solver on a known analytic case)

## 2.1 Beam Testcase — Analytical Theory

**Shown (left):** the derivation from PDE to characteristic equation. **(right):**
the dimensionless eigenvalues and how frequencies follow.

**Why this slide exists:** before trusting the 3D solver on a complicated runner,
test it on a case with an **exact closed-form answer** — the cantilever
Euler–Bernoulli beam (clamped at one end, free at the other).

### Governing equation: \( EI\,\dfrac{\partial^4 w}{\partial x^4} + \rho A\,\dfrac{\partial^2 w}{\partial t^2} = 0 \)

This is the **Euler–Bernoulli beam equation** for free bending vibration. In words:

- **w(x,t)** = the sideways deflection of the beam at position *x*, time *t*.
- **EI** = *bending stiffness*: **E** Young's modulus (material stiffness) times
  **I** the second moment of area (how the cross-section resists bending).
- **ρA** = *mass per unit length*: **ρ** density times **A** cross-sectional area.
- The first term is the elastic restoring force (fourth spatial derivative —
  bending resists curvature-of-curvature); the second is inertia (acceleration).
  Setting their sum to zero is Newton's law for a vibrating beam with no external
  load.

### Separation of variables → ODE

Assume the beam vibrates in a fixed **shape** φ(x) oscillating in time:
\( w(x,t) = \varphi(x)\,e^{i\omega t} \). Substituting turns the PDE into an
ordinary differential equation in space only:
\( \varphi'''' - \beta^4\varphi = 0 \) with \( \beta^4 = \dfrac{\rho A\,\omega^2}{EI} \).

- **φ(x)** is the **mode shape**; **ω** the angular frequency.
- **β** bundles material, geometry and frequency into one number. Its fourth
  power is proportional to ω² — that is the seed of "frequency grows fast".

### General solution + boundary conditions

The ODE's general solution is a combination of **sin, cos, sinh, cosh**. Four
constants are fixed by the four **cantilever boundary conditions**:

- **Clamped end (x = 0):** deflection zero and slope zero → \( \varphi(0)=0,\ \varphi'(0)=0 \).
  (The wall holds the beam in place and flat.)
- **Free end (x = L):** bending moment zero and shear force zero →
  \( \varphi''(L)=0,\ \varphi'''(L)=0 \). (Nothing pushes on the free tip.)

### Characteristic equation: \( \cos\alpha\,\cosh\alpha = -1 \), with \( \alpha \equiv \beta L \)

Requiring a **non-trivial** solution (a real vibration, not the zero solution)
forces the 4×4 determinant of the boundary conditions to vanish. That condition
collapses to this single transcendental equation. Its roots are the allowed
**α = βL** — a **dimensionless** eigenvalue combining β and the length L.

### From α to frequency (right column)

The first roots are universal numbers:
\( \alpha_1\approx1.875,\ \alpha_2\approx4.694,\ \alpha_3\approx7.855 \)
(higher ones approach \( (2n-1)\pi/2 \)). They **encode only the mode shape and
boundary condition** — independent of material or units.

Invert β = α/L and use β⁴ = ρAω²/EI to get the frequency:
\[
\omega_n = \left(\frac{\alpha_n}{L}\right)^2\sqrt{\frac{EI}{\rho A}},\qquad
f_n = \frac{\omega_n}{2\pi}.
\]

- **ω_n** scales with **α_n²** and with **1/L²** (longer beams → lower notes),
  and with **√(EI/ρA)** (stiffer/lighter → higher notes).
- **f_n = ω_n/2π** just converts angular frequency (rad/s) to Hz.

Because frequency scales with **α²**, the modes spread out fast:
α₁²=3.52, α₂²=22.0, α₃²=61.7 → **f₂/f₁ ≈ 6.3, f₃/f₁ ≈ 17.5**.

**The clean-test point:** the α-roots are exact and unit-free; once you plug in a
material (E, ρ) and geometry (I, A, L), you get exact reference frequencies to
compare the solver against.

**Likely questions**

- *Why Euler–Bernoulli and not Timoshenko?* E–B is the simplest slender-beam
  theory (ignores shear deformation & rotary inertia) — perfect as a first exact
  reference. Its limits show up as small deviations at higher modes (next slides).
- *What is a "mode shape"?* The spatial pattern of a natural vibration (first
  bending, second bending with one internal node, etc.). Each has its own
  frequency.
- *Why is α dimensionless useful?* It separates "which shape" (universal math)
  from "what frequency" (your specific material & size) — a clean way to validate.

## 2.2 Beam Testcase — 3D FEM solver

**Shown (left):** discretization to a matrix eigenproblem + the FEniCSx/SLEPc
stack. **(right):** P1 vs P2 Lagrange elements.

### From PDE to matrices: \( K\,\phi = \omega^2 M\,\phi \)

Real 3D geometry has no closed-form solution, so we discretize with the
**finite-element method (FEM)**. The continuous 3D **elasticity** eigenvalue
problem becomes a **generalized matrix eigenvalue problem**:

- **K** = **stiffness matrix** — the discrete elastic restoring forces (built
  from E, ν and the mesh).
- **M** = **mass matrix** — the discrete inertia (built from ρ and the mesh).
- **φ** = the **mode-shape vector** (nodal displacements); **ω²** the eigenvalue.
- Reading it: "elastic force = ω² × inertia" — the discrete analogue of the beam
  PDE. Solving it yields pairs (ω_n², φ_n) = (frequency², mode shape).

### The software stack

- **FEniCSx (DOLFINx core):** open-source FEM library. It defines the weak form,
  meshes the geometry, and **assembles** K and M.
- **SLEPc** (on **PETSc**): a sparse **eigen**solver. It uses a **Krylov–Schur**
  iteration with a **shift-invert** spectral transformation to target the
  **lowest** frequencies efficiently (shift-invert turns "smallest eigenvalues,"
  which iterative solvers find slowly, into "largest," which they find fast). The
  inner linear systems are solved by a **direct LU factorization (MUMPS)**. GHEP =
  *generalized Hermitian eigenvalue problem* (K, M symmetric → real eigenvalues).

### Lagrange elements — P1 vs P2 (right)

The mesh is tetrahedra; the displacement field inside each is a polynomial:

- **P1 — linear, 4-node tetrahedron:** unknowns only at the 4 corners.
  Cheap, but **over-stiff in bending** — it can't curve within an element, so
  bending modes converge slowly and come out too high.
- **P2 — quadratic, 10-node tetrahedron:** adds a node at each of the 6 edge
  midpoints. It represents curvature within an element → **far more accurate per
  degree of freedom** for bending and curved mode shapes.
- **Choice: P2** — trustworthy eigenfrequencies without an absurdly fine mesh.

**Likely questions**

- *What is the weak (variational) form?* The integral form of the PDE that FEM
  actually solves; multiplying by test functions and integrating turns
  derivatives into an assembleable bilinear form → K and M.
- *Why shift-invert?* We want the few lowest modes; shift-invert around a target
  makes those the dominant, fast-converging eigenvalues of the transformed
  problem.
- *Why a direct solver (MUMPS) inside?* Shift-invert needs to solve (K − σM)x = b
  repeatedly; a direct LU factorization is robust and reusable across iterations.
- *Generalized vs standard eigenproblem?* Because M ≠ identity (consistent mass
  matrix); GHEP handles Kφ = ω²Mφ directly.

## 2.3 Beam validation — Results (Analytical vs Numerical)

**Shown:** the interactive mode viewer + bullets comparing FEM vs analytical.

**In depth.** The 3D solver, run on a **meshed 3D beam** (not the 1D equation),
reproduces the analytical Euler–Bernoulli bending frequencies to engineering
accuracy — e.g. **Mode 1: 8.4 Hz (FEM) vs 8.4 Hz (analytical)**. Two honest
caveats, both physically expected:

- **Higher modes deviate slightly** because Euler–Bernoulli is a *slender-beam
  approximation* (no shear / 3D effects); the real 3D solid is slightly less
  stiff, and the gap grows with mode number.
- **The 3D solve also finds torsion modes** that the 1D bending model simply does
  not contain — extra physics, not error.

**Validation passed → the solver is trustworthy for the real 3D runner.** The
viewer lets you step through the mode shapes live.

**Likely questions**

- *Why do higher modes drift?* Slender-beam theory omits shear; real modes are a
  touch lower. Expected and bounded.
- *Is 8.4/8.4 suspicious (too perfect)?* Mode 1 is the easiest to nail; the point
  is the *trend* across modes stays within tolerance.

---

# 3 · 3D Testcase (validating against real measurements)

## 3.1 3D validation

**Shown:** the bronze-disc hammer-impact validation, mesh + solver specs, and the
headline "PASSED · all measured modes within 5 %".

**In depth.** Stronger than the beam: compare the solver against **real
hammer-impact measurements** of a **bronze disc**, provided by the Laval group.

- **Free–free boundary conditions** (disc hanging freely) → the first **6 modes
  are rigid-body** (3 translations + 3 rotations, zero frequency) and are
  discarded; only elastic modes count.
- Disc: diameter 0.2 m, thickness 87 mm, mass ≈ 5.99 kg; bronze E = 75.85 GPa,
  ρ = 8910 kg/m³, ν = 0.34 (**ν** = Poisson's ratio, lateral-to-axial strain).
- **Mesh:** 325 000 quadratic tetrahedra (tet10, P2) → **1.96 million vector
  degrees of freedom** (3 displacement components per node).
- **Solver:** FEniCSx + SLEPc, GHEP with shift-invert and LU/MUMPS.

Result: **all measured modes within 5 %** — the solver is trustworthy on real 3D
geometry, not just an idealized beam.

**Likely questions**

- *Why a bronze disc, not the runner?* The disc has trusted measurements and is
  simple enough to be an unambiguous benchmark; the runner has no such reference.
- *Why free-free (not clamped)?* It matches the experiment (disc suspended by
  soft cords), and avoids modelling an uncertain clamp stiffness.
- *What's a rigid-body mode?* A zero-frequency "mode" that is pure translation or
  rotation — no elastic deformation; discarded.

## 3.2 Measured modes & the case for P2

**Shown (left):** FEniCSx vs experiment vs ANSYS table. **(right):** P1 vs P2
error table — the core justification for P2.

**Left table (accuracy).** Modes are labelled by **nodal-diameter (ND)** family —
"1ND", "2ND", … — patterns with 1, 2, … diameters of zero motion across the disc,
plus a torsion mode:

| Mode | FEniCSx (Hz) | Experiment | Δexp | ANSYS | ΔANSYS |
|---|---|---|---|---|---|
| 1ND | 192.45 | 192.8 | −0.18 % | 191.6 | +0.44 % |
| Tors. | 223.73 | — (not measured) | — | 226.0 | −1.01 % |
| 2ND | 290.16 | 299.13 | −3.00 % | 293.63 | −1.18 % |
| 3ND | 693.92 | 712.0 | −2.54 % | 703.25 | −1.33 % |
| 4ND | 1291.50 | 1320.0 | −2.16 % | 1310.88 | −1.48 % |

- All **Δexp ≤ 3 %** (vs measurement), all **ΔANSYS ≤ 1.5 %** (vs the commercial
  reference solver). Our open-source stack matches ANSYS.
- **ND modes are degenerate sin/cos pairs**: two mode shapes at (ideally) the same
  frequency, rotated 90°. Our split is < 0.1 Hz → the mesh preserves the disc's
  rotational **symmetry** (a good numerical-quality check). **Torsion is a
  singlet** (no pair) and was not measured experimentally.

**Right table (why P2).**

| Mode | P1 tet4 | P2 tet10 |
|---|---|---|
| 1ND | +19.95 % | −0.18 % |
| 2ND | +19.16 % | −3.00 % |
| 3ND | +20.06 % | −2.54 % |
| 4ND | +14.43 % | −2.16 % |

- **Linear P1 tetrahedra over-stiffen bending by 14–20 %** — a huge, systematic
  bias that makes them **unusable** for modal analysis.
- **Quadratic P2 tetrahedra remove the bias** (errors drop to a few percent).
- Hence the decision: **P2 + SLEPc/MUMPS at ~2 M DOFs**, accepting the higher cost
  for correct physics.

**Likely questions**

- *Why is P1 so wrong?* Linear elements represent constant strain per element;
  bending needs strain to vary linearly across the thickness — P1 can't, so it
  looks artificially stiff ("shear/volumetric locking" family of effects).
- *Why does ANSYS beat you slightly?* Different element formulations/mesh; both
  are within measurement uncertainty — the point is parity with a trusted tool.
- *What is a nodal diameter?* Lines across the disc where the mode has zero
  displacement; n of them = "nND". Common language for disc/bladed-disc modes.
- *Why care about the sin/cos degeneracy split?* A large split would signal a
  mesh that broke the disc's symmetry — a numerical artefact. < 0.1 Hz = clean.

---

# 4 · Eigenfrequency-Aware Optimization

## 4.1 Objective function

**Shown (left):** four stacked formulas — total loss, penalty, reward, CFD loss.
**(right):** the penalty–reward curve.

The optimizer **minimizes a single scalar loss**. Lower = better.

### Total: \( f_{\text{total}} = f_{\text{CFD}} + f_{\text{res}} \)

Two contributions added: a **hydraulic** part (f_CFD) and a **resonance** part
(f_res). f_res itself is *penalty − reward* over the eigenfrequencies (below).

### Penalty: \( p(f)=\sum_{h=1}^{4} k\,\min(f-D_{h,\text{lo}},\ D_{h,\text{hi}}-f)\ \text{if } f\in D_h,\ \text{else } 0 \)

Read term by term:

- Sum over **h = 1…4** = the four **forbidden bands** D_h (around f_bp and its
  first three harmonics — 27, 54, 81, 108 Hz).
- For an eigenfrequency **f** that falls **inside** band h (between its low edge
  D_{h,lo} and high edge D_{h,hi}): the term is **k · min(distance-to-low-edge,
  distance-to-high-edge)**. That "min of the two edge distances" is **zero at the
  edges and maximal at the band centre** → a **triangular penalty**: the deeper
  into a forbidden band, the larger the punishment.
- **k** is a scaling constant (penalty strength). If f is outside every band, the
  contribution is 0.

### Reward: \( r(f)=\sum_{j=1}^{J} k\,\min(f-G_{j,\text{lo}},\ G_{j,\text{hi}}-f)\ \text{if } f\in G_j,\ \text{else } 0 \)

Same triangular shape, but over the **safe gaps G_j** *between* the forbidden
bands. It is **maximal at the centre of a gap**. Subtracting the reward means the
optimizer is **actively pulled toward the middle of a safe gap**, not merely
"just outside" a band. This prevents fragile boundary solutions that hover on a
band edge and would resonate under any small modelling error or operating drift.

### CFD loss: \( f_{\text{CFD}} = w_\eta\tanh|1-\eta| + w_{\text{cav}}\tanh(V_{\text{cav}}\,10^{6}) + w_{\text{head}}\tanh|dH - dH_{\text{t}}| \)

Three hydraulic terms, each **weighted (w)** and wrapped in **tanh**:

- **Efficiency:** \(|1-\eta|\) — distance of efficiency η from the ideal 1.0
  (100 %). Zero when perfect.
- **Cavitation:** \(V_{\text{cav}}\cdot10^{6}\) — cavitation volume scaled up by a
  million (physical volumes are tiny) so it's numerically comparable; want small.
- **Head:** \(|dH - dH_{\text{t}}|\) — deviation of the achieved head dH from the
  target head dH_t.
- **Why tanh?** It **saturates** (→ 1 for large inputs), so a single terrible
  outlier can't dominate the whole objective; it keeps the three hydraulic terms
  on comparable, bounded scales. The **w**'s set their relative importance.

**Likely questions**

- *Why penalty AND reward (not just penalty)?* Penalty alone lets solutions sit
  exactly on a band edge (zero penalty). The reward creates a positive gradient
  toward gap centres → robust margins.
- *Where do the band edges come from?* From f_bp = Z·n/60 and its harmonics plus
  a safety margin — kinematic, no CFD needed.
- *Are CFD and resonance on the same scale?* The weights and tanh-scaling are
  chosen to balance them; in modal-only runs f_CFD is switched off.
- *Is it differentiable?* The triangular min() has kinks, but we use a
  derivative-free optimizer (Differential Evolution), so smoothness isn't
  required.

## 4.2 Geometry parameterization

**Shown (left):** how the blade is parameterized. **(right):** a schematic + the
3D blade.

**In depth.** dtOO describes the runner blade with **30 continuous shape
variables**, each defined at **three spanwise sections** — **hub (root), mid-span,
tip**. Interpolating between the sections gives the full 3D blade. The variables
control:

- **Inlet & outlet flow angles** — the blade angle where flow enters and leaves
  (the outlet/"exit" angle is the strongest resonance lever, see sensitivity).
- **Length (chord)** — how long the blade is in the flow direction.
- **Thickness distribution** — thickness at leading edge → mid-chord → trailing
  edge.
- **Meridional & circumferential position** — where the section sits in the
  runner passage (its offset along the through-flow direction and around the
  axis).

**Export:** dtOO writes **geometry only** → `runner.msh` (via **OpenCascade** CAD
kernel + **GMSH** mesher) for the modal solver. **No CFD mesh** is produced here —
the modal objective needs only the structural mesh, which is why the frequency
objective is comparatively cheap.

The strongest resonance levers are the **mid-span shape** and the **outlet
(trailing-edge) angle** (quantified next slide).

**Likely questions**

- *Why three sections?* A practical compromise: enough to shape hub-to-tip twist
  and thickness, few enough to keep the design space tractable (30 variables).
- *Why no CFD mesh here?* Eigenfrequencies depend on the *structure* (geometry +
  material), not the flow; only the solid mesh is needed.
- *What is dtOO?* IHS's in-house parametric geometry + optimization tool for
  hydraulic machines (OpenCascade-based).

## 4.3 Parameter sensitivity

**Shown (left):** a Spearman-correlation ranking of parameters vs the resonance
penalty. **(right):** best/worst mode penalties.

**In depth.** From the first **31 valid DE individuals**, compute the **Spearman
rank correlation ρ** between each design variable and the resonance objective.
Spearman measures **monotonic** association on **ranks** (robust to non-linearity
and outliers): ρ near ±1 = strong monotone link, near 0 = none. Top drivers:

| Rank | Parameter (label) | ρ | Meaning |
|---|---|---|---|
| 1 | α₂_ex_1.0 | −0.732 | outlet (exit) blade angle at the **tip** |
| 2 | offsetM_ex_0.5 | +0.723 | meridional offset at **mid-span** |
| 3 | t_mid_a_0.5 | −0.715 | **mid-chord thickness** at mid-span |
| 4 | offsetΦ_R_ex_0.5 | −0.625 | circumferential (Φ) offset at mid-span |
| 5 | offsetM_ex_1.0 | −0.624 | meridional offset at the tip |
| 6 | bladeLength_0.5 | −0.575 | blade length (chord) at mid-span |

The **sign** tells direction (increase the parameter → penalty rises (+) or falls
(−)); the **magnitude** tells importance. The **outlet angle at the tip**,
**mid-span meridional position** and **mid-chord thickness** dominate (|ρ| > 0.7).
These are the **critical levers for resonance avoidance** — and explain why the
optimizer concentrates its search on exactly these parameters in later
generations.

**Likely questions**

- *Why Spearman, not Pearson?* Spearman uses ranks → robust to non-linear but
  monotone relationships and to outliers; we only care which knobs matter, not a
  linear fit.
- *Only 31 individuals — is that enough?* It is an early, indicative screening;
  correlations > 0.7 from 31 samples are already meaningful for prioritising, and
  they agree with engineering intuition (trailing edge drives modes).
- *Correlation ≠ causation?* True; but here the variables are independent design
  inputs we perturb, so a strong rank correlation with the output is a genuine
  sensitivity.

## 4.4 Best vs. worst blade shape

**Shown:** the lowest- and highest-objective individuals side by side.

**In depth.** The two extremes of the population make the objective tangible:

- **Best — resonance objective 4.90:** all eigenfrequencies sit **clear of the
  blade-passing bands**.
- **Worst — objective 11.88:** an eigenfrequency sits **deep inside a forbidden
  band** → heavy penalty.
Comparing the shapes shows the optimizer reshaping mainly the **mid-span and the
trailing edge** — exactly the parameters the sensitivity flagged. This closes the
loop: sensitivity says which knobs matter → the optimizer turns those knobs.

**Likely questions**

- *Is "worst" a failed run?* No — it is a valid individual that simply scores
  badly; useful as the contrast that shows what the objective is avoiding.
- *Lower objective = better?* Yes, the whole loss is minimized.

---

# 5 · Optimization, Parallelization, Tooling

## 5.1 Differential Evolution

**Shown:** the per-generation DE loop (Population → Mutation → Crossover →
Selection → next generation) + parameter bullets.

**In depth.** **Differential Evolution (DE)** is a population-based, derivative-
free evolutionary optimizer — ideal for our noisy, non-smooth, black-box
objective. Per generation, for each **target vector x_i** in the population:

1. **Mutation:** pick three *distinct random* members and form a **donor**:
   \( v = x_{r1} + F\,(x_{r2}-x_{r3}) \).
   The **difference vector** \((x_{r2}-x_{r3})\) is the population's own scale/
   direction of spread; **F = 0.8** scales it. Early on the population is spread
   out → big exploratory steps; as it converges the steps shrink automatically.
   This *self-scaling* is DE's key trick.
2. **Crossover:** mix donor and target coordinate-by-coordinate into a **trial u**
   with rate **CR = 0.9** (≈ 90 % of coordinates come from the donor).
3. **Greedy selection:** evaluate the trial; **keep it only if it lowers f_total**,
   else keep the target. The population never gets worse.

**Settings:** population **NP = 20** (up to 32 on the cluster), F = 0.8, CR = 0.9,
budget **≤ 30 generations ≈ 600 evaluations**. Variant used in runs:
**DE/rand/1/bin** (random base vector, one difference, binomial crossover).

**Likely questions**

- *Why DE, not gradient descent?* The objective is non-smooth (triangular
  penalties), possibly noisy, and a black box (CFD/modal solvers). DE needs no
  gradients and handles multimodal landscapes.
- *What do F and CR do?* F scales the mutation step (exploration); CR controls how
  much of the donor enters the trial (higher = more aggressive change).
- *What's "DE/rand/1/bin"?* Base vector = random member; "1" difference vector;
  "bin" = binomial (independent per-coordinate) crossover.
- *Why greedy selection?* Guarantees monotone improvement of each slot → stable
  convergence.
- *600 evaluations — is that a lot?* Each is a full geometry build + modal (and
  optionally CFD) solve, so 600 is substantial compute — hence parallelization.

## 5.2 Pyro5 parallelization

**Shown:** a coordinator hub + N workers, each running CFD + modal, with dispatch/
return arrows.

**In depth.** Each fitness evaluation is a full pipeline run, so we distribute
them across the cluster:

- **One DE client (coordinator)** + **N persistent worker processes**, one per
  **srun step** (Slurm task). Persistent = started once, reused across many
  evaluations (no per-job startup cost).
- Each **worker evaluates one design**: runs the **CFD** (simpleFoam) and the
  **modal** solve (FEniCSx / SLEPc), combines them into **f_total**, and returns
  it. The coordinator dispatches design vectors and collects fitnesses.
- **File-based URI discovery on the shared /pfs filesystem:** each worker writes
  its Pyro5 address (URI) to a file on /pfs; the coordinator reads them and
  dispatches — **no name server needed**, and it **survives partial node
  failures** (more robust on a cluster than a central registry).
- **Checkpoint / resume every generation:** `de_state.json` (written atomically
  via temp-file rename) + append-only `de_history.jsonl`. An interrupted 30-minute
  dev-node slot resumes seamlessly in the next slot.

**Pyro5** = *Python Remote Objects* — a library for calling methods on objects in
other Python processes/nodes over the network (RPC).

**Likely questions**

- *Why persistent workers, not one Slurm job per evaluation?* Job startup +
  queueing overhead would dwarf the evaluation; persistent workers amortise it.
- *Why file-based discovery over a Pyro name server?* No single point of failure,
  no extra service to keep alive; /pfs is already shared and reliable.
- *What if a node dies mid-run?* Its URI file goes stale; the coordinator skips it
  and the generation checkpoint lets the run resume — no lost progress.
- *Is this the island model?* No — this is master/worker parallelism of *one* DE
  population. The island model (next slide) is the future, coarser-grained scheme.

## 5.3 Parallelization — island model

**Shown (left):** a ring of six islands, each with individuals. **(right):** the
per-island generation loop.

**In depth.** The long-term, **massive-parallelization** strategy — named in the
SPP project title. Instead of one global population:

- Run **many subpopulations ("islands")**, each evolving **independently and in
  parallel** on its own worker (each island a full DE with its own seed).
- **Inside each island**, every generation runs the normal EA operators —
  **selection → crossover → mutation** — producing the next generation.
- **Every few generations, islands exchange their best individuals — migration —**
  along a **ring topology** (island k → k+1).
- Effect: **keeps global diversity high**, **avoids premature convergence** to a
  single basin, and **scales near-linearly** to many nodes because islands
  communicate only rarely (cheap, infrequent migration).

Crucially, islands provide **diversity, not just raw speed-up** — different
islands explore different regions of the design space. The current DE + Pyro5
setup is the **prototype**; the island model is the **target** for scaling to many
cluster nodes.

**Likely questions**

- *Island model vs simply a bigger population?* One big population tends to
  converge to a single basin; independent islands with occasional migration
  maintain diversity and explore more of the space at the same total cost.
- *Why ring migration (not all-to-all)?* Ring keeps communication local and cheap;
  good individuals still diffuse around the ring over several migrations.
- *Migration frequency trade-off?* Too frequent → islands homogenise (lose
  diversity); too rare → good genes spread too slowly. A few generations between
  migrations is the usual sweet spot.

## 5.4 AI-Agent integration (MCP server)

**Shown:** an in-progress **MCP server** exposing the framework to AI assistants.

**In depth.** Alongside the science, the framework was refactored into a clean,
**pip-installable Python package** with a full CLI and interchangeable optimizer
backends, independent of dtOO. On top sits an **MCP server** *(in progress)*:

- **`fastmcp`-based server** exposing **6 tools + 4 resources**.
- Tools: `submit_job`, `get_status`, `list_results`, `get_best_design`,
  `cancel_job`, `get_history`.
- **MCP = Model Context Protocol** (Anthropic's open standard) — it lets an AI
  assistant (e.g. Claude) **submit optimization jobs, monitor them, and query
  results via natural language**, with no shell knowledge.
- **Goal:** lower the barrier for non-expert users of the framework.

**Likely questions**

- *What is MCP?* A standard protocol that connects AI assistants to external tools/
  data; the assistant calls your "tools" and reads your "resources" in a
  structured way.
- *Tools vs resources?* Tools are actions (submit/cancel a job); resources are
  readable data (status, history, best design).
- *Is this core to the science?* No — it's a usability layer so the optimizer is
  approachable through natural language.

---

# 6 · Status & outlook

## 6.1 Current status & pending results

**Shown (left):** what's built. **(right):** the optimization-run status table.

**Built (operational):** modal solver; beam validation; 3D runner dry modes;
coupled CFD + blade-passing-frequency objective; Differential-Evolution parallel
optimizer; cluster deployment; a resonance-only run verified end-to-end.

**Runs on the Tistos runner:**

| Run | Status | Result |
|---|---|---|
| **Modal-only** | ✓ 3 dev-node runs | penalty **7.36 → 4.90** |
| **CFD-only** | pending in queue | — |
| **Combined** | pending in queue | — |

- **Modal-only** ran on the dev node in three 30-minute slots with checkpoint-
  resume across job boundaries: **pop 32, DE/rand/1/bin, 8 nodes × 4 workers**,
  ~**12 generations**. Penalty dropped **7.36 → 4.90** — the optimizer actively
  shifts eigenfrequencies out of the forbidden bands.
- **CFD-only** and **combined** are **pending**: they need **24 h walltime** and
  are waiting on queue priority. The full three-way comparison — isolating how the
  eigenfrequency objective reshapes the design — follows after the talk.

**Likely questions**

- *Why only modal-only so far?* It fits in short dev-node slots; CFD-heavy runs
  need long walltime that's still queued.
- *Is 7.36 → 4.90 good?* It's a clear, monotone improvement in ~12 generations,
  confirming the objective and optimizer work end-to-end; the absolute value is
  case-specific.
- *Why 30-minute slots?* Dev-node policy; checkpoint-resume stitches them into a
  continuous run.

## 6.2 Future work & acknowledgements

**Shown (left):** the next steps. **(right):** thanks.

**Future work**

1. **CFD + modal in water** — wet added-mass lowers eigenfrequencies; a **15 %
   placeholder shift** is stubbed now, with **real Laplace coupling**
   (`rayleigh_ratios`, i.e. an added-mass matrix from potential/Helmholtz
   acoustics) to follow.
2. **+ kinematics** — **diametral-mode matching** against blade-passing harmonics
   in the wet regime: verify the *right mode shapes* (nodal diameters n = 1,2,3…)
   are pushed out of the *right bands*.
3. **Long-term** — unsteady CFD; full **Helmholtz-acoustic ↔ elasticity FSI**;
   **forced-response amplitude** and **fatigue** analysis.
4. **Engineering follow-ups** — verify the hub-clamp boundary condition in
   ParaView; rescale the mesh to metres (coords ~2.5×); confirm CFD
   post-processing column indices; async steady-state DE.

**Acknowledgements:** DFG Priority Programme **SPP 2335**; **IHS, University of
Stuttgart**; **Université Laval**; and **HEKI**, the hydropower network in Canada —
especially the Laval group for the validation data and the exchange.

**Likely questions**

- *Why a 15 % placeholder for water?* A quick, physically-motivated first estimate
  of the added-mass down-shift, so the pipeline is complete while the real Laplace
  coupling is implemented.
- *What is diametral-mode matching?* Ensuring the specific mode *shapes* excited by
  blade passing (given nodal-diameter numbers) are the ones moved out of the
  bands — not just any modes.
- *Why rescale to metres?* The current mesh coordinates are ~2.5× off the physical
  scale; frequencies scale with size, so units must be correct.

---

## Fast-recall cheat sheet

- **f_bp = Z·n/60** — blade-passing freq; kinematic, no CFD. Tistos: 18·90/60 = 27 Hz (+ harmonics).
- **Beam PDE** EI·wₓₓₓₓ + ρA·w_tt = 0 → **cos α cosh α = −1**; α₁,₂,₃ = 1.875, 4.694, 7.855; **f_n ∝ α_n²**.
- **FEM** Kφ = ω²Mφ (K stiffness, M mass); **SLEPc** shift-invert + LU/MUMPS; **P2** needed (P1 over-stiffens bending 14–20 %).
- **Validation:** beam Mode1 8.4 Hz; bronze disc all modes < 5 % (vs exp), < 1.5 % (vs ANSYS); 325k tet10 ≈ 1.96 M DOFs.
- **Objective** f_total = f_CFD + f_res; **triangular penalty** inside forbidden bands, **reward** toward gap centres; CFD terms tanh-damped (η, V_cav, head).
- **DE** v = x_r1 + F(x_r2 − x_r3), F=0.8, CR=0.9, greedy; NP=20–32, ≤30 gen, ~600 evals, DE/rand/1/bin.
- **Parallel:** Pyro5 coordinator + persistent workers, file-based URIs on /pfs, checkpoint per generation. **Island model** = future massive-parallel (ring migration for diversity).
- **Result so far:** modal-only 7.36 → 4.90 in ~12 gen; CFD/combined queued.
