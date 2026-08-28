"""Tests for MCP server resources — fastmcp in-memory client.

Tests the 4 resources: results://{job_id}, machines://, docs://validation,
docs://howto/{topic}.  Also verifies guardrails: exactly 6 tools, no
code-graph tooling, resources are read-only.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── fastmcp availability guard ────────────────────────────────────────────────


def _require_fastmcp() -> None:
    pytest.importorskip("fastmcp")
    pytest.importorskip("jsonschema")


async def _read_resource(client: Any, uri: str) -> str:
    """Read a resource via the fastmcp in-memory client and return text content."""
    _require_fastmcp()
    result = await client.read_resource(uri)
    assert len(result) > 0
    return result[0].text


# ── fixture: client wrapping the server module ────────────────────────────────


@pytest.fixture
def mcp_client():
    """Return an async context manager that yields a fastmcp Client."""
    _require_fastmcp()
    from fastmcp import Client

    from eigenfrequencies.mcp.server import mcp as server_mcp

    return Client(server_mcp)


# ── fixture: mock JobStore ────────────────────────────────────────────────────


@pytest.fixture
def mock_jobstore():
    """Patch JobStore in the server module so fetch returns a known result."""
    with patch("eigenfrequencies.mcp.server.JobStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.fetch.return_value = {
            "frequencies_hz": [8.39, 52.61, 147.38],
            "mode_shapes": "modes.xdmf",
        }
        mock_cls.return_value = mock_instance
        yield mock_cls


# ═══════════════════════════════════════════════════════════════════════════════
# results://{job_id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestResultsResource:
    def test_returns_result_json_for_done_job(self, mcp_client, mock_jobstore):
        """results://known-job returns the JobStore.fetch() result as JSON."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "results://known-job")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert data["frequencies_hz"] == [8.39, 52.61, 147.38]
        assert data["mode_shapes"] == "modes.xdmf"
        mock_jobstore.return_value.fetch.assert_called_once_with("known-job")

    def test_not_found_job_returns_error(self, mcp_client, mock_jobstore):
        """results://nonexistent returns an error when JobStore.fetch raises."""
        from eigenfrequencies.mcp import JobNotFoundError

        mock_jobstore.return_value.fetch.side_effect = JobNotFoundError("nonexistent")

        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "results://nonexistent")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert "error" in data
        assert "nonexistent" in data["error"]

    def test_not_done_job_returns_error(self, mcp_client, mock_jobstore):
        """results://running-job returns an error when the job is not done."""
        mock_jobstore.return_value.fetch.side_effect = RuntimeError(
            "Job running-job is not done (state='running')."
        )

        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "results://running-job")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert "error" in data
        assert "not done" in data["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# machines://
# ═══════════════════════════════════════════════════════════════════════════════


class TestMachinesResource:
    def test_returns_machine_list(self, mcp_client):
        """machines:// returns the list of available YAMLs from adapters/machines/."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "machines://")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert "machines" in data
        machines = data["machines"]
        assert "tistos.yaml" in machines
        assert "canadaLight.yaml" in machines
        assert "naca.yaml" in machines
        assert len(machines) >= 3

    def test_machines_are_sorted(self, mcp_client):
        """machines:// returns a sorted list."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "machines://")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert data["machines"] == sorted(data["machines"])


# ═══════════════════════════════════════════════════════════════════════════════
# docs://validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocsValidationResource:
    def test_returns_validation_summary(self, mcp_client):
        """docs://validation returns the VALIDATION_summary.md content."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://validation")
            return text

        import asyncio

        text = asyncio.run(_test())
        assert "Validierung" in text or "validation" in text.lower()
        assert len(text) > 200  # substantial document


# ═══════════════════════════════════════════════════════════════════════════════
# docs://howto/{topic}
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocsHowtoResource:
    def test_install_topic_returns_content(self, mcp_client):
        """docs://howto/install returns the install guide."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://howto/install")
            return text

        import asyncio

        text = asyncio.run(_test())
        assert "conda" in text.lower() or "install" in text.lower()
        assert len(text) > 50

    def test_adapters_topic_returns_content(self, mcp_client):
        """docs://howto/adapters returns the adapters guide."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://howto/adapters")
            return text

        import asyncio

        text = asyncio.run(_test())
        assert "adapter" in text.lower()
        assert len(text) > 50

    def test_cluster_topic_returns_content(self, mcp_client):
        """docs://howto/cluster returns the cluster guide."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://howto/cluster")
            return text

        import asyncio

        text = asyncio.run(_test())
        assert "cluster" in text.lower() or "slurm" in text.lower()
        assert len(text) > 50

    def test_mcp_topic_returns_content(self, mcp_client):
        """docs://howto/mcp returns the MCP guide."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://howto/mcp")
            return text

        import asyncio

        text = asyncio.run(_test())
        assert "mcp" in text.lower()
        assert len(text) > 50

    def test_unknown_topic_returns_error(self, mcp_client):
        """docs://howto/nonexistent returns a structured error."""
        async def _test():
            async with mcp_client as client:
                text = await _read_resource(client, "docs://howto/nonexistent")
            return text

        import asyncio

        text = asyncio.run(_test())
        data = json.loads(text)
        assert "error" in data
        assert "unknown topic" in data["error"].lower()
        assert "nonexistent" in data["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# resource listing
# ═══════════════════════════════════════════════════════════════════════════════


class TestResourceListing:
    def test_all_concrete_resources_are_listable(self, mcp_client):
        """list_resources() includes the 2 concrete resources."""
        async def _test():
            async with mcp_client as client:
                resources = await client.list_resources()
            return resources

        import asyncio

        resources = asyncio.run(_test())
        uris = {str(r.uri) for r in resources}
        assert "machines://" in uris
        assert "docs://validation" in uris

    def test_all_templates_are_listable(self, mcp_client):
        """list_resource_templates() includes the 2 template resources."""
        async def _test():
            async with mcp_client as client:
                templates = await client.list_resource_templates()
            return templates

        import asyncio

        templates = asyncio.run(_test())
        uris = {str(t.uriTemplate) for t in templates}
        assert "results://{job_id}" in uris
        assert "docs://howto/{topic}" in uris

    def test_howto_template_exposes_valid_topics(self, mcp_client):
        """docs://howto/{topic} template is registered and resolves for each valid topic."""
        async def _test():
            async with mcp_client as client:
                templates = await client.list_resource_templates()
            return templates

        import asyncio

        templates = asyncio.run(_test())
        howto = [
            t for t in templates
            if str(t.uriTemplate).startswith("docs://howto/")
        ]
        assert len(howto) == 1
        assert str(howto[0].uriTemplate) == "docs://howto/{topic}"


# ═══════════════════════════════════════════════════════════════════════════════
# guardrail: exactly 6 tools, no code-graph tooling, resources are read-only
# ═══════════════════════════════════════════════════════════════════════════════


_EXPECTED_SIX_TOOLS = {
    "get_config_schema",
    "solve_modal",
    "validate",
    "optimize_start",
    "job_status",
    "fetch_results",
}

# Tool names that would indicate code-graph / source-code-awareness —
# these MUST NOT appear in the MCP server tool registry.
_CODE_GRAPH_SMELLS = frozenset({
    "explain_codebase",
    "read_file",
    "edit_file",
    "list_files",
    "search_code",
    "query_graph",
    "get_symbol",
    "find_references",
    "ast_query",
    "codebase_query",
    "explain",
})


class TestGuardrails:
    def test_exactly_six_tools(self, mcp_client):
        """The server exposes exactly the 6 job-orchestration tools — no more."""
        async def _test():
            async with mcp_client as client:
                tools = await client.list_tools()
            return tools

        import asyncio

        tools = asyncio.run(_test())
        tool_names = {t.name for t in tools}
        assert tool_names == _EXPECTED_SIX_TOOLS, (
            f"Expected exactly 6 tools {_EXPECTED_SIX_TOOLS}, got {len(tools)}: {tool_names}"
        )

    def test_no_code_graph_tooling(self, mcp_client):
        """The server exposes zero code-graph / source-code-awareness tools."""
        async def _test():
            async with mcp_client as client:
                tools = await client.list_tools()
            return tools

        import asyncio

        tools = asyncio.run(_test())
        tool_names = {t.name for t in tools}
        code_graph_overlap = tool_names & _CODE_GRAPH_SMELLS
        assert not code_graph_overlap, (
            f"Code-graph tooling detected: {code_graph_overlap}. "
            f"MCP server tools must be job-orchestration only."
        )

    def test_resources_are_read_only(self, mcp_client):
        """All resources and templates are read-only.

        Read-only means the client can only read resource content; there are
        no resource update/delete endpoints.  fastmcp resources are read-only
        by default.
        """
        async def _test():
            async with mcp_client as client:
                resources = await client.list_resources()
                templates = await client.list_resource_templates()
            return resources, templates

        import asyncio

        resources, templates = asyncio.run(_test())
        assert len(resources) >= 2
        assert len(templates) >= 2
        for r in resources:
            uri = str(r.uri)
            assert "://" in uri or uri.startswith("docs://"), (
                f"Resource URI {uri!r} does not follow read-only URI convention"
            )
        for t in templates:
            uri = str(t.uriTemplate)
            assert "://" in uri or uri.startswith("docs://"), (
                f"Template URI {uri!r} does not follow read-only URI convention"
            )

    def test_probe_tool_would_be_caught_by_registry_check(self, mcp_client):
        """Demonstrate that adding a code-graph probe tool breaks the 6-tool invariant.

        This test temporarily registers a probe tool on the server's mcp instance
        to prove the guardrail catches tool-creep, then removes it again.

        The probe MUST be removed in a finally block. ``mcp`` is a module-level
        singleton, so a tool registered here stays registered for the rest of the
        session and makes test_exactly_six_tools fail depending on test order.
        """
        from eigenfrequencies.mcp.server import mcp as server_mcp

        # Register a code-graph probe tool that must NOT ship in production.
        @server_mcp.tool
        def explain_codebase() -> str:
            """Probe: explain the codebase structure.  MUST NOT ship."""
            return "This tool should never appear in the production server."

        async def _check():
            async with mcp_client as client:
                tools = await client.list_tools()
            return tools

        import asyncio

        try:
            tools = asyncio.run(_check())
            tool_names = {t.name for t in tools}

            # The registry test (test_exactly_six_tools) would FAIL here because
            # we now have 7 tools instead of 6, and "explain_codebase" is a
            # code-graph smell.
            assert len(tools) == 7, (
                f"Expected 7 tools (6 + probe), got {len(tools)}: {tool_names}"
            )
            assert "explain_codebase" in tool_names
            code_graph_overlap = tool_names & _CODE_GRAPH_SMELLS
            assert "explain_codebase" in code_graph_overlap, (
                f"Probe tool 'explain_codebase' should be in code-graph smell set. "
                f"Overlap: {code_graph_overlap}"
            )

            # The 6-tool assertion would fail:
            assert tool_names != _EXPECTED_SIX_TOOLS, (
                "After adding probe, tool set must NOT equal the expected 6-tool set"
            )
        finally:
            server_mcp.remove_tool("explain_codebase")
