"""End-to-end MCP tests driving the server through a real stdio session.

Uses fastmcp Client with StdioTransport to test the full protocol flow:
  get_config_schema → build config → submit job → poll → fetch → compare.

Three scenarios:
  1. Full flow: beam solve → compare frequencies to golden (1e-4 rel tol)
  2. Invalid config: typo field → structured error, zero jobs
  3. Transport error: kill server mid-session → client errors, job state consistent
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ── guards ────────────────────────────────────────────────────────────────

_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

_GMSH_AVAILABLE = False
try:
    import gmsh  # noqa: F401
    _GMSH_AVAILABLE = True
except ImportError:
    pass

_FULL_SOLVER_AVAILABLE = _DOLFINX_AVAILABLE and _GMSH_AVAILABLE

# ── paths ──────────────────────────────────────────────────────────────────

_GOLDEN_PATH = _REPO_ROOT / "tests" / "characterization" / "golden" / "beam.json"
_EVIDENCE_DIR = _REPO_ROOT / ".omo" / "evidence" / "eigenfrequencies-final-design"
_LEARNINGS_PATH = _REPO_ROOT / ".omo" / "notepads" / "eigenfrequencies-final-design" / "learnings.md"


# ── server bootstrap script ────────────────────────────────────────────────

_SERVER_SCRIPT = """
import sys
from eigenfrequencies.mcp.server import main
main()
"""


def _make_client() -> Client:
    """Return a Client connected to the MCP server via stdio."""
    return Client(
        StdioTransport(
            command=sys.executable,
            args=["-c", _SERVER_SCRIPT],
        )
    )


# ── mesh generation (matches golden) ───────────────────────────────────────


def _generate_beam_msh(output_dir: str) -> str:
    """Generate a cantilever beam mesh matching the golden reference.

    Dimensions: 1.0 x 0.1 x 0.01 m, lc=0.1, element_degree=2 compatible.
    """
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("Mesh.Algorithm", 6)
    gmsh.model.add("beam")

    L, B, H = 1.0, 0.1, 0.01
    lc = 0.1
    B2 = B / 2
    H2 = H / 2

    occ = gmsh.model.occ
    p1 = occ.addPoint(0, -B2, -H2, lc)
    p2 = occ.addPoint(L, -B2, -H2, lc)
    p3 = occ.addPoint(L, B2, -H2, lc)
    p4 = occ.addPoint(0, B2, -H2, lc)
    p5 = occ.addPoint(0, -B2, H2, lc)
    p6 = occ.addPoint(L, -B2, H2, lc)
    p7 = occ.addPoint(L, B2, H2, lc)
    p8 = occ.addPoint(0, B2, H2, lc)

    e1 = occ.addLine(p1, p2)
    e2 = occ.addLine(p2, p3)
    e3 = occ.addLine(p3, p4)
    e4 = occ.addLine(p4, p1)
    e5 = occ.addLine(p5, p6)
    e6 = occ.addLine(p6, p7)
    e7 = occ.addLine(p7, p8)
    e8 = occ.addLine(p8, p5)
    e9 = occ.addLine(p1, p5)
    e10 = occ.addLine(p2, p6)
    e11 = occ.addLine(p3, p7)
    e12 = occ.addLine(p4, p8)

    bottom_loop = occ.addCurveLoop([e1, e2, e3, e4])
    bottom = occ.addSurfaceFilling(bottom_loop)
    top_loop = occ.addCurveLoop([e5, e6, e7, e8])
    top = occ.addSurfaceFilling(top_loop)
    front_loop = occ.addCurveLoop([e1, e10, e5, e9])
    front = occ.addSurfaceFilling(front_loop)
    back_loop = occ.addCurveLoop([e3, e11, e7, e12])
    back = occ.addSurfaceFilling(back_loop)
    left_loop = occ.addCurveLoop([e4, e12, e8, e9])
    left = occ.addSurfaceFilling(left_loop)
    right_loop = occ.addCurveLoop([e2, e10, e6, e11])
    right = occ.addSurfaceFilling(right_loop)

    surfaces = [bottom, top, front, back, left, right]
    surface_loop = occ.addSurfaceLoop(surfaces)
    volume_tag = occ.addVolume([surface_loop])
    occ.synchronize()

    gmsh.model.addPhysicalGroup(3, [volume_tag])
    gmsh.model.setPhysicalName(3, volume_tag, "Beam")
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)

    msh_path = os.path.join(output_dir, "beam.msh")
    gmsh.write(msh_path)
    gmsh.finalize()
    return msh_path


# ── golden helpers ─────────────────────────────────────────────────────────


def _load_golden() -> dict[str, Any]:
    return json.loads(_GOLDEN_PATH.read_text())


def _freqs_rel_close(computed: list[float], golden: list[float], rtol: float = 1e-4) -> bool:
    """Check all frequencies match within relative tolerance."""
    if len(computed) != len(golden):
        return False
    for i, (c, g) in enumerate(zip(computed, golden)):
        if g == 0.0:
            if abs(c) > rtol:
                return False
        else:
            if abs((c - g) / g) > rtol:
                return False
    return True


def _beam_config(mesh_path: str) -> dict[str, Any]:
    """Minimal beam config matching the golden reference parameters."""
    return {
        "optimization": {"n_rpm": 72.0},
        "cfd": {"n_rpm": 72.0},
        "material": {
            "youngs_modulus": 210e9,
            "density": 7850.0,
            "poisson_ratio": 0.0,
        },
        "bc": {
            "axis": "x",
            "mode": "axial_plane",
            "plane_value": 0.0,
            "plane_tol": 1e-6,
        },
        "mesh": {
            "msh_path": mesh_path,
            "gdim": 3,
        },
        "solver": {
            "num_eigenvalues": 10,
            "tolerance": 1e-6,
            "freq_min": 0.0,
            "freq_max": 1000.0,
            "element_degree": 2,
            "solver_backend": "scipy",
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test: full flow e2e
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(
    not _FULL_SOLVER_AVAILABLE,
    reason="dolfinx + gmsh required for full solver flow (available in fenicsx container)",
)
class TestFullFlowE2E:
    """Schema → build config → solve → poll → fetch → compare."""

    async def _call_tool(self, client: Any, name: str, args: dict[str, Any]) -> Any:
        result = await client.call_tool(name, args)
        return (
            result.structured_content
            if result.structured_content is not None
            else result.data
        )

    def test_full_beam_solve_via_stdio(self):
        """End-to-end: get schema, build config, submit solve, poll, fetch, compare."""
        golden = _load_golden()
        golden_freqs = golden["frequencies"]

        async def _run():
            with tempfile.TemporaryDirectory() as tmpdir:
                mesh_path = _generate_beam_msh(tmpdir)
                config = _beam_config(mesh_path)

                async with _make_client() as client:
                    # 1. Get config schema — verify it's usable
                    schema_result = await self._call_tool(client, "get_config_schema", {})
                    assert "$schema" in schema_result
                    assert schema_result["type"] == "object"

                    # 2. Submit solve
                    solve_result = await self._call_tool(
                        client, "solve_modal", {"config": config}
                    )
                    assert "job_id" in solve_result
                    job_id = solve_result["job_id"]

                    # 3. Poll until done (timeout 120s)
                    deadline = time.time() + 120
                    state = None
                    while time.time() < deadline:
                        status = await self._call_tool(
                            client, "job_status", {"job_id": job_id}
                        )
                        state = status.get("state", "unknown")
                        if state in ("done", "failed"):
                            break
                        await asyncio.sleep(0.5)

                    assert state == "done", (
                        f"Job {job_id} did not finish in time. "
                        f"Last status: {status}"
                    )

                    # 4. Fetch results
                    fetch_result = await self._call_tool(
                        client, "fetch_results", {"job_id": job_id}
                    )
                    assert "frequencies_hz" in fetch_result, (
                        f"No frequencies_hz in fetch result: {fetch_result}"
                    )
                    computed_freqs = fetch_result["frequencies_hz"]

                    # 5. Compare to golden
                    assert _freqs_rel_close(computed_freqs, golden_freqs, rtol=1e-4), (
                        f"Frequency mismatch:\n"
                        f"  computed: {computed_freqs}\n"
                        f"  golden:   {golden_freqs}"
                    )

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# Test: invalid config — LLM-usable error messages
# ═══════════════════════════════════════════════════════════════════════════════


class TestInvalidConfig:
    """Invalid config produces structured error with field name, zero jobs created."""

    async def _call_tool(self, client: Any, name: str, args: dict[str, Any]) -> Any:
        result = await client.call_tool(name, args)
        return (
            result.structured_content
            if result.structured_content is not None
            else result.data
        )

    def test_typo_material_returns_structured_error(self):
        """solve_modal with 'material' typo → structured error, no job_id returned."""

        async def _run():
            bad_config: dict[str, Any] = {"material": "typo"}

            # Count existing jobs before the call
            jobs_root = Path(".eigenfrequencies/jobs")
            before = len(list(jobs_root.rglob("status.json"))) if jobs_root.is_dir() else 0

            async with _make_client() as client:
                result = await self._call_tool(
                    client, "solve_modal", {"config": bad_config}
                )
                assert "error" in result
                assert result["error"] == "config validation failed"
                assert "details" in result
                # Must NOT return a job_id
                assert "job_id" not in result

                details_str = " ".join(result["details"])
                # Must name the offending field
                assert "material" in details_str.lower() or "material" in details_str

                # Verify no new job was created
                after = len(list(jobs_root.rglob("status.json"))) if jobs_root.is_dir() else 0
                assert after == before, (
                    f"Expected {before} jobs, found {after} after invalid config"
                )

        asyncio.run(_run())

    def test_missing_required_field_returns_error(self):
        """Missing 'optimization' and 'cfd' → structured error."""

        async def _run():
            bad_config: dict[str, Any] = {"solver": {"num_eigenvalues": 10}}

            async with _make_client() as client:
                result = await self._call_tool(
                    client, "solve_modal", {"config": bad_config}
                )
                assert "error" in result
                assert result["error"] == "config validation failed"
                assert "details" in result

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# Test: transport error — kill server mid-session
# ═══════════════════════════════════════════════════════════════════════════════


class TestTransportError:
    """Kill server mid-session → client sees transport error, job state consistent."""

    async def _call_tool(self, client: Any, name: str, args: dict[str, Any]) -> Any:
        result = await client.call_tool(name, args)
        return (
            result.structured_content
            if result.structured_content is not None
            else result.data
        )

    def test_kill_server_mid_session(self):
        """Kill server process → next call raises ClosedResourceError, job state consistent."""

        async def _run():
            config: dict[str, Any] = {
                "optimization": {"n_rpm": 72.0},
                "cfd": {"n_rpm": 72.0},
            }

            async with _make_client() as client:
                # 1. Submit a minimal valid job to confirm the server is alive
                result = await self._call_tool(
                    client, "solve_modal", {"config": config}
                )
                assert "error" in result or "job_id" in result

                # 2. Trigger server disconnect via transport stop event
                #    This terminates the stdio subprocess.
                client.transport._stop_event.set()
                await asyncio.sleep(0.5)

                # 3. The next call should raise a transport error
                #    The underlying anyio stream raises ClosedResourceError.
                with pytest.raises(Exception) as exc_info:
                    await self._call_tool(client, "get_config_schema", {})
                error_name = type(exc_info.value).__name__
                assert error_name in (
                    "ClosedResourceError",
                    "BrokenPipeError",
                    "ConnectionError",
                    "OSError",
                ), f"Unexpected error type: {error_name}: {exc_info.value}"

            # 4. After exit, verify job state on disk is consistent
            #    (the job directory should still exist with its status.json)
            jobs_root = Path(".eigenfrequencies/jobs")
            if jobs_root.is_dir():
                status_files = list(jobs_root.rglob("status.json"))
                # At least one job was submitted before the kill
                assert len(status_files) >= 1, (
                    "Job state disappeared after server kill"
                )

        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════════════════
# verify exactly 6 tools over stdio
# ═══════════════════════════════════════════════════════════════════════════════


class TestE2EToolCount:
    """Verify the server exposes exactly 6 tools via stdio transport."""

    def test_exactly_six_tools_over_stdio(self):
        """list_tools() returns the 6 expected tools."""

        async def _run():
            async with _make_client() as client:
                tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            assert tool_names == {
                "get_config_schema",
                "solve_modal",
                "validate",
                "optimize_start",
                "job_status",
                "fetch_results",
            }, f"Unexpected tool set: {tool_names}"

        asyncio.run(_run())
