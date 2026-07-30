"""MCP server for eigenfrequencies — async job orchestration via fastmcp.

Exposes 6 tools: get_config_schema, solve_modal, validate, optimize_start,
job_status, fetch_results.  All long-running tools submit jobs via JobStore
and return immediately; the caller polls job_status → fetch_results.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from eigenfrequencies.mcp import JobNotFoundError, JobStore

mcp = FastMCP("eigenfrequencies")

# ── schema path resolution ───────────────────────────────────────────────────

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "schema"
    / "eigenfrequencies-config.schema.json"
)


def _load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_bytes())


def _add_additional_properties_false(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively add ``additionalProperties: false`` to every object schema."""
    import copy

    sc = copy.deepcopy(schema)
    _stack: list[dict[str, Any]] = [sc]
    while _stack:
        node = _stack.pop()
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
        for key in ("properties", "definitions", "$defs"):
            if key in node:
                for sub in node[key].values():
                    if isinstance(sub, dict):
                        _stack.append(sub)
        if "items" in node:
            if isinstance(node["items"], dict):
                _stack.append(node["items"])
            elif isinstance(node["items"], list):
                _stack.extend(i for i in node["items"] if isinstance(i, dict))
    return sc


def _validate_config(config: dict[str, Any]) -> list[str] | None:
    """Validate *config* against the committed JSON Schema.

    Returns ``None`` when valid, or a list of human-readable error strings.
    """
    import jsonschema

    schema = _load_schema()
    strict_schema = _add_additional_properties_false(schema)
    validator = jsonschema.Draft7Validator(strict_schema)
    errors = sorted(
        validator.iter_errors(config),
        key=lambda e: list(e.absolute_path),
    )
    if not errors:
        return None
    return [
        f"{' -> '.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in errors
    ]


def _write_temp_config(config: dict[str, Any]) -> str:
    """Write *config* to a temporary YAML file and return the path."""
    # PyYAML safe_load accepts JSON, but write as YAML so the CLI's YAML
    # parser is the exact code path.
    import yaml

    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    with f:
        yaml.dump(config, f, sort_keys=False)
    return f.name


# ── tools ─────────────────────────────────────────────────────────────────────


@mcp.tool
def get_config_schema() -> dict[str, Any]:
    """Return the JSON Schema for eigenfrequencies configuration files.

    Use this to validate configs before submitting solve or optimize jobs.
    The returned schema is the committed artifact from
    ``schema/eigenfrequencies-config.schema.json``.
    """
    return _load_schema()


@mcp.tool
def solve_modal(config: dict[str, Any]) -> dict[str, Any]:
    """Submit an async modal-solve job from a config dict.

    Validates *config* against the JSON schema first.  If validation fails,
    returns a structured error dict (no job created).  If valid, writes the
    config to a temporary file and submits a ``solve`` job via JobStore.

    Returns ``{"job_id": "<uuid>"}`` on success.
    """
    errors = _validate_config(config)
    if errors is not None:
        return {"error": "config validation failed", "details": errors}

    config_path = _write_temp_config(config)
    store = JobStore()
    job_id = store.submit("solve", config_path)
    return {"job_id": job_id}


@mcp.tool
def validate(suite: str) -> dict[str, Any]:
    """Submit an async validation-suite job.

    *suite* must be ``"beam"`` or ``"testcase"``.
    The job runs ``eigenfrequencies validate --suite <suite>`` in a
    subprocess.  Poll ``job_status`` until ``state == "done"``, then call
    ``fetch_results``.

    Returns ``{"job_id": "<uuid>"}`` on success.
    """
    if suite not in ("beam", "testcase"):
        return {"error": f"unknown suite {suite!r}; choose 'beam' or 'testcase'"}

    store = JobStore()
    job_id = store.submit("validate", suite)
    return {"job_id": job_id}


