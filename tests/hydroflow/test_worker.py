"""The evaluation worker against the hydroflow-opt contract.

The physics stages are stubbed — what is under test is the contract: a
``result.json`` on every path, exit 0 even when the design fails, the
candidate id echoed back, and the options and per-candidate scratch directory
actually reaching the physics. ``worker.evaluate`` imports the stages lazily,
so none of this needs dtOO or dolfinx.
"""

import json
from pathlib import Path

import pytest

from eigenfrequencies.hydroflow import worker

MACHINE_YAML = str(Path(__file__).parents[2] / "adapters" / "machines" / "naca.yaml")
FREQUENCIES = [12.0, 48.0, 130.0]


@pytest.fixture
def stub_stages(monkeypatch):
    """Record what the stages were called with; return plausible physics."""
    calls = {}

    def modal(machine_cfg, parameters, options, context=None):
        calls["modal"] = {"parameters": dict(parameters), "options": options, "context": context}
        return list(FREQUENCIES), {
            "mesh_seconds": 1.5,
            "modal_seconds": 4.0,
            "msh_path": "/tmp/x.msh",
        }

    def cfd(machine_cfg, parameters, options, cfd_cfg, context=None):
        calls["cfd"] = {"parameters": dict(parameters), "options": options, "context": context}
        return {"ok": True, "eta": -0.93, "vcav": 1e-7, "dH": -2.4, "P": 1.0, "Q": 0.5}

    monkeypatch.setattr("eigenfrequencies.hydroflow.physics.run_modal_stage", modal)
    monkeypatch.setattr("eigenfrequencies.hydroflow.physics.run_cfd_stage", cfd)
    return calls


