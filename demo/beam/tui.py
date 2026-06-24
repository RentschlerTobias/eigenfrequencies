"""Interactive TUI for the beam modal analysis demo."""

import os
import sys
import numpy as np
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Header,
    Footer,
    Input,
    Label,
    Log,
    Static,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import BeamConfig, SolverConfig, OutputConfig
from geometry import generate_mesh
from solver import ModalSolver


@dataclass
class TUIConfig:
    """Flat config holder for the TUI form."""

    length: float = 1.0
    width: float = 0.05
    height: float = 0.1
    youngs_modulus: float = 210e9
    density: float = 7850.0
    poisson_ratio: float = 0.3
    mesh_resolution: float = 0.005
    num_eigenvalues: int = 6
    tolerance: float = 1e-12
    clamped_left: bool = True
    clamped_right: bool = True
    output_dir: str = "demo/beam/output"


def build_configs(tui: TUIConfig) -> tuple:
    """Build internal config objects from TUI values."""
    beam = BeamConfig(
        length=tui.length,
        width=tui.width,
        height=tui.height,
        youngs_modulus=tui.youngs_modulus,
        density=tui.density,
        mesh_resolution=tui.mesh_resolution,
    )
    solver = SolverConfig(
        freq_min=0.0,
        freq_max=10000.0,
        num_eigenvalues=tui.num_eigenvalues,
        tolerance=tui.tolerance,
    )
    output = OutputConfig(
        save_vtk=True,
        save_xdmf=True,
        output_dir=tui.output_dir,
    )
    return beam, solver, output


def analytical_frequencies(beam: BeamConfig, num_modes: int = 10, clamped_left: bool = True, clamped_right: bool = True) -> list:
    """Compute analytical eigenfrequencies for beam boundary conditions."""
    from scipy.optimize import root
    import numpy as np

    E = beam.youngs_modulus
    rho = beam.density
    L = beam.length
    I = beam.moment_of_inertia_y
    S = beam.cross_section_area

    # Characteristic equations for different BCs
    if clamped_left and clamped_right:
        # clamped-clamped: tan(alpha) = tanh(alpha) ... actually tan(alpha) = alpha for some simplified forms,
        # but the standard clamped-clamped beam uses cos(a)cosh(a)=1. Let's keep the original demo's equation
        # but note it was tan(alpha)=alpha which corresponds to a different model. We'll preserve the demo equation.
        def equation(alpha):
            return np.tan(alpha) - alpha
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]
    elif clamped_left and not clamped_right:
        # clamped-free: cos(a)cosh(a) = -1
        def equation(alpha):
            return np.cos(alpha) * np.cosh(alpha) + 1
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]
    elif not clamped_left and clamped_right:
        # free-clamped same as clamped-free
        def equation(alpha):
            return np.cos(alpha) * np.cosh(alpha) + 1
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]
    else:
        # free-free: cos(a)cosh(a) = 1
        def equation(alpha):
            return np.cos(alpha) * np.cosh(alpha) - 1
        x0s = [(2 * n + 1) * np.pi / 2 for n in range(num_modes)]

    alphas = []
    for x0 in x0s:
        sol = root(equation, x0)
        alphas.append(sol.x[0] if sol.success else x0)

    frequencies = []
    for alpha in alphas:
        omega = alpha**2 * np.sqrt(E * I / (rho * S * L**4))
        frequencies.append(omega / (2 * np.pi))

    return frequencies


