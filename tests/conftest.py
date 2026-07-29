"""Root conftest for the tests/ suite.

Guard: if pytest-xdist is not installed, register a no-op ``-n`` option
so the ``addopts = \"-n auto\"`` in ``pyproject.toml`` does not cause an
error.  Tests then fall back to serial execution.
"""

import importlib.util


def pytest_addoption(parser):
    if importlib.util.find_spec("xdist") is None:
        parser.addoption(
            "--numprocesses",
            action="store",
            default=None,
            help="no-op fallback when pytest-xdist is missing",
        )
