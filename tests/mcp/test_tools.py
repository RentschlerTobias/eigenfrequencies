"""Tests for MCP server tools — fastmcp in-memory client.

Tests each of the 6 tools: get_config_schema, solve_modal, validate,
optimize_start, job_status, fetch_results.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── fastmcp availability guard ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _fastmcp_available() -> bool:
    try:
        import fastmcp  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def _jsonschema_available() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


def _require_fastmcp_and_jsonschema() -> None:
    pytest.importorskip("fastmcp")
    pytest.importorskip("jsonschema")


# ── schema reference ──────────────────────────────────────────────────────────

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "schema"
    / "eigenfrequencies-config.schema.json"
)


def _load_committed_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_bytes())


# ── minimal valid config ─────────────────────────────────────────────────────

_MINIMAL_VALID_CONFIG: dict[str, Any] = {
    "optimization": {
        "n_rpm": 72.0,
    },
    "cfd": {
        "n_rpm": 72.0,
    },
}


def _minimal_valid_config() -> dict[str, Any]:
    return dict(_MINIMAL_VALID_CONFIG)  # defensive copy


# ── helpers ──────────────────────────────────────────────────────────────────


class AsyncMock(MagicMock):
    """A MagicMock subclass that works with async context managers."""

    async def __aenter__(self) -> AsyncMock:
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        pass


async def _call_tool(client: Any, name: str, args: dict[str, Any]) -> Any:
    """Call a tool via the fastmcp in-memory client and return its data."""
    _require_fastmcp_and_jsonschema()
    result = await client.call_tool(name, args)
    # result.structured_content is the typed return; result.data is JSON-serialized
    return result.structured_content if result.structured_content is not None else result.data


# ── fixture: client wrapping the server module ────────────────────────────────

@pytest.fixture
def mcp_client():
    """Return an async context manager that yields a fastmcp Client."""
    _require_fastmcp_and_jsonschema()
    from fastmcp import Client

    # Import the server module's mcp instance
    from eigenfrequencies.mcp.server import mcp as server_mcp

    return Client(server_mcp)


# ── fixture: mock JobStore ────────────────────────────────────────────────────

@pytest.fixture
def mock_jobstore():
    """Patch JobStore in the server module so tools return a fake job_id."""
    with patch("eigenfrequencies.mcp.server.JobStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.submit.return_value = "mock-job-id-abc123"
        mock_instance.status.return_value = {
            "state": "done",
            "exit_code": 0,
            "started_utc": "2026-07-29T00:00:00Z",
            "finished_utc": "2026-07-29T00:01:00Z",
            "kind": "solve",
            "config_path": "/tmp/test.yaml",
        }
        mock_instance.fetch.return_value = {
            "frequencies_hz": [8.39, 52.61, 147.38],
        }
        mock_cls.return_value = mock_instance
        yield mock_cls


# ═══════════════════════════════════════════════════════════════════════════════
# get_config_schema
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetConfigSchema:
    def test_returns_valid_schema(self, mcp_client):
        """get_config_schema() returns an object with $schema, type, properties."""
        async def _test():
            async with mcp_client as client:
                data = await _call_tool(client, "get_config_schema", {})
            assert data is not None
            assert "$schema" in data
            assert data["type"] == "object"
            assert "properties" in data
            assert "required" in data
            return data

        import asyncio
        data = asyncio.run(_test())
        assert data is not None

    def test_schema_matches_committed_artifact(self, mcp_client):
        """get_config_schema() returns bytes identical to the committed file."""
        async def _test():
            async with mcp_client as client:
                data = await _call_tool(client, "get_config_schema", {})
            return data

        import asyncio
        committed = _load_committed_schema()
        returned = asyncio.run(_test())
        assert returned == committed, (
            "get_config_schema() output differs from schema/eigenfrequencies-config.schema.json"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# solve_modal
# ═══════════════════════════════════════════════════════════════════════════════


class TestSolveModal:
    def test_valid_config_returns_job_id(self, mcp_client, mock_jobstore):
        """Valid config → {job_id} returned, JobStore.submit called."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "solve_modal", {"config": _minimal_valid_config()}
                )

        import asyncio
        result = asyncio.run(_test())
        assert result == {"job_id": "mock-job-id-abc123"}
        mock_jobstore.return_value.submit.assert_called_once()
        call_kind = mock_jobstore.return_value.submit.call_args[0][0]
        assert call_kind == "solve"

    def test_typo_in_field_name_returns_structured_error(self, mcp_client, mock_jobstore):
        """Typo 'materail' → structured error, zero jobs created."""
        bad_config = {
            "optimization": {"n_rpm": 72.0},
            "cfd": {"n_rpm": 72.0},
            "materail": {"density": 7850},
        }

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "solve_modal", {"config": bad_config}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert result["error"] == "config validation failed"
        assert "details" in result
        # The error should name the offending field
        details_str = " ".join(result["details"])
        assert "materail" in details_str or "Additional properties" in details_str
        # JobStore.submit must NOT have been called
        mock_jobstore.return_value.submit.assert_not_called()

    def test_missing_required_field_returns_error(self, mcp_client, mock_jobstore):
        """Missing 'optimization' → structured error, no job."""
        bad_config = {"cfd": {"n_rpm": 72.0}}

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "solve_modal", {"config": bad_config}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert result["error"] == "config validation failed"
        mock_jobstore.return_value.submit.assert_not_called()

    def test_nested_typo_returns_error_naming_path(self, mcp_client, mock_jobstore):
        """Typo inside 'material' block → error naming the dotted path."""
        bad_config = {
            "optimization": {"n_rpm": 72.0},
            "cfd": {"n_rpm": 72.0},
            "material": {"density": 7850, "youngs_modulus": 210e9, "poisson_ratio": 0.3, "tyop": "bad"},
        }

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "solve_modal", {"config": bad_config}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert result["error"] == "config validation failed"
        # Should name the path or field
        details_str = " ".join(result["details"])
        assert "tyop" in details_str or "Additional properties" in details_str
        mock_jobstore.return_value.submit.assert_not_called()

    def test_non_dict_config_returns_error(self, mcp_client, mock_jobstore):
        """A list instead of dict → validation error (caught by fastmcp input schema)."""
        from fastmcp.exceptions import ToolError

        bad_config = [1, 2, 3]  # type: ignore[assignment]

        async def _test():
            async with mcp_client as client:
                return await client.call_tool(
                    "solve_modal", {"config": bad_config}
                )

        import asyncio
        # fastmcp validates input shape before the tool runs — list is rejected
        try:
            asyncio.run(_test())
            pytest.fail("Expected ToolError was not raised")
        except ToolError as exc:
            assert "dict" in str(exc).lower()
        mock_jobstore.return_value.submit.assert_not_called()


