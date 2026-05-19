Quickstart
==========

Installation
------------

Using Docker (recommended):

.. code-block:: bash

    ./scripts/build_container.sh
    ./scripts/run_container.sh

Building the Beam Demo
----------------------

Inside the container:

.. code-block:: bash

    cd demo/beam
    python main.py

This will compute the eigenfrequencies of a simple clamped beam and validate against analytical solutions.