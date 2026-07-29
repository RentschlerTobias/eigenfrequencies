# Test Suite Guide

## Running tests

Install dev dependencies (includes ``pytest-xdist``):

```bash
pip install -e ".[dev]"
```

Run the full suite (parallel by default):

```bash
pytest tests/
```

Run without parallelisation:

```bash
pytest tests/ -n 0
```

If ``pytest-xdist`` is not installed, the ``-n auto`` flag from
``pyproject.toml`` is automatically stripped by the guard in
``tests/conftest.py`` so tests fall back to serial execution.

## Markers

| Marker | Meaning |
|--------|---------|
| ``slow`` | Long-running tests (deselect with ``-m "not slow"``) |
| ``requires_container`` | Needs a Docker container (e.g. FEniCSx image) |
| ``requires_dtoo`` | Needs the dtOO environment |
| ``requires_slurm`` | Needs SLURM cluster access |
| ``serial`` | Must not run in parallel with other tests (MPI/SLEPc or shared worker directories) |

Tests that use MPI/SLEPc backends or write to shared worker directories should
be decorated with ``@pytest.mark.serial`` so that ``pytest-xdist`` groups them
onto a single worker and avoids race conditions.

## Marker registration

All markers are registered in ``pyproject.toml`` under
``[tool.pytest.ini_options]`` so that unknown-marker warnings are suppressed.
