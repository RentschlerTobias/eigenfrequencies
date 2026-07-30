project = "eigenfrequencies"
copyright = "2025, IHS University of Stuttgart"
author = "IHS University of Stuttgart"
release = "0.1.0"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "myst_parser",
]

# Mock all heavy scientific deps — not available in CI
autodoc_mock_imports = [
    "dolfinx",
    "ufl",
    "petsc4py",
    "slepc4py",
    "mpi4py",
    "gmsh",
    "pyvista",
    "numpy",
    "scipy",
    "Pyro5",
    "fastmcp",
    "optuna",
    "pymoo",
    "cma",
    "gymnasium",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_title = "eigenfrequencies"
html_static_path = ["_static"]

html_theme_options = {
    "sidebar_hide_name": False,
}

source_suffix = [".rst", ".md"]
master_doc = "index"