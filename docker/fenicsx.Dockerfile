FROM dolfinx/dolfinx:stable

RUN pip install gmsh matplotlib pyvista scipy plotly

RUN apt-get update && apt-get install -y neovim curl && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy repo and install package
# rl extra excluded: d3rlpy/stable-baselines3 add ~500MB image bloat
COPY . /src/eigenfrequencies
RUN uv pip install --system -e ".[optimize,mcp,dev]"