@mcp.tool
def optimize_start(
    config: dict[str, Any],
    optimizer: str,
    islands: int = 1,
    workers: int = 1,
    budget: int | None = None,
) -> dict[str, Any]:
    """Submit an async optimization job.

    Validates *config* against the JSON schema first.  *optimizer* must be
    one of ``de``, ``pso``, ``cmaes``, ``bo``, or ``rl``.

    Returns ``{"job_id": "<uuid>"}`` on success.
    """
    errors = _validate_config(config)
    if errors is not None:
        return {"error": "config validation failed", "details": errors}

    config_path = _write_temp_config(config)
    extra = ["--optimizer", optimizer, "--islands", str(islands),
             "--workers", str(workers)]
    if budget is not None:
        extra.extend(["--budget", str(budget)])

    store = JobStore()
    job_id = store.submit("optimize", config_path, extra_args=extra)
    return {"job_id": job_id}


@mcp.tool
def job_status(job_id: str) -> dict[str, Any]:
    """Return the current status dict for a job.

    Poll this until ``state`` is ``"done"`` or ``"failed"`` before calling
    ``fetch_results``.
    """
    store = JobStore()
    try:
        return store.status(job_id)
    except JobNotFoundError:
        return {"error": f"job {job_id!r} not found"}


@mcp.tool
def fetch_results(job_id: str) -> dict[str, Any]:
    """Return the result payload for a finished job.

    Raises an error if the job is not yet done or not found.
    Always check ``job_status`` first.
    """
    store = JobStore()
    try:
        return store.fetch(job_id)
    except JobNotFoundError:
        return {"error": f"job {job_id!r} not found"}
    except RuntimeError as exc:
        return {"error": str(exc)}


# ── resource paths ────────────────────────────────────────────────────────────

_MACHINES_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "adapters" / "machines"
)

_DOCS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
)

_VALIDATION_DOC = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "turbine_runner" / "VALIDATION_summary.md"
)

_VALID_HOWTO_TOPICS = frozenset({"install", "adapters", "cluster", "mcp"})


# ── resources ─────────────────────────────────────────────────────────────────


@mcp.resource("results://{job_id}")
def resource_results(job_id: str) -> str:
    """Return the result JSON for a finished job.

    Reads from JobStore.fetch().  Returns an error string if the job is
    not found or not yet done.
    """
    store = JobStore()
    try:
        result = store.fetch(job_id)
        return json.dumps(result, indent=2)
    except JobNotFoundError:
        return json.dumps({"error": f"job {job_id!r} not found"})
    except RuntimeError as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("machines://")
def resource_machines() -> str:
    """Return the list of available machine adapter YAMLs.

    Reads the machine catalog from ``adapters/machines/`` (tistos,
    canadaLight, naca).
    """
    if not _MACHINES_DIR.is_dir():
        return json.dumps({"machines": [], "error": "machines directory not found"})
    machines = sorted(p.name for p in _MACHINES_DIR.glob("*.yaml"))
    return json.dumps({"machines": machines})


@mcp.resource("docs://validation")
def resource_docs_validation() -> str:
    """Return the validation summary (beam + testcase).

    Sources ``turbine_runner/VALIDATION_summary.md``.
    """
    if _VALIDATION_DOC.is_file():
        return _VALIDATION_DOC.read_text(encoding="utf-8")
    return "# Validation documentation not found\n"


@mcp.resource("docs://howto/{topic}")
def resource_docs_howto(topic: str) -> str:
    """Return the howto document for *topic*.

    Valid topics: install, adapters, cluster, mcp.
    """
    if topic not in _VALID_HOWTO_TOPICS:
        return json.dumps(
            {"error": f"unknown topic {topic!r}; choose from {sorted(_VALID_HOWTO_TOPICS)}"}
        )
    doc_path = _DOCS_DIR / f"{topic}.md"
    if doc_path.is_file():
        return doc_path.read_text(encoding="utf-8")
    return json.dumps({"error": f"documentation for {topic!r} not found"})


def main() -> None:
    """Entry point for ``eigenfrequencies-mcp`` console script."""
    mcp.run()