def _make_optimize_config() -> dict[str, Any]:
    return {
        "optimization": {"n_rpm": 72.0},
        "cfd": {"n_rpm": 72.0},
        "design": {"params": {}},
    }


class TestOptimizeStart:
    def test_valid_config_returns_job_id(self, mcp_client, mock_jobstore):
        """Valid config + optimizer → {job_id}."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client,
                    "optimize_start",
                    {"config": _make_optimize_config(), "optimizer": "de"},
                )

        import asyncio
        result = asyncio.run(_test())
        assert result == {"job_id": "mock-job-id-abc123"}
        mock_jobstore.return_value.submit.assert_called_once()
        call_kind = mock_jobstore.return_value.submit.call_args[0][0]
        assert call_kind == "optimize"
        # extra_args should contain --optimizer de
        extra_args = mock_jobstore.return_value.submit.call_args[1].get("extra_args", [])
        assert "--optimizer" in extra_args
        assert "de" in extra_args

    def test_optimize_with_budget_passes_budget(self, mcp_client, mock_jobstore):
        """budget=100 → extra_args includes --budget 100."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client,
                    "optimize_start",
                    {"config": _make_optimize_config(), "optimizer": "de", "budget": 100},
                )

        import asyncio
        result = asyncio.run(_test())
        assert result == {"job_id": "mock-job-id-abc123"}
        extra_args = mock_jobstore.return_value.submit.call_args[1].get("extra_args", [])
        assert "--budget" in extra_args
        assert "100" in extra_args

    def test_invalid_config_returns_structured_error(self, mcp_client, mock_jobstore):
        """Invalid config → error, no job."""
        bad_config = {"materail": "typo"}

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client,
                    "optimize_start",
                    {"config": bad_config, "optimizer": "de"},
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert result["error"] == "config validation failed"
        mock_jobstore.return_value.submit.assert_not_called()

    def test_default_islands_workers(self, mcp_client, mock_jobstore):
        """islands/workers default to 1."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client,
                    "optimize_start",
                    {"config": _make_optimize_config(), "optimizer": "de"},
                )

        import asyncio
        asyncio.run(_test())
        extra_args = mock_jobstore.return_value.submit.call_args[1].get("extra_args", [])
        assert "--islands" in extra_args
        idx = extra_args.index("--islands")
        assert extra_args[idx + 1] == "1"
        assert "--workers" in extra_args
        idx = extra_args.index("--workers")
        assert extra_args[idx + 1] == "1"


# ═══════════════════════════════════════════════════════════════════════════════
# validate
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidate:
    def test_beam_suite_returns_job_id(self, mcp_client, mock_jobstore):
        """suite='beam' → {job_id}."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "validate", {"suite": "beam"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert result == {"job_id": "mock-job-id-abc123"}
        mock_jobstore.return_value.submit.assert_called_once()
        call_kind = mock_jobstore.return_value.submit.call_args[0][0]
        assert call_kind == "validate"

    def test_testcase_suite_returns_job_id(self, mcp_client, mock_jobstore):
        """suite='testcase' → {job_id}."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "validate", {"suite": "testcase"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert result == {"job_id": "mock-job-id-abc123"}

    def test_unknown_suite_returns_error(self, mcp_client, mock_jobstore):
        """suite='unknown' → error, no job."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "validate", {"suite": "unknown"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert "unknown suite" in result["error"].lower()
        mock_jobstore.return_value.submit.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# job_status
