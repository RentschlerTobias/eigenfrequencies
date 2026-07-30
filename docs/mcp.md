# MCP Server

The eigenfrequencies MCP server exposes the solver, validator, and optimizer as async tools that AI agents can call without blocking. It is built on `fastmcp` and runs as a separate process.

## Server start

Install the MCP extra:

```bash
uv pip install -e ".[mcp]"
```

Start the server:

```bash
eigenfrequencies-mcp
```

The server listens on stdio by default (MCP transport). For debugging, run with `EIGENFREQ_MCP_LOG_LEVEL=debug`.

## Client configuration

### OpenCode

Add to your project-local `.opencode/mcp.json`:

```json
{
  "mcpServers": {
    "eigenfrequencies": {
      "command": "eigenfrequencies-mcp",
      "env": {
        "EIGENFREQ_MCP_LOG_LEVEL": "info",
        "EIGENFREQ_JOBS_ROOT": ".eigenfrequencies/jobs"
      }
    }
  }
}
```

For uv-managed environments, use the full path:

```json
{
  "mcpServers": {
    "eigenfrequencies": {
      "command": "/path/to/project/.venv/bin/eigenfrequencies-mcp",
      "env": {
        "EIGENFREQ_MCP_LOG_LEVEL": "info"
      }
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json` (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "eigenfrequencies": {
      "command": "/path/to/conda/envs/eigenfrequencies/bin/eigenfrequencies-mcp",
      "env": {
        "EIGENFREQ_MCP_LOG_LEVEL": "info",
        "EIGENFREQ_JOBS_ROOT": "/tmp/eigenfrequencies-jobs"
      }
    }
  }
}
```

Replace `/path/to/conda/envs/eigenfrequencies/bin/` with the actual path to the activated environment.  For uv-managed projects, point to `.venv/bin/eigenfrequencies-mcp`.

### Environment overrides

| Variable | Default | Purpose |
|---|---|---|
| `EIGENFREQ_MCP_LOG_LEVEL` | `info` | Server log level (`debug`, `info`, `warning`, `error`) |
| `EIGENFREQ_JOBS_ROOT` | `.eigenfrequencies/jobs` | Job storage directory (relative to CWD) |

## Tools (6)

### `get_config_schema`

Returns the JSON schema for a valid eigenfrequencies YAML config. Use this to validate configs before submitting solve or optimize jobs.

**Input**: none  
**Output**: JSON schema object

### `solve_modal`

Submit an async modal-solve job from a config dict.

**Input**: `{config: object}`  (full RunConfig dict matching the JSON schema)  
**Output**: `{job_id: string}` or `{error: string, details: [string]}`

The config is validated against the committed JSON Schema before job submission.
If validation fails, returns a structured error naming the offending field and
creates zero jobs.

### `validate`

Submit a validation-suite job.

**Input**: `{suite: "beam" | "testcase"}`  
**Output**: `{job_id: string}`

- `suite: "beam"` runs the cantilever beam FEM vs analytical check.
- `suite: "testcase"` runs the Laval disc validation.

### `optimize_start`

Submit an async optimization job.

**Input**:

```json
{
  "config": { … },
  "optimizer": "de | pso | cmaes | bo | rl",
  "islands": 1,
  "workers": 1,
  "budget": null
}
```

**Output**: `{job_id: string}` or `{error: string, details: [string]}`

The config is validated against the JSON schema before submission.
Island optimization (`islands > 1`) is planned but not yet implemented.

### `job_status`

Poll the status of a submitted job.

**Input**: `{job_id: string}`  
**Output**:

```json
{
  "state": "queued | running | done | failed",
  "exit_code": null | int,
  "started_utc": "ISO8601",
  "finished_utc": null | "ISO8601",
  "kind": "solve | validate | optimize",
  "config_path": "string"
}
```

### `fetch_results`

Return the result payload for a finished job.

**Input**: `{job_id: string}`  
**Output**: result JSON (structure depends on job kind)

Raises an error if the job is not yet done. Always check `job_status` first.

## Resources (4)

The server exposes four read-only resources:

| URI | Type | Description |
|---|---|---|
| `results://{job_id}` | Template | Result JSON for a finished job (frequencies, eigenvalues, provenance) |
| `machines://` | Concrete | List of available machine adapter YAMLs (`tistos.yaml`, `canadaLight.yaml`, `naca.yaml`) |
| `docs://validation` | Concrete | Validation summary document (beam + testcase) |
| `docs://howto/{topic}` | Template | How-to guides for `install`, `adapters`, `cluster`, `mcp` |

Resources are read-only — no write endpoints exist.

## Guardrails

The eigenfrequencies MCP server is intentionally scoped to **job orchestration** only. It does NOT expose:

- Code-graph tools (no `read_file`, `edit_file`, or AST traversal)
- Shell execution (all work happens inside isolated subprocesses)
- Network access beyond local file paths

This keeps the blast radius small: a misbehaving agent can only submit, poll, and fetch solver jobs. It cannot modify source code or access the broader system.