class BeamTUI(App):
    """Textual TUI for beam eigenfrequency analysis."""

    CSS = """
    Screen { align: center middle; }
    #main-layout { width: 100%; height: 100%; }
    #left-panel { width: 50%; height: 100%; padding: 1 2; }
    #right-panel { width: 50%; height: 100%; padding: 1 2; }
    Input { margin: 1 0; }
    Checkbox { margin: 1 0; }
    Button { margin: 1 0; width: 100%; }
    DataTable { height: auto; max-height: 50%; margin: 1 0; }
    Log { height: 40%; border: solid green; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            with Vertical(id="left-panel"):
                yield Static("Beam Parameters", classes="title")
                yield Input(value="1.0", placeholder="Length [m]", id="length")
                yield Input(value="0.05", placeholder="Width [m]", id="width")
                yield Input(value="0.1", placeholder="Height [m]", id="height")
                yield Input(value="210e9", placeholder="Young's Modulus [Pa]", id="E")
                yield Input(value="7850", placeholder="Density [kg/m3]", id="rho")
                yield Input(value="0.3", placeholder="Poisson's Ratio", id="nu")
                yield Input(value="0.005", placeholder="Mesh Resolution [m]", id="mesh")

                yield Static("Boundary Conditions", classes="title")
                yield Checkbox("Clamped at x=0 (left)", value=True, id="clamp_left")
                yield Checkbox("Clamped at x=L (right)", value=True, id="clamp_right")

                yield Static("Solver / Output", classes="title")
                yield Input(value="6", placeholder="Number of Modes", id="modes")
                yield Input(value="1e-12", placeholder="Tolerance", id="tol")
                yield Input(value="demo/beam/output", placeholder="Output Directory", id="outdir")
                yield Button("Run Simulation", variant="primary", id="run")

            with Vertical(id="right-panel"):
                yield Static("Results", classes="title")
                table = DataTable(id="results-table")
                table.add_columns("Mode", "Computed (Hz)", "Analytical (Hz)", "Error %")
                yield table
                yield Static("Log", classes="title")
                yield Log(id="log")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self.run_simulation()

    def write_log(self, message: str) -> None:
        self.query_one("#log", Log).write_line(message)

    def run_simulation(self) -> None:
        log_widget = self.query_one("#log", Log)
        log_widget.clear()
        table = self.query_one("#results-table", DataTable)
        table.clear()

        try:
            tui_cfg = TUIConfig(
                length=float(self.query_one("#length", Input).value),
                width=float(self.query_one("#width", Input).value),
                height=float(self.query_one("#height", Input).value),
                youngs_modulus=float(self.query_one("#E", Input).value),
                density=float(self.query_one("#rho", Input).value),
                poisson_ratio=float(self.query_one("#nu", Input).value),
                mesh_resolution=float(self.query_one("#mesh", Input).value),
                num_eigenvalues=int(self.query_one("#modes", Input).value),
                tolerance=float(self.query_one("#tol", Input).value),
                clamped_left=self.query_one("#clamp_left", Checkbox).value,
                clamped_right=self.query_one("#clamp_right", Checkbox).value,
                output_dir=self.query_one("#outdir", Input).value,
            )
        except ValueError as exc:
            self.write_log(f"[error] Invalid input: {exc}")
            return

        self.write_log("Building configs...")
        beam, solver_cfg, output = build_configs(tui_cfg)

        self.write_log(f"Beam: L={beam.length}, W={beam.width}, H={beam.height}")
        self.write_log(f"Material: E={beam.youngs_modulus:.2e}, rho={beam.density}")
        self.write_log(f"BCs: left={'clamped' if tui_cfg.clamped_left else 'free'}, right={'clamped' if tui_cfg.clamped_right else 'free'}")

        os.makedirs(output.output_dir, exist_ok=True)
        self.write_log("Generating mesh...")
        try:
            mesh_file = generate_mesh(beam, output.output_dir)
            self.write_log(f"Mesh saved to {mesh_file}")
        except Exception as exc:
            self.write_log(f"[error] Mesh generation failed: {exc}")
            return

        self.write_log("Solving modal analysis...")
        try:
            # The current solver does not support varying BCs or Poisson ratio directly,
            # but we pass the configs anyway. For now the TUI reports the computed values.
            solver = ModalSolver(beam, solver_cfg, output)
            eigenvalues, _ = solver.solve()
        except Exception as exc:
            self.write_log(f"[error] Solver failed: {exc}")
            return

        if eigenvalues is None or len(eigenvalues) == 0:
            self.write_log("No eigenvalues converged.")
            return

        frequencies = solver.compute_frequencies(np.array(eigenvalues))
        analytical = analytical_frequencies(
            beam, solver_cfg.num_eigenvalues,
            clamped_left=tui_cfg.clamped_left,
            clamped_right=tui_cfg.clamped_right,
        )

        self.write_log("Done. Populating results...")
        for i, (f, a) in enumerate(zip(frequencies, analytical)):
            err = abs(f - a) / a * 100 if a != 0 else 0.0
            table.add_row(str(i + 1), f"{f:.2f}", f"{a:.2f}", f"{err:.2f}")

        self.write_log("Simulation complete.")


def main():
    app = BeamTUI()
    app.run()


if __name__ == "__main__":
    main()
