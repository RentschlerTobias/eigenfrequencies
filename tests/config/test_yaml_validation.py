"""YAML validation tests: unknown keys and missing required fields.

Also covers the typo scenario ``materail:`` → ConfigError.
"""

import os
import tempfile

import pytest

from eigenfrequencies.config_yaml import ConfigError, dump_config, load_config

_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_BEAM_YAML = os.path.join(_REPO_ROOT, "examples", "configs", "beam.yaml")


# ---------------------------------------------------------------------------
# Unknown key tests
# ---------------------------------------------------------------------------

def test_unknown_key_at_root_raises():
    """A top-level typo like ``materail:`` must raise ConfigError."""
    loaded = load_config(_BEAM_YAML)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        dump_config(loaded, tmp.name)
        tmp_path = tmp.name

    try:
        # Inject a typo at the root level
        with open(tmp_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("material:", "materail:")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(text)

        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)

        err_msg = str(exc_info.value)
        assert "materail" in err_msg or "Unknown key" in err_msg, (
            f"Expected ConfigError mentioning unknown key, got: {err_msg}"
        )
    finally:
        os.unlink(tmp_path)


def test_unknown_key_nested_raises():
    """A typo inside a nested block must raise ConfigError with dotted path."""
    loaded = load_config(_BEAM_YAML)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        dump_config(loaded, tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("youngs_modulus:", "youngs_moduluss:")
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(text)

        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)

        err_msg = str(exc_info.value)
        assert "youngs_moduluss" in err_msg or "Unknown key" in err_msg, (
            f"Expected ConfigError mentioning unknown nested key, got: {err_msg}"
        )
        # Dotted path should mention the parent block
        assert "material" in err_msg, (
            f"Expected dotted path to mention 'material', got: {err_msg}"
        )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Missing required field tests
# ---------------------------------------------------------------------------

def test_missing_n_rpm_in_optimization_raises():
    """Omitting the required ``n_rpm`` field must raise ConfigError."""
    loaded = load_config(_BEAM_YAML)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        dump_config(loaded, tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        # Remove the n_rpm line from optimization block
        lines = text.splitlines()
        filtered = [ln for ln in lines if not ln.strip().startswith("n_rpm:")]
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(filtered) + "\n")

        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)

        err_msg = str(exc_info.value)
        assert "n_rpm" in err_msg, (
            f"Expected ConfigError mentioning 'n_rpm', got: {err_msg}"
        )
        assert "Missing required field" in err_msg, (
            f"Expected missing-field wording, got: {err_msg}"
        )
    finally:
        os.unlink(tmp_path)


def test_missing_n_rpm_in_cfd_raises():
    """Omitting ``cfd.n_rpm`` must raise ConfigError listing the field."""
    loaded = load_config(_BEAM_YAML)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        dump_config(loaded, tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        # Remove only the cfd.n_rpm line (appears after "cfd:" block start)
        lines = text.splitlines()
        in_cfd = False
        filtered = []
        for ln in lines:
            stripped = ln.strip()
            if stripped == "cfd:":
                in_cfd = True
            elif stripped.endswith(":") and not stripped.startswith("cfd"):
                in_cfd = False
            if in_cfd and stripped.startswith("n_rpm:"):
                continue
            filtered.append(ln)
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(filtered) + "\n")

        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)

        err_msg = str(exc_info.value)
        assert "n_rpm" in err_msg, (
            f"Expected ConfigError mentioning 'n_rpm', got: {err_msg}"
        )
        assert "Missing required field" in err_msg, (
            f"Expected missing-field wording, got: {err_msg}"
        )
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# YAML root type guard
# ---------------------------------------------------------------------------

def test_non_dict_root_raises():
    """A YAML file containing a bare list must raise ConfigError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        tmp.write("- item1\n- item2\n")
        tmp_path = tmp.name

    try:
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        assert "mapping" in str(exc_info.value)
    finally:
        os.unlink(tmp_path)
