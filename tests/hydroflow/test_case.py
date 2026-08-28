"""The machine case plugin against the hydroflow-opt contract."""

import sys

import pytest

pytest.importorskip("hydroflow_opt", reason="requires the [hydroflow] extra")

from eigenfrequencies.hydroflow.case import (  # noqa: E402
    MachineCasePlugin,
    NacaCase,
    TistosCase,
    machines_dir,
)


class TestParameterSpace:
    def test_tistos_exposes_all_thirty_design_parameters(self):
        space = TistosCase().parameter_space({})
        assert len(space.names) == 30
        assert len(space.lower_bounds) == len(space.upper_bounds) == 30

    def test_bounds_match_the_machine_yaml(self):
        space = TistosCase().parameter_space({})
        idx = space.names.index("cV_ru_alpha_1_ex_0.0")
        assert space.lower_bounds[idx] == pytest.approx(-0.155)
        assert space.upper_bounds[idx] == pytest.approx(0.025)

    def test_naca_uses_the_same_class(self):
        space = NacaCase().parameter_space({})
        assert isinstance(NacaCase(), MachineCasePlugin)
        assert len(space.names) > 0

    def test_subset_selection_preserves_order(self):
        names = ["cV_ru_ratio_1.0", "cV_ru_alpha_1_ex_0.0"]
        space = TistosCase().parameter_space({"parameters": names})
        assert space.names == tuple(names)

    def test_unknown_parameter_is_rejected(self):
        with pytest.raises(ValueError, match="no design parameter"):
            TistosCase().parameter_space({"parameters": ["not_a_parameter"]})

    def test_explicit_yaml_overrides_the_catalog(self):
        path = machines_dir() / "naca.yaml"
        space = MachineCasePlugin("tistos").parameter_space({"machine_yaml": str(path)})
        assert space.names == NacaCase().parameter_space({}).names

    def test_missing_machine_reports_the_path(self, monkeypatch):
        monkeypatch.setenv("EIGENFREQUENCIES_MACHINES_DIR", "/nonexistent")
        with pytest.raises(FileNotFoundError, match="machine catalog entry not found"):
            MachineCasePlugin("tistos").parameter_space({})


class TestWorkerCommand:
    def test_goes_through_the_interpreter_with_positional_paths(self, tmp_path):
        req, res = tmp_path / "request.json", tmp_path / "result.json"
        cmd = TistosCase().worker_command(req, res)
        assert cmd[0] == sys.executable
        assert cmd[1:4] == ["-m", "eigenfrequencies.hydroflow.worker", "--machine"]
        assert cmd[4] == "tistos"
        # REQUEST and RESULT stay the trailing positional pair.
        assert cmd[-2:] == [str(req), str(res)]


class TestDiscovery:
    def test_case_from_name_finds_the_registered_cases(self):
        from hydroflow_opt.cases import case_from_name

        for name, expected in (("tistos", 30),):
            plugin = case_from_name(name)
            assert len(plugin.parameter_space({}).names) == expected
