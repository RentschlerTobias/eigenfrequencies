"""Cantilever beam validation test.

Compares 3D FEM eigenfrequencies with analytical Euler-Bernoulli solutions
for a cantilever beam (one end clamped at x=0, other end free).
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from solver import ModalSolver
from geometry import generate_mesh
from config import BeamConfig, SolverConfig, OutputConfig
from euler_analytical import analytical_frequencies_cantilever


def classify_mode(eigenvector, mesh_coords):
    """Classify vibration mode based on displacement pattern.
    
    Args:
        eigenvector: Eigenvector array (num_dofs)
        mesh_coords: Node coordinates (num_nodes, 3)
        
    Returns:
        dict with mode classification
    """
    num_nodes = len(mesh_coords)
    
    # For Lagrange-2 elements, the eigenvector has more DOFs than nodes
    # We need to evaluate the function at the nodes
    # The DOFs are organized in blocks of 3 (x, y, z components)
    # For nodes, we can just take the first DOF for each component at each node
    # This is an approximation but works for classification
    
    # Extract the displacement values for each node
    # The eigenvector contains values for all DOFs, but we need node values
    # For simplicity, we'll take the first 3*num_nodes values (node values)
    # and ignore the edge/face DOFs for classification
    
    if len(eigenvector) >= num_nodes * 3:
        # Take the first 3*num_nodes values (node values for P1 or P2)
        u = eigenvector[:num_nodes * 3].reshape((num_nodes, 3))
    else:
        # If eigenvector is smaller than expected, just reshape what we have
        u = eigenvector.reshape((-1, 3))
    
    # Extract displacement components
    ux = u[:, 0]
    uy = u[:, 1]
    uz = u[:, 2]
    
    # Max absolute displacements
    max_ux = np.max(np.abs(ux))
    max_uy = np.max(np.abs(uy))
    max_uz = np.max(np.abs(uz))
    
    # Determine dominant direction
    displacements = {"x": max_ux, "y": max_uy, "z": max_uz}
    dominant = max(displacements, key=displacements.get)
    
    # Check for torsion (rotation about x-axis)
    # Torsion: top and bottom nodes move in opposite z-directions
    y_coords = mesh_coords[:, 1]
    z_coords = mesh_coords[:, 2]
    
    top_mask = z_coords > 0
    bottom_mask = z_coords < 0
    
    if np.any(top_mask) and np.any(bottom_mask):
        uy_top = uy[top_mask]
        uy_bottom = uy[bottom_mask]
        uz_top = uz[top_mask]
        uz_bottom = uz[bottom_mask]
        
        # Torsion indicator: opposite z-displacement at top vs bottom
        torsion_indicator = np.abs(np.mean(uz_top) - np.mean(uz_bottom))
    else:
        torsion_indicator = 0
    
    # Classify mode
    if torsion_indicator > 0.5 * max_uz:
        mode_type = "torsion"
    elif dominant == "x":
        mode_type = "axial"
    elif dominant == "y":
        mode_type = "bending_y"
    elif dominant == "z":
        mode_type = "bending_z"
    else:
        mode_type = "unknown"
    
    return {
        "type": mode_type,
        "dominant": dominant,
        "max_ux": max_ux,
        "max_uy": max_uy,
        "max_uz": max_uz,
        "torsion_indicator": torsion_indicator,
    }


def plot_mode_shape(eigenvector, mesh_coords, mode_num, output_dir):
    """Legacy 2D plot (deprecated). Use plotly_dashboard instead."""
    pass


def plotly_dashboard(eigenvectors, mesh_coords, mode_info, analytical_freqs, output_dir):
    """Create interactive 3D Plotly dashboard.

    Simple, no animation, no play/pause. Slider switches between modes.
    Bar chart shows all modes, highlights active one.
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        print("plotly not available, skipping dashboard")
        return

    num_nodes = len(mesh_coords)

    # Human-readable mode descriptions
    type_desc = {
        "bending_z": "Bending up/down (z-direction)",
        "bending_y": "Bending left/right (y-direction)",
        "torsion": "Torsion (twisting around beam axis)",
        "axial": "Axial (stretching along beam)",
        "unknown": "Unknown",
    }

    color_map = {
        "torsion": "#2ecc71",
        "bending_y": "#3498db",
        "bending_z": "#2980b9",
        "axial": "#e67e22",
        "unknown": "#95a5a6",
    }

    def extract_disp(ev):
        if len(ev) >= num_nodes * 3:
            u = ev[:num_nodes * 3].reshape((num_nodes, 3))
        else:
            u = ev.reshape((-1, 3))
        return u

    # Deduplicate modes
    seen = set()
    unique_modes = []
    for info in mode_info:
        key = round(info["fem_freq"], 4)
        if key not in seen:
            seen.add(key)
            unique_modes.append(info)

    if not unique_modes:
        print("No unique modes found.")
        return

    # Build figure
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        specs=[[{"type": "scatter3d"}], [{"type": "bar"}]],
        subplot_titles=(
            "Mode Shape (3D) — gray = original, colored = deformed",
            "All Modes — FEM vs Analytical (only for bending_z)",
        ),
    )

    # First mode data
    first_mode = unique_modes[0]
    u0 = extract_disp(eigenvectors[first_mode["mode_num"] - 1])
    disp_mag = np.linalg.norm(u0, axis=1)
    max_disp = disp_mag.max() if disp_mag.max() > 0 else 1.0
    scale = 0.2 * np.max(mesh_coords[:, 0]) / max_disp
    deformed0 = mesh_coords + scale * u0

    # Trace 0: Undeformed (gray)
    fig.add_trace(
        go.Scatter3d(
            x=mesh_coords[:, 0], y=mesh_coords[:, 1], z=mesh_coords[:, 2],
            mode="markers", marker=dict(size=2, color="#bdc3c7", opacity=0.4),
            hoverinfo="skip",
        ),
        row=1, col=1,
    )

    # Trace 1: Deformed (colored by displacement)
    fig.add_trace(
        go.Scatter3d(
            x=deformed0[:, 0], y=deformed0[:, 1], z=deformed0[:, 2],
            mode="markers", marker=dict(
                size=4, color=disp_mag, colorscale="Viridis", cmin=0, cmax=max_disp,
                colorbar=dict(title="Disp. [m]", x=0.95),
            ),
            text=[f"disp: {d:.2e}" for d in disp_mag],
            hovertemplate="x: %{x:.3f}<br>y: %{y:.3f}<br>z: %{z:.3f}<br>%{text}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Bar chart: all modes, FEM always, Analytical only for bending_z
    bending_z = [m for m in unique_modes if m["type"] == "bending_z"]
    mode_labels = [f"M{m['mode_num']}" for m in unique_modes]

    # FEM values (all modes)
    fem_vals = [m["fem_freq"] for m in unique_modes]
    fem_colors = [color_map.get(m["type"], "#95a5a6") for m in unique_modes]

    # Analytical values (only for bending_z, None for others)
    ana_vals = []
    for m in unique_modes:
        if m["type"] == "bending_z":
            bz_idx = bending_z.index(m)
            if bz_idx < len(analytical_freqs):
                ana_vals.append(analytical_freqs[bz_idx])
            else:
                ana_vals.append(None)
        else:
            ana_vals.append(None)

    # Calculate max_freq for y-axis
    all_freqs = [m["fem_freq"] for m in unique_modes] + [a for a in ana_vals if a is not None]
    max_freq = max(all_freqs) * 1.2 if all_freqs else 1.0

    # Hover text
    fem_hover = []
    ana_hover = []
    for i, m in enumerate(unique_modes):
        desc = type_desc.get(m["type"], "Unknown")
        if ana_vals[i] is not None:
            err = abs(m["fem_freq"] - ana_vals[i]) / ana_vals[i] * 100
            fem_txt = f"<b>Mode {m['mode_num']}</b><br>{desc}<br>FEM: {m['fem_freq']:.2f} Hz<br>Analytical: {ana_vals[i]:.2f} Hz<br>Error: {err:.1f}%"
            ana_txt = f"<b>Mode {m['mode_num']} Analytical</b><br>{ana_vals[i]:.2f} Hz"
        else:
            fem_txt = f"<b>Mode {m['mode_num']}</b><br>{desc}<br>FEM: {m['fem_freq']:.2f} Hz<br>Analytical: —"
            ana_txt = ""
        fem_hover.append(fem_txt)
        ana_hover.append(ana_txt)

    # Trace 2: FEM bars
    fig.add_trace(
        go.Bar(
            x=mode_labels, y=fem_vals,
            name="FEM",
            marker=dict(color=fem_colors, line=dict(color="#000", width=0)),
            text=[f"{v:.1f}" for v in fem_vals],
            textposition="outside",
            hovertext=fem_hover,
            hoverinfo="text",
        ),
        row=2, col=1,
    )

    # Trace 3: Analytical bars (None for non-bending_z)
    fig.add_trace(
        go.Bar(
            x=mode_labels, y=ana_vals,
            name="Analytical",
            marker=dict(color="#e74c3c", line=dict(color="#000", width=0)),
            text=[f"{v:.1f}" if v is not None else "" for v in ana_vals],
            textposition="outside",
            hovertext=ana_hover,
            hoverinfo="text",
        ),
        row=2, col=1,
    )

    # Trace 4: Active mode indicator line
    active_label = f"M{first_mode['mode_num']}"
    fig.add_trace(
        go.Scatter(
            x=[active_label, active_label],
            y=[0, max_freq],
            mode="lines",
            line=dict(color="red", width=2, dash="dash"),
            hoverinfo="skip",
        ),
        row=2, col=1,
    )

    # --- Build frames (one per mode) ---
    frames = []
    for info in unique_modes:
        u = extract_disp(eigenvectors[info["mode_num"] - 1])
        disp = np.linalg.norm(u, axis=1)
        max_d = disp.max() if disp.max() > 0 else 1.0
        sc = 0.2 * np.max(mesh_coords[:, 0]) / max_d
        deformed = mesh_coords + sc * u
        mode_label = f"M{info['mode_num']}"

        frame = go.Frame(
            data=[
                # Trace 1: deformed
                go.Scatter3d(
                    x=deformed[:, 0], y=deformed[:, 1], z=deformed[:, 2],
                    mode="markers", marker=dict(
                        size=4, color=disp, colorscale="Viridis", cmin=0, cmax=max_d,
                        colorbar=dict(title="Disp. [m]", x=0.95),
                    ),
                    text=[f"disp: {d:.2e}" for d in disp],
                    hovertemplate="x: %{x:.3f}<br>y: %{y:.3f}<br>z: %{z:.3f}<br>%{text}<extra></extra>",
                ),
                # Trace 4: active line
                go.Scatter(
                    x=[mode_label, mode_label],
                    y=[0, max_freq],
                    mode="lines",
                    line=dict(color="red", width=2, dash="dash"),
                    hoverinfo="skip",
                ),
            ],
            traces=[1, 4],
            name=info["mode_num"],
            layout=dict(
                title=dict(
                    text=f"Mode {info['mode_num']} — {type_desc.get(info['type'], 'Unknown')} — {info['fem_freq']:.2f} Hz",
                    font=dict(size=16),
                ),
                annotations=[
                    dict(
                        x=0.02, y=0.98,
                        xref="paper", yref="paper",
                        text=f"<b>{type_desc.get(info['type'], 'Unknown')}</b><br>Freq: {info['fem_freq']:.2f} Hz",
                        showarrow=False,
                        font=dict(size=12),
                        bgcolor="rgba(255,255,255,0.8)",
                        borderpad=4,
                    )
                ],
            ),
        )
        frames.append(frame)

    fig.frames = frames

    # --- Slider ---
    steps = []
    for info in unique_modes:
        step = dict(
            method="animate",
            args=[
                [info["mode_num"]],
                dict(mode="immediate", frame=dict(duration=0, redraw=True),
                     transition=dict(duration=0)),
            ],
            label=str(info["mode_num"]),
        )
        steps.append(step)

    sliders = [dict(
        active=0,
        steps=steps,
        x=0.1, y=0,
        len=0.8,
        xanchor="left", yanchor="top",
        currentvalue=dict(
            prefix="Mode: ",
            font=dict(size=14),
            visible=True,
        ),
        transition=dict(duration=0),
    )]

    fig.update_layout(
        title=dict(
            text=f"Mode {first_mode['mode_num']} — {type_desc.get(first_mode['type'], 'Unknown')} — {first_mode['fem_freq']:.2f} Hz",
            font=dict(size=16),
        ),
        scene=dict(
            xaxis_title="x [m]", yaxis_title="y [m]", zaxis_title="z [m]",
            aspectmode="data",
            camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        ),
        sliders=sliders,
        height=850,
        showlegend=False,
        barmode="group",
        margin=dict(l=0, r=0, b=80, t=80),
    )

    fig.update_yaxes(title_text="Frequency [Hz]", row=2, col=1)
    fig.update_xaxes(title_text="Mode Number", row=2, col=1)

    html_path = os.path.join(output_dir, "modes_dashboard.html")
    fig.write_html(html_path, include_plotlyjs="cdn")
    print(f"  Interactive dashboard saved to: {html_path}")


def main():
    """Run cantilever beam validation test."""
    beam_config = BeamConfig(
        length=1.0,
        width=0.1,
        height=0.01,
        youngs_modulus=210e9,
        density=7850.0,
        mesh_resolution=0.1,
    )
    
    solver_config = SolverConfig(
        freq_min=0.0,
        freq_max=1000.0,
        num_eigenvalues=10,
        tolerance=1e-6,
    )
    
    output_config = OutputConfig(
        save_vtk=True,
        save_xdmf=True,
    )
    
    print("=" * 70)
    print("Cantilever Beam Validation Test")
    print("=" * 70)
    print(f"Beam dimensions: {beam_config.length} x {beam_config.width} x {beam_config.height} m")
    print(f"Material: E={beam_config.youngs_modulus:.2e} Pa, rho={beam_config.density} kg/m³")
    print(f"Mesh resolution: {beam_config.mesh_resolution} m")
    print()
    
    # Analytical solution
    print("Analytical Solution (Cantilever - Euler-Bernoulli):")
    print("-" * 50)
    analytical_freqs = analytical_frequencies_cantilever(beam_config, solver_config.num_eigenvalues)
    for i, freq in enumerate(analytical_freqs):
        print(f"  Mode {i+1}: {freq:.4f} Hz")
    print()
    
    # Generate mesh
    print("Generating mesh...")
    os.makedirs(output_config.output_dir, exist_ok=True)
    mesh_file = generate_mesh(beam_config, output_config.output_dir)
    print(f"Mesh saved to: {mesh_file}")
    print()
    
    # Solve 3D FEM
    print("Solving 3D FEM modal analysis...")
    solver = ModalSolver(beam_config, solver_config, output_config, boundary_type="cantilever")
    eigenvalues, eigenvectors = solver.solve()
    
    if eigenvalues is None or len(eigenvalues) == 0:
        print("No eigenvalues converged!")
        return
    
    frequencies = solver.compute_frequencies(eigenvalues)
    
    # Get mesh coordinates for mode analysis
    domain = solver.create_mesh()
    mesh_coords = domain.geometry.x
    
    print()
    print("3D FEM Results:")
    print("-" * 50)
    
    # Analyze and classify modes
    mode_info = []
    for i, (freq, ev) in enumerate(zip(frequencies, eigenvectors)):
        info = classify_mode(ev, mesh_coords)
        info["fem_freq"] = freq
        info["mode_num"] = i + 1
        mode_info.append(info)
        
        print(f"  Mode {i+1}: {freq:.4f} Hz  ({info['type']}, dominant: {info['dominant']})")
    
    print()
    
    # Extract bending modes in z-direction (primary bending direction for analytical comparison)
    bending_z_modes = [m for m in mode_info if m["type"] == "bending_z"]
    
    print("=" * 70)
    print("Comparison: Bending Modes (z-direction)")
    print("=" * 70)
    print(f"{'Mode':<6} {'Analytical':<15} {'3D FEM':<15} {'Error %':<12} {'Status'}")
    print("-" * 70)
    
    num_compare = min(len(analytical_freqs), len(bending_z_modes))
    for i in range(num_compare):
        analytical_freq = analytical_freqs[i]
        fem_mode = bending_z_modes[i]
        fem_freq = fem_mode["fem_freq"]
        error_percent = abs(fem_freq - analytical_freq) / analytical_freq * 100
        
        status = "✓ PASS" if error_percent < 5.0 else "✗ FAIL"
        
        print(f"{i+1:<6} {analytical_freq:<15.4f} {fem_freq:<15.4f} {error_percent:<12.2f} {status}")
    
    print()
    
    # Also show bending modes in y-direction
    bending_y_modes = [m for m in mode_info if m["type"] == "bending_y"]
    
    print("=" * 70)
    print("Bending Modes (y-direction) - Lower stiffness due to smaller I_z")
    print("=" * 70)
    print(f"{'Mode':<6} {'3D FEM':<15} {'Type':<20}")
    print("-" * 70)
    
    for i, fem_mode in enumerate(bending_y_modes):
        fem_freq = fem_mode["fem_freq"]
        print(f"{i+1:<6} {fem_freq:<15.4f} {fem_mode['type']:<20}")
    
    print()
    
    # Plot mode shapes
    print("Generating interactive 3D dashboard...")
    plotly_dashboard(eigenvectors, mesh_coords, mode_info, analytical_freqs, output_config.output_dir)
    
    print()
    print("=" * 70)
    print("Done")
    print("=" * 70)


if __name__ == "__main__":
    main()
