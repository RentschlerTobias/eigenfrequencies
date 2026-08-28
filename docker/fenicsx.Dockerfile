FROM dolfinx/dolfinx:stable

RUN pip install gmsh matplotlib pyvista scipy plotly

RUN apt-get update && apt-get install -y neovim curl && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy repo and install package
# rl extra excluded: d3rlpy/stable-baselines3 add ~500MB image bloat
# .dockerignore keeps the meshes and the history out of the context.
COPY . /src/eigenfrequencies
# WORKDIR, or `-e "."` resolves to /root and uv reports "does not appear to be
# a Python project".
WORKDIR /src/eigenfrequencies
# --break-system-packages: the base image marks its interpreter EXTERNALLY-MANAGED
# (PEP 668), and uv refuses --system without it. Installing into the system
# interpreter is the point here — the container has no other one, and the modal
# stage is invoked as `python3 <repo>/src/.../physics.py`.
RUN uv pip install --system --break-system-packages -e ".[optimize,mcp,dev]"