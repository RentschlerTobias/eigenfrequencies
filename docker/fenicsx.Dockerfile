FROM dolfinx/dolfinx:stable

RUN conda install -c conda-forge \
    pygmo \
    matplotlib \
    pyvista \
    gmsh \
    && conda clean -afy