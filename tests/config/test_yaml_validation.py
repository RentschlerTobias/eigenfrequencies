"""YAML validation tests: unknown keys and missing required fields.

Also covers the typo scenario ``materail:`` → ConfigError.
"""

import os
import tempfile

import pytest

from eigenfrequencies.config import ModalAnalysisConfig, ResonanceConfig
from eigenfrequencies.config_yaml import ConfigError, dump_config, load_config


def _minimal_config() -> ModalAnalysisConfig:
    return ModalAnalysisConfig(resonance=ResonanceConfig(n_rpm=72.0))


def _dumped() -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
        dump_config(_minimal_config(), tmp.name)
        return tmp.name


def _mutate(path: str, old: str, new: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))


def test_unknown_key_at_root_raises():
    """A top-level typo like ``materail:`` must raise ConfigError."""
    tmp_path = _dumped()
    try:
        _mutate(tmp_path, "material:", "materail:")
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        err_msg = str(exc_info.value)
        assert "materail" in err_msg or "Unknown key" in err_msg, err_msg
    finally:
        os.unlink(tmp_path)


def test_unknown_key_nested_raises():
    """A typo inside a nested block must raise ConfigError with dotted path."""
    tmp_path = _dumped()
    try:
        _mutate(tmp_path, "youngs_modulus:", "youngs_moduluss:")
        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        err_msg = str(exc_info.value)
        assert "youngs_moduluss" in err_msg or "Unknown key" in err_msg, err_msg
        assert "material" in err_msg, err_msg
    finally:
        os.unlink(tmp_path)


def test_missing_n_rpm_raises():
    """Omitting the required ``resonance.n_rpm`` field must raise ConfigError."""
    tmp_path = _dumped()
    try:
        with open(tmp_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        filtered = [ln for ln in lines if not ln.strip().startswith("n_rpm:")]
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(filtered) + "\n")

        with pytest.raises(ConfigError) as exc_info:
            load_config(tmp_path)
        err_msg = str(exc_info.value)
        assert "n_rpm" in err_msg, err_msg
        assert "Missing required field" in err_msg, err_msg
    finally:
        os.unlink(tmp_path)


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
