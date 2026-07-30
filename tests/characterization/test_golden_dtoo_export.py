"""Driver-integration characterization test: dtOO export parity and env-override matrix.

Freezes the expected behavior of ``turbine_runner.dtoo_export`` (a kept driver
file) so that future changes to env-var handling, defaults, or export output
are caught immediately.

This is an explicitly-marked driver-integration test: it imports from
``turbine_runner`` because ``dtoo_export.py`` is a driver file that has not been
ported into the ``eigenfrequencies`` package.

This test runs **inside the dtOO container** (atismer/dtoo-opensuse:stable) where
dtOOPythonSWIG is available. Locally it skips gracefully with a clear message.

Golden file: ``golden/dtoo_export.json`` documents the env-override matrix,
expected output checksum, and design.json content.
"""

import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

# Module-level skip: dtOO is only available inside its container.
pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("dtOOPythonSWIG") is None,
    reason="dtOOPythonSWIG not available — run inside the dtOO container "
           "(atismer/dtoo-opensuse:stable) with LD_LIBRARY_PATH set",
)

_GOLDEN_DIR = Path(__file__).with_suffix("").parent / "golden"
_GOLDEN_PATH = _GOLDEN_DIR / "dtoo_export.json"


def _load_golden() -> dict:
    with open(_GOLDEN_PATH) as fh:
        return json.load(fh)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class TestDtOOExportHappyPath:
    """Verify that dtoo_export.py produces the expected runner.msh."""

    def test_export_produces_runner_msh(self, tmp_path: Path):
        """Run dtoo_export.main() and assert the output file exists."""
        golden = _load_golden()
        output_msh = tmp_path / "runner.msh"

        # Point the export at a temp output so we do not clobber data/runner.msh.
        os.environ["DTOO_OUTPUT_MSH"] = str(output_msh)
        # Ensure we use the baseline (no design overrides).
        os.environ["DTOO_DESIGN_JSON"] = ""

        from turbine_runner import dtoo_export

        dtoo_export.main()

        assert output_msh.exists(), "dtoo_export did not write runner.msh"
        assert output_msh.stat().st_size > 0, "runner.msh is empty"

    def test_runner_msh_checksum_matches_golden(self, tmp_path: Path):
        """SHA-256 of runner.msh must match the frozen golden checksum.

        If the golden checksum is ``TBD``, the test xfail-s so that the
        first container run records the actual hash.
        """
        golden = _load_golden()
        expected_checksum = golden["checksum"]
        output_msh = tmp_path / "runner.msh"

        os.environ["DTOO_OUTPUT_MSH"] = str(output_msh)
        os.environ["DTOO_DESIGN_JSON"] = ""

        from turbine_runner import dtoo_export

        dtoo_export.main()

        if expected_checksum == "TBD — generate in dtOO container":
            actual = _sha256_file(str(output_msh))
            pytest.xfail(
                f"Golden checksum is TBD. Actual SHA-256: {actual}"
            )

        actual = _sha256_file(str(output_msh))
        assert actual == expected_checksum, (
            f"runner.msh checksum changed!\n"
            f"  expected: {expected_checksum}\n"
            f"  actual:   {actual}\n"
            f"If the change is intentional, update golden/dtoo_export.json"
        )

    def test_design_json_roundtrip(self, tmp_path: Path):
        """Supply a design.json and assert the exported mesh differs from baseline."""
        golden = _load_golden()
        design_data = golden["design_json"]
        design_json = tmp_path / "design.json"
        with open(design_json, "w") as fh:
            json.dump(design_data, fh)

        baseline_msh = tmp_path / "baseline.msh"
        design_msh = tmp_path / "design.msh"

        # Baseline run.
        os.environ["DTOO_DESIGN_JSON"] = ""
        os.environ["DTOO_OUTPUT_MSH"] = str(baseline_msh)
        from turbine_runner import dtoo_export as dte1
        dte1.main()

        # Design run.
        os.environ["DTOO_DESIGN_JSON"] = str(design_json)
        os.environ["DTOO_OUTPUT_MSH"] = str(design_msh)
        # Re-import to pick up fresh module-level env reads.
        import importlib
        dte2 = importlib.reload(dte1)
        dte2.main()

        assert baseline_msh.exists() and design_msh.exists()
        baseline_hash = _sha256_file(str(baseline_msh))
        design_hash = _sha256_file(str(design_msh))
        assert baseline_hash != design_hash, (
            "Design JSON did not alter the exported mesh — "
            "check that design parameters are being applied"
        )


class TestDtOOExportEnvOverrides:
    """Verify env-override matrix documented in golden/dtoo_export.json."""

    def test_dtoo_case_dir_nonexistent_raises(self, tmp_path: Path):
        """DTOO_CASE_DIR pointing at a nonexistent directory must raise."""
        nonexistent = tmp_path / "no_such_case_dir"
        os.environ["DTOO_CASE_DIR"] = str(nonexistent)
        os.environ["DTOO_OUTPUT_MSH"] = str(tmp_path / "runner.msh")

        from turbine_runner import dtoo_export

        with pytest.raises((FileNotFoundError, OSError)) as exc_info:
            dtoo_export.main()

        err_msg = str(exc_info.value)
        assert "No such file" in err_msg or "cannot change" in err_msg.lower() or \
               "not a directory" in err_msg.lower(), (
            f"Expected chdir/FileNotFound error for missing case dir, got: {err_msg}"
        )

    def test_dtoo_design_json_invalid_path_uses_baseline(self, tmp_path: Path):
        """DTOO_DESIGN_JSON set to a nonexistent file must fall back to baseline."""
        os.environ["DTOO_DESIGN_JSON"] = str(tmp_path / "missing.json")
        os.environ["DTOO_OUTPUT_MSH"] = str(tmp_path / "runner.msh")

        from turbine_runner import dtoo_export

        dtoo_export.main()

        assert (tmp_path / "runner.msh").exists()

    def test_dtoo_output_msh_override(self, tmp_path: Path):
        """DTOO_OUTPUT_MSH must redirect the mesh write location."""
        custom_msh = tmp_path / "custom" / "path" / "output.msh"
        os.environ["DTOO_OUTPUT_MSH"] = str(custom_msh)
        os.environ["DTOO_DESIGN_JSON"] = ""

        from turbine_runner import dtoo_export

        dtoo_export.main()

        assert custom_msh.exists(), "DTOO_OUTPUT_MSH override was ignored"

    def test_dtoo_log_file_default(self, tmp_path: Path):
        """Default DTOO_LOG_FILE is <dirname(OUTPUT_MSH)>/dtoo_build.log."""
        output_msh = tmp_path / "runner.msh"
        expected_log = tmp_path / "dtoo_build.log"
        os.environ["DTOO_OUTPUT_MSH"] = str(output_msh)
        os.environ["DTOO_DESIGN_JSON"] = ""
        # Clear any explicit override so the default kicks in.
        os.environ.pop("DTOO_LOG_FILE", None)

        from turbine_runner import dtoo_export

        dtoo_export.main()

        assert expected_log.exists(), (
            "Default log file dtoo_build.log was not created"
        )
