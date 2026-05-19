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

Euler-Bernoulli Beam Theory
---------------------------

For a clamped-clamped beam, the analytical eigenfrequencies are:

.. math::

    f_n = \frac{\alpha_n^2}{2\pi} \sqrt{\frac{EI}{\rho S L^4}}

where :math:`\alpha_n` are the solutions of:

.. math::

    \tan(\alpha) = \alpha