def write_request(tmp_path: Path, *, options: dict | None = None, context: dict | None = None,
                  parameters: dict | None = None, candidate_id: str = "island-000-initial-000"):
    """Write a request.json in the shape SubprocessBackend produces."""
    request = {
        "candidate": {
            "id": candidate_id,
            "parameters": parameters if parameters is not None else {"cV_bladeLength": 1.0},
        },
        "case": {"name": "naca", "options": {"machine_yaml": MACHINE_YAML, **(options or {})}},
        "context": context if context is not None else {"scratch_dir": str(tmp_path / "scratch")},
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return path


def run_worker(tmp_path: Path, request_path: Path) -> dict:
    """Run the worker CLI, assert it exited 0, return the parsed result."""
    result_path = tmp_path / "result.json"
    assert worker.main(["--machine", "naca", str(request_path), str(result_path)]) == 0
    return json.loads(result_path.read_text(encoding="utf-8"))


class TestSuccessPath:
    def test_combined_evaluation_reports_both_physics(self, tmp_path, stub_stages):
        result = run_worker(tmp_path, write_request(tmp_path))

        assert result["status"] == "success"
        assert result["candidate_id"] == "island-000-initial-000"
        assert isinstance(result["objective"], float)
        assert result["error"] is None
        assert result["metadata"]["frequencies_hz"] == FREQUENCIES
        assert result["metadata"]["cfd"]["eta"] == pytest.approx(-0.93)
        assert result["metadata"]["breakdown"]["f_cfd"] > 0

    def test_stage_timings_are_separated(self, tmp_path, stub_stages):
        result = run_worker(tmp_path, write_request(tmp_path))
        timings = result["timings"]

        # Each half of the modal stage times itself; a derived duration went
        # negative as soon as the two clocks disagreed.
        assert timings["mesh"] == pytest.approx(1.5)
        assert timings["modal"] == pytest.approx(4.0)
        assert set(timings) == {"mesh", "modal", "cfd", "total"}
        assert result["metadata"]["mesh"]["msh_path"] == "/tmp/x.msh"

    def test_cfd_only_skips_the_modal_solve(self, tmp_path, stub_stages):
        result = run_worker(tmp_path, write_request(tmp_path, options={"eval_mode": "cfd_only"}))

        assert result["status"] == "success"
        assert "modal" not in stub_stages
        assert "frequencies_hz" not in result["metadata"]

    def test_resonance_only_skips_the_cfd(self, tmp_path, stub_stages):
        result = run_worker(
            tmp_path, write_request(tmp_path, options={"eval_mode": "resonance_only"})
        )

        assert result["status"] == "success"
        assert "cfd" not in stub_stages
        assert result["metadata"]["frequencies_hz"] == FREQUENCIES


class TestOptionsPlumbing:
    def test_options_are_read_from_the_case_table(self, tmp_path, stub_stages):
        """Regression: the orchestrator nests them under ``case.options``.

        Reading ``request.options`` instead returns ``{}`` for every candidate,
        so the whole [case.options] table — runtimes, images, timeouts — is
        silently dropped and the worker runs on defaults.
        """
        request = write_request(tmp_path, options={"dtoo": {"runtime": "enroot"}})
        run_worker(tmp_path, request)

        assert stub_stages["modal"]["options"]["dtoo"] == {"runtime": "enroot"}

    def test_the_candidate_scratch_dir_reaches_the_stages(self, tmp_path, stub_stages):
        scratch = str(tmp_path / "island-000-trial-007")
        run_worker(tmp_path, write_request(tmp_path, context={"scratch_dir": scratch}))

        assert stub_stages["modal"]["context"]["scratch_dir"] == scratch
        assert stub_stages["cfd"]["context"]["scratch_dir"] == scratch

    def test_n_rpm_option_drives_the_operating_point(self, tmp_path, monkeypatch):
        captured = {}

        def cfd(machine_cfg, parameters, options, cfd_cfg, context=None):
            captured["omega"] = cfd_cfg.omega
            return {"ok": True, "eta": -0.9, "vcav": 0.0, "dH": -2.4, "P": 1.0, "Q": 1.0}

        monkeypatch.setattr("eigenfrequencies.hydroflow.physics.run_cfd_stage", cfd)
        run_worker(
            tmp_path,
            write_request(tmp_path, options={"eval_mode": "cfd_only", "n_rpm": 120.0}),
        )
        assert captured["omega"] == pytest.approx(2 * 3.141592653589793 * 120.0 / 60.0)


class TestFailurePath:
    def test_a_failed_stage_is_a_result_not_a_crash(self, tmp_path, monkeypatch):
        def explode(*args, **kwargs):
            raise RuntimeError("dtoo export: exit 139 (segfault)")

        monkeypatch.setattr("eigenfrequencies.hydroflow.physics.run_modal_stage", explode)
        result = run_worker(tmp_path, write_request(tmp_path))

        assert result["status"] == "failed"
        assert result["objective"] is None
        assert "segfault" in result["error"]
        assert result["metadata"]["traceback"]
        assert result["candidate_id"] == "island-000-initial-000"

    def test_a_failed_cfd_read_is_reported_with_its_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "eigenfrequencies.hydroflow.physics.run_cfd_stage",
            lambda *a, **kw: {"ok": False, "error": "Pump detected (|eta|>1)"},
        )
        monkeypatch.setattr(
            "eigenfrequencies.hydroflow.physics.run_modal_stage",
            lambda *a, **kw: (list(FREQUENCIES), {"mesh_seconds": 0.1}),
        )
        result = run_worker(tmp_path, write_request(tmp_path))

        assert result["status"] == "failed"
        assert "Pump detected" in result["error"]

    def test_unknown_parameters_are_rejected_before_any_physics(self, tmp_path, stub_stages):
        request = write_request(tmp_path, parameters={"not_a_design_parameter": 1.0})
        result = run_worker(tmp_path, request)

        assert result["status"] == "failed"
        assert "not_a_design_parameter" in result["error"]
        assert stub_stages == {}

    def test_unknown_eval_mode_is_rejected(self, tmp_path, stub_stages):
        result = run_worker(tmp_path, write_request(tmp_path, options={"eval_mode": "guess"}))

        assert result["status"] == "failed"
        assert "unknown eval_mode" in result["error"]

    def test_a_malformed_request_still_produces_a_result(self, tmp_path):
        bad = tmp_path / "request.json"
        bad.write_text("{not json", encoding="utf-8")
        result = run_worker(tmp_path, bad)

        assert result["status"] == "failed"
        assert result["candidate_id"] is None
        assert result["metadata"] == {}

    def test_the_result_directory_is_created_if_missing(self, tmp_path, stub_stages):
        result_path = tmp_path / "nested" / "dir" / "result.json"
        assert (
            worker.main(["--machine", "naca", str(write_request(tmp_path)), str(result_path)]) == 0
        )
        assert json.loads(result_path.read_text())["status"] == "success"
