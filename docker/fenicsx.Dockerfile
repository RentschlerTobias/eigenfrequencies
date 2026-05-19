FROM dolfinx/dolfinx:stable

RUN pip install gmsh pygmo matplotlib pyvista scipy

RUN apt-get update && apt-get install -y neovim && rm -rf /var/lib/apt/lists/*