# ═══════════════════════════════════════════════════════════════════════════════


class TestJobStatus:
    def test_known_job_returns_status(self, mcp_client, mock_jobstore):
        """Known job_id → status dict."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "job_status", {"job_id": "known-job"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert result["state"] == "done"
        assert result["exit_code"] == 0

    def test_unknown_job_returns_error(self, mcp_client, mock_jobstore):
        """Unknown job_id → error dict."""
        from eigenfrequencies.mcp import JobNotFoundError

        mock_jobstore.return_value.status.side_effect = JobNotFoundError("bad-job")

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "job_status", {"job_id": "bad-job"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert "bad-job" in result["error"]

    def test_failed_job_returns_state_failed(self, mcp_client, mock_jobstore):
        """Failed job → status shows state='failed'."""
        mock_jobstore.return_value.status.return_value = {
            "state": "failed",
            "exit_code": 2,
        }

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "job_status", {"job_id": "failed-job"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert result["state"] == "failed"
        assert result["exit_code"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# fetch_results
# ═══════════════════════════════════════════════════════════════════════════════


class TestFetchResults:
    def test_done_job_returns_results(self, mcp_client, mock_jobstore):
        """Done job → result payload."""
        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "fetch_results", {"job_id": "done-job"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "frequencies_hz" in result

    def test_unknown_job_returns_error(self, mcp_client, mock_jobstore):
        """Unknown job_id → error."""
        from eigenfrequencies.mcp import JobNotFoundError
        mock_jobstore.return_value.fetch.side_effect = JobNotFoundError("nonexistent")

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "fetch_results", {"job_id": "nonexistent"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_not_done_job_returns_error(self, mcp_client, mock_jobstore):
        """Job not yet done → error message."""
        mock_jobstore.return_value.fetch.side_effect = RuntimeError(
            "Job running-job is not done (state='running'). Check status() before fetch()."
        )

        async def _test():
            async with mcp_client as client:
                return await _call_tool(
                    client, "fetch_results", {"job_id": "running-job"}
                )

        import asyncio
        result = asyncio.run(_test())
        assert "error" in result
        assert "not done" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════════════════════
# verify exactly 6 tools
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolCount:
    def test_exactly_six_tools(self, mcp_client):
        """The server exposes exactly 6 tools — no more, no less."""
        async def _test():
            async with mcp_client as client:
                tools = await client.list_tools()
            return tools

        import asyncio
        tools = asyncio.run(_test())
        tool_names = {t.name for t in tools}
        assert tool_names == {
            "get_config_schema",
            "solve_modal",
            "validate",
            "optimize_start",
            "job_status",
            "fetch_results",
        }, f"Unexpected tool set: {tool_names}"
