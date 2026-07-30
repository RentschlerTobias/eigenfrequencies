Eigenvalue Theory
=================

Introduction
------------

Eigenfrequencies describe the natural vibration modes of a structure. When a structure is excited at one of these frequencies, resonance occurs, which can lead to catastrophic failure.

Mathematical Formulation
-------------------------

For a free vibration analysis, we solve the generalized eigenvalue problem:

.. math::

    [K]\{u\} = \lambda[M]\{u\}

where:
- :math:`K` is the stiffness matrix
- :math:`M` is the mass matrix
- :math:`\lambda` is the eigenvalue
- :math:`u` is the eigenvector (mode shape)

The eigenfrequency is related to the eigenvalue by:

.. math::

    f = \frac{\sqrt{\lambda}}{2\pi}


Physical Meaning of the Stiffness Matrix K
------------------------------------------

The stiffness matrix :math:`K` connects forces with displacements. Each entry :math:`k_{ij}` represents how the force at degree of freedom :math:`i` depends on the displacement at degree of freedom :math:`j`.

**Matrix representation:**

.. code-block:: text

    ┌ F₁ ┐     ┌ k₁₁  k₁₂  k₁₃ ┐   ┌ u₁ ┐
    │ F₂ │  =  │ k₂₁  k₂₂  k₂₃ │ · │ u₂ │
    └ F₃ ┘     └ k₃₁  k₃₂  k₃₃ ┘   └ u₃ ┘

- **Diagonal** :math:`k_{ii}` = self-coupling (node i resists its own displacement)
- **Off-diagonal** :math:`k_{ij}` = coupling between nodes i and j

**Physical intuition:**
- Thicker beam → larger :math:`K` → smaller displacement :math:`u`
- Moment of inertia :math:`I = bh³/12` for rectangular cross-section


Physical Meaning of the Mass Matrix M
-------------------------------------

The mass matrix discretizes the distributed mass of the structure. Each node receives a portion of the element's mass.

**Continuous to discrete:**

.. code-block:: text

    Continuous beam (infinitely many points):
    ════════════════════════════════════════════════→ x
    ρ(x) = uniformly distributed density [kg/m]


    Discretized (3 nodes):

        ●──────────●──────────●
        1          2          3

    Each node receives mass from adjacent elements


**Mass matrix structure:**

.. code-block:: text

                 Node 1   Node 2   Node 3
                ┌──────────────────────────────┐
    Node 1     │  m₁₁    m₁₂      0   │
    Node 2     │  m₂₁    m₂₂     m₂₃   │   ← off-diagonals non-zero
    Node 3     │   0     m₃₂     m₃₃   │     due to shape function overlap
                └──────────────────────────────┘

**Key insight:**
- More nodes → smaller individual entries (mass distributed over more nodes)
- Sum of all entries = total mass of the beam (conserved)


Shape Functions
---------------

Shape functions :math:`N_i(x)` approximate the displacement :math:`u(x)` between nodes. They define how a nodal displacement "spreads" across the element.

**Linear shape function between nodes 1 and 2:**

.. code-block:: text

    N₁(x)                    N₂(x)
     1│╲                     ╱│1
      │  ╲                 ╱  │
      │    ╲             ╱    │
      │      ╲         ╱      │
      │        ╲     ╱        │
      │          ╲ ╱          │
    0●───────────●───────────●→ x
                     L/2

    N₁(x) = 1 - x/(L/2)   → 1 at node 1, 0 at node 2
    N₂(x) = x/(L/2)        → 0 at node 1, 1 at node 2


**Displacement approximation:**

.. code-block:: text

    u(x) = u₁ · N₁(x) + u₂ · N₂(x)

The shape function determines the **influence zone** of each node.


Weak Formulation
----------------

**Strong form (differential equation):**

.. code-block:: text

    d⁴u/dx⁴ = f(x)    ← must hold at EVERY point (infinitely many equations)

**Weak form:** Multiply by test function :math:`v` and integrate over the domain:

.. code-block:: text

    ∫ d⁴u/dx⁴ · v dx = ∫ f · v dx

After integration by parts, the order is reduced - only **first derivatives** needed:

.. code-block:: text

    -∫ d³u/dx³ · dv/dx dx = ∫ f · v dx
          ↑
      "Strain energy" term


**Insert shape function approximation:**

.. code-block:: text

    u(x) ≈ Σ uᵢ · Nᵢ(x)

    du/dx ≈ Σ uᵢ · dNᵢ/dx    ← shape functions are differentiated!


How K and M are Computed
------------------------

From the weak form, the matrices are:

.. code-block:: text

    K = ∫ (dNᵢ/dx) · (dNⱼ/dx) dx    ← stiffness contribution
    M = ∫ ρ · Nᵢ · Nⱼ dx             ← mass contribution

**Important:** K comes from :math:`\frac{dN}{dx}`, not from :math:`N` itself.


Linear vs. Quadratic Shape Functions
------------------------------------

**Linear (1st order):**

.. code-block:: text

    N₁      N₂
     1╲      ╱1
       ╲    ╱
        ╲  ╱
         ╲╱
         ● node

    dN₁/dx = -1/L  (constant over element)
    dN₂/dx = +1/L  (constant over element)


**Quadratic (2nd order):**

.. code-block:: text

    N₁      N₂      N₃
     1╲      ╱╲      ╱1
       ╲    ╱  ╲    ╱
        ╲  ╱    ╲  ╱
         ╲╱      ╲╱
         ●        ● nodes

    dN₁/dx = varies (not constant)
    dN₂/dx = varies


**Effect on K:**
- Higher order → :math:`\frac{dN}{dx}` varies within element
- Integral computed more accurately
- Energy better approximated → more accurate stiffness matrix


Euler-Bernoulli Beam Theory
---------------------------

For a clamped-clamped beam, the analytical eigenfrequencies are:

.. math::

    f_n = \frac{\alpha_n^2}{2\pi} \sqrt{\frac{EI}{\rho S L^4}}

where :math:`\alpha_n` are the solutions of:

.. math::

    \tan(\alpha) = \alpha


Connection Between λ and Eigenfrequency
---------------------------------------

The eigenvalue :math:`λ` relates to the circular frequency :math:`ω`:

.. code-block:: text

    λ = ω²
    f = ω / 2π = √λ / 2π

For the generalized eigenvalue problem :math:`K u = λ M u`:
- :math:`λ` is computed by the solver (SLEPc)
- :math:`f` is the physical frequency in Hz