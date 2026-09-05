"""The physics stages: runtime selection, staleness cleanup, error reporting.

dtOO and OpenFOAM are not available here, so every test that would shell out
stubs the subprocess boundary and asserts on the command that *would* run. The
two behaviours that actually cost a run of the optimizer get the most
attention: that a stale OpenFOAM result can never survive into the next
candidate, and that a failed stage is reported rather than raised past the
worker.
"""

import json
import subprocess
from pathlib import Path

import pytest

from eigenfrequencies.adapters.dtoo.machine_yaml import (
    BCTemplate,
    MachineAdapterConfig,
)
from eigenfrequencies.config import CFDConfig
from eigenfrequencies.hydroflow import physics
from eigenfrequencies.hydroflow.physics import Runtime, StageError


def machine(**overrides) -> MachineAdapterConfig:
    """A machine config with the fields the stages read."""
    kwargs = dict(
        name="naca",
        case_dir="/does/not/exist/naca",
        state="init",
        mech_volume="gridGmsh",
        adjust_plugin="",
        design={},
        bc_template=BCTemplate("foil_clamp"),
    )
    kwargs.update(overrides)
    return MachineAdapterConfig(**kwargs)


class TestRuntimeResolution:
    def test_auto_runs_in_process_when_the_module_is_importable(self):
        runtime = Runtime.resolve(
            {}, probe_module="json", image="i", container="c", setup=(), timeout=1.0
        )
        assert runtime.kind == "inprocess"

    def test_auto_falls_back_to_docker_when_it_is_not(self):
        runtime = Runtime.resolve(
            {},
            probe_module="a_module_that_is_not_installed",
            image="i",
            container="c",
            setup=(),
            timeout=1.0,
        )
        assert runtime.kind == "docker"

    def test_explicit_runtime_wins_over_detection(self):
        runtime = Runtime.resolve(
            {"runtime": "enroot"},
            probe_module="json",
            image="i",
            container="c",
            setup=(),
            timeout=1.0,
        )
        assert runtime.kind == "enroot"

    def test_unknown_runtime_is_rejected(self):
        with pytest.raises(StageError, match="unknown runtime"):
            Runtime.resolve(
                {"runtime": "podman"},
                probe_module="json",
                image="i",
                container="c",
                setup=(),
                timeout=1.0,
            )


class TestRuntimeCommand:
    def test_docker_sources_both_environments_before_the_interpreter(self):
        cmd = Runtime(kind="docker", image="img", setup=physics.DTOO_SETUP).command(
            ["python3.13", "/x/run.py"], workdir="/w"
        )
        script = cmd[-1]
        # Without both, dtOOPythonSWIG fails on libPstream / libTKFeat — the
        # dtOO env.sh alone does not put OpenCASCADE on the library path.
        assert "openfoam2606/etc/bashrc" in script
        assert "/dtOO-install/bin/env.sh" in script
        assert script.index("bashrc") < script.index("python3.13")

    def test_the_solve_does_not_source_openfoam(self):
        """The two stages need different environments. The solve imports nothing
        and only runs OpenFOAM binaries, which the image configures itself —
        sourcing its bashrc on top *strips* the library entries and puts nothing
        back, leaving only lib/dummy. checkMesh then dies on libfiniteVolume.so
        and the stage reports a bare exit 127. Measured with
        cluster/probe_solve_shell.sh."""
        assert physics.CFD_SOLVE_SETUP == ()
        assert any("openfoam" in line for line in physics.DTOO_SETUP)

    def test_the_payload_is_exec(self):
        """Sourcing OpenFOAM's bashrc makes the shell run its command string a
        second time — same PID, sequentially. Every build was done twice until
        exec left no shell behind to repeat it."""
        cmd = Runtime(kind="docker", image="img", setup=physics.DTOO_SETUP).command(
            ["python3.13", "/x/run.py"], workdir="/w"
        )
        assert cmd[-1].rstrip().endswith("exec python3.13 /x/run.py")

    def test_mounts_map_host_paths_onto_themselves(self, tmp_path):
        cmd = Runtime(kind="docker", image="img").command(
            ["true"], workdir=tmp_path, mounts=[tmp_path]
        )
        assert f"{tmp_path.resolve()}:{tmp_path.resolve()}" in cmd

    def test_a_symlinked_mount_keeps_the_name_the_command_line_uses(self, tmp_path):
        """bwUniCluster's $HOME is a symlink (/home/st/<user> →
        /pfs/data6/home/st/<user>). Resolving the mount while argv keeps the
        symlinked spelling mounts one path and asks for another: the build died
        with "can't open file" on a script that was plainly there on the host."""
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real)
        cmd = Runtime(kind="enroot", container="dtOO").command(
            [f"{link}/run.py"], workdir=link, mounts=[link]
        )
        assert f"{link}:{link}" in cmd
        assert not any(str(real) in part for part in cmd)

    def test_missing_mount_sources_are_skipped(self, tmp_path):
        # The dtOO case directory lives inside the image, not on the host.
        cmd = Runtime(kind="docker", image="img").command(
            ["true"], workdir=tmp_path, mounts=[tmp_path / "absent"]
        )
        assert "-v" not in cmd

    def test_enroot_uses_the_container_name_and_changes_directory(self, tmp_path):
        cmd = Runtime(kind="enroot", container="pyxis_dtoo").command(
            ["true"], workdir=tmp_path, mounts=[tmp_path]
        )
        assert cmd[:2] == ["enroot", "start"]
        assert "pyxis_dtoo" in cmd
        assert f"cd {tmp_path.resolve()}" in cmd[-1]

    def test_the_directory_change_comes_after_the_environment_setup(self, tmp_path):
        """A `cd` *before* sourcing OpenFOAM's bashrc sends the container shell
        into an endless re-execution loop: it reprints everything up to the
        source several times a second and never returns, so the stage yields no
        artifact, no log line and no error until its timeout expires. That is
        why no candidate had ever completed on the cluster. Measured with
        cluster/probe_openfoam_cd_order.sh — sourcing both environments first
        and changing directory afterwards finishes in well under a second."""
        for kind, kwargs in (
            ("enroot", {"container": "dtOO"}),
            ("native", {}),
            ("docker", {"image": "img"}),
        ):
            script = (
                Runtime(kind=kind, setup=physics.DTOO_SETUP, **kwargs)
                .command(["true"], workdir=tmp_path)[-1]
            )
            cd = script.index(f"cd {tmp_path.resolve()}")
            assert script.index("/dtOO-install/bin/env.sh") < cd, kind

    def test_enroot_replaces_the_image_command_script(self, monkeypatch, tmp_path):
        """The dtOO image's command script sources OpenFOAM's configuration,
        which eval's the parameters it was handed: quoting is destroyed and
        every command runs twice. `checkMesh` then ran before its environment
        existed, failed on libfiniteVolume.so, and that first run decided the
        exit code."""
        rc = tmp_path / "rc.sh"
        rc.write_text('exec "$@"\n')
        monkeypatch.setenv("EIGENFREQUENCIES_ENROOT_RC", str(rc))
        cmd = Runtime(kind="enroot", container="dtOO").command(["true"], workdir="/w")
        assert cmd[cmd.index("--rc") + 1] == str(rc)
        assert cmd.index("--rc") < cmd.index("dtOO")

    def test_enroot_runs_as_root_by_default(self):
        """Without it enroot cannot drop privileges and refuses to mount at all:
        "mount: drop permissions failed", and the container never starts."""
        cmd = Runtime(kind="enroot", container="/x.sqsh").command(["true"], workdir="/w")
        assert cmd[:3] == ["enroot", "start", "--root"]

    def test_explicit_args_are_not_duplicated(self):
        cmd = Runtime(kind="enroot", container="/x.sqsh", args=("--root",)).command(
            ["true"], workdir="/w"
        )
        assert cmd.count("--root") == 1

    def test_a_variable_in_the_container_path_is_expanded(self, monkeypatch):
        """TOML expands nothing and execve expands nothing, so this has to."""
        monkeypatch.setenv("WS", "/pfs/work9/ws")
        cmd = Runtime(kind="enroot", container="$WS/enroot-images/dtOO.sqsh").command(
            ["true"], workdir="/w"
        )
        assert "/pfs/work9/ws/enroot-images/dtOO.sqsh" in cmd

    def test_a_tilde_in_the_container_path_is_expanded(self):
        """Nothing between here and execve expands it, and enroot then reports
        a container it cannot find — from a config line that looks correct."""
        cmd = Runtime(kind="enroot", container="~/enroot-images/x.sqsh").command(
            ["true"], workdir="/w"
        )
        assert not any(a.startswith("~") for a in cmd)
        assert any(a.endswith("/enroot-images/x.sqsh") for a in cmd)

    def test_environment_is_exported_inside_the_shell(self):
        cmd = Runtime(kind="native").command(
            ["true"], workdir="/w", env={"DTOO_CASE_DIR": "/a b"}
        )
        assert "export DTOO_CASE_DIR='/a b'" in cmd[-1]

    def test_in_process_runtime_has_no_command(self):
        with pytest.raises(StageError, match="no shell command"):
            Runtime(kind="inprocess").command(["true"], workdir="/w")


class TestWorkDir:
    def test_prefers_the_candidate_scratch_dir(self, tmp_path):
        scratch = tmp_path / "island-000-initial-000"
        assert physics.work_dir({}, {"scratch_dir": str(scratch)}) == scratch
        assert scratch.is_dir()

    def test_local_scratch_keeps_the_candidate_id(self, tmp_path):
        """Heavy artifacts go node-local, the orchestrator's path stays put.

        That path is part of the request, and the request is the cache key that
        lets `resume` reuse a finished evaluation. Redirecting it per job would
        make every resumed run recompute everything.
        """
        chosen = physics.work_dir(
            {"local_scratch": str(tmp_path / "nvme")},
            {"scratch_dir": "/pfs/ws/runs/x/scratch/island-000-trial-007"},
        )
        assert chosen == tmp_path / "nvme" / "island-000-trial-007"

    def test_explicit_option_overrides_the_context(self, tmp_path):
        chosen = physics.work_dir(
            {"work_dir": str(tmp_path / "here")}, {"scratch_dir": str(tmp_path / "there")}
        )
        assert chosen == tmp_path / "here"


class TestCaseDirResolution:
    def test_container_falls_back_to_the_image_path(self):
        runtime = Runtime(kind="docker")
        assert physics._case_dir(machine(), {}, runtime) == "/dtOO/build/test/naca"

    def test_host_path_is_kept_when_it_exists(self, tmp_path):
        cfg = machine(case_dir=str(tmp_path))
        assert physics._case_dir(cfg, {}, Runtime(kind="docker")) == str(tmp_path)

    def test_option_overrides_everything(self):
        chosen = physics._case_dir(
            machine(), {"case_dir": "/opt/cases/naca"}, Runtime(kind="docker")
        )
        assert chosen == "/opt/cases/naca"


class TestExportMesh:
    def test_container_run_writes_a_spec_and_returns_the_mesh(self, tmp_path, monkeypatch):
        recorded = {}

        def fake_run(cmd, **kwargs):
            recorded["cmd"] = cmd
            # The container writes the mesh; stand in for it.
            (tmp_path / "mesh" / "naca.msh").write_text("mesh", encoding="utf-8")
            return ""

        monkeypatch.setattr(physics, "_run", fake_run)
        msh, meta = export_with(tmp_path, {"dtoo": {"runtime": "docker"}})

        spec = json.loads((tmp_path / "mesh" / "dtoo_spec.json").read_text())
        assert spec["design"] == {"cV_bladeLength": 1.0}
        assert spec["state"] == "init"
        assert spec["output_msh"] == msh
        assert "dtoo-export" in recorded["cmd"][-1]
        assert meta["runtime"] == "docker"

    def test_a_stale_mesh_is_removed_before_the_build(self, tmp_path, monkeypatch):
        stale = tmp_path / "mesh" / "naca.msh"
        stale.parent.mkdir(parents=True)
        stale.write_text("previous candidate", encoding="utf-8")

        monkeypatch.setattr(physics, "_run", lambda cmd, **kw: "")
        with pytest.raises(StageError, match="no mesh at"):
            export_with(tmp_path, {"dtoo": {"runtime": "docker"}})
        assert not stale.exists()

    def test_the_dtoo_trace_is_dropped_after_a_successful_export(self, tmp_path, monkeypatch):
        """It is ~39 MB per tistos candidate — twice the mesh it produced."""

        def fake_run(cmd, **kwargs):
            mesh = tmp_path / "mesh"
            (mesh / "naca.msh").write_text("mesh", encoding="utf-8")
            (mesh / "dtoo_build.log").write_text("x" * 4096, encoding="utf-8")
            return ""

        monkeypatch.setattr(physics, "_run", fake_run)
        _, meta = export_with(tmp_path, {"dtoo": {"runtime": "docker"}})

        assert not (tmp_path / "mesh" / "dtoo_build.log").exists()
        assert meta["dtoo_log_bytes"] == 4096, "its size is still reported"

    def test_the_trace_is_kept_on_request(self, tmp_path, monkeypatch):
        def fake_run(cmd, **kwargs):
            mesh = tmp_path / "mesh"
            (mesh / "naca.msh").write_text("mesh", encoding="utf-8")
            (mesh / "dtoo_build.log").write_text("trace", encoding="utf-8")
            return ""

        monkeypatch.setattr(physics, "_run", fake_run)
        export_with(tmp_path, {"dtoo": {"runtime": "docker", "keep_build_log": True}})
        assert (tmp_path / "mesh" / "dtoo_build.log").exists()

    def test_the_trace_survives_a_failed_export(self, tmp_path, monkeypatch):
        """The one log worth reading is the one from the export that broke."""

        def fake_run(cmd, **kwargs):
            (tmp_path / "mesh" / "dtoo_build.log").write_text("segfault", encoding="utf-8")
            return ""

        monkeypatch.setattr(physics, "_run", fake_run)
        with pytest.raises(StageError, match="no mesh at"):
            export_with(tmp_path, {"dtoo": {"runtime": "docker"}})
        assert (tmp_path / "mesh" / "dtoo_build.log").read_text() == "segfault"

    def test_dtoo_failure_becomes_a_stage_error(self, tmp_path, monkeypatch):
        def fail(cmd, **kwargs):
            raise StageError("dtoo export: exit 1\nsegfault")

        monkeypatch.setattr(physics, "_run", fail)
        with pytest.raises(StageError, match="segfault"):
            export_with(tmp_path, {"dtoo": {"runtime": "docker"}})


def export_with(tmp_path: Path, options: dict):
    return physics.export_mesh(
        machine(), {"cV_bladeLength": 1.0}, options, tmp_path
    )


class TestModalRuntimeExtras:
    """Mounts and PYTHONPATH, which is what lets the stock dolfinx image serve.

    The published dolfinx image has no gmsh, so the modal stage could not read a
    mesh in it. A `pip install --target` directory mounted from the host supplies
    it in 17 MB, and then nothing has to be built, pushed or copied to reach the
    cluster.
    """

    def _capture(self, tmp_path, monkeypatch, options):
        seen = {}

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            return physics.RESULT_MARKER + '{"ok": true, "frequencies_hz": [1.0]}'

        monkeypatch.setattr(physics, "_run", fake_run)
        physics.solve_modal(str(tmp_path / "m.msh"), machine(), options, tmp_path)
        return seen["cmd"]

    def test_pythonpath_is_appended_never_assigned(self, tmp_path, monkeypatch):
        """Assigning it hides the image's own dolfinx and breaks the import."""
        cmd = self._capture(
            tmp_path,
            monkeypatch,
            {"modal": {"runtime": "docker", "pythonpath": ["/opt/pylibs"]}},
        )
        script = cmd[-1]
        assert "export PYTHONPATH=/opt/pylibs:$PYTHONPATH" in script

    def test_the_pythonpath_directory_is_mounted(self, tmp_path, monkeypatch):
        libs = tmp_path / "pylibs"
        libs.mkdir()
        cmd = self._capture(
            tmp_path,
            monkeypatch,
            {"modal": {"runtime": "docker", "pythonpath": [str(libs)]}},
        )
        assert f"{libs}:{libs}" in cmd

    def test_extra_mounts_are_passed_through(self, tmp_path, monkeypatch):
        extra = tmp_path / "shared"
        extra.mkdir()
        cmd = self._capture(
            tmp_path,
            monkeypatch,
            {"modal": {"runtime": "docker", "mounts": [str(extra)]}},
        )
        assert f"{extra}:{extra}" in cmd


class TestStaleResultCleanup:
    """The frozen-CFD guard: simpleFoam skips the solve if endTime exists."""

    def test_time_steps_and_post_processing_are_removed(self, tmp_path):
        for name in ("0", "100", "500", "postProcessing", "constant", "system"):
            (tmp_path / name).mkdir()
        removed = physics._clear_stale_results(tmp_path)

        assert sorted(removed) == ["100", "500", "postProcessing"]
        assert (tmp_path / "0").is_dir(), "initial conditions must survive"
        assert (tmp_path / "constant").is_dir()
        assert (tmp_path / "system").is_dir()

    def test_a_leftover_decomposition_is_removed(self, tmp_path):
        """decomposePar aborts on one — or silently reuses the wrong mesh.

        The solve script deletes processor* on its way out, so a leftover only
        exists after a run that did not finish. Observed for real: "Case is
        already decomposed with 2 domains", exit 1, before simpleFoam ever ran.
        """
        for name in ("processors2", "processor0", "processor1", "constant"):
            (tmp_path / name).mkdir()
        removed = physics._clear_stale_results(tmp_path)

        assert sorted(removed) == ["processor0", "processor1", "processors2"]
        assert (tmp_path / "constant").is_dir()

    def test_fractional_time_directories_are_removed_too(self, tmp_path):
        (tmp_path / "0.5").mkdir()
        assert physics._clear_stale_results(tmp_path) == ["0.5"]

    def test_nothing_to_clear_is_not_an_error(self, tmp_path):
        assert physics._clear_stale_results(tmp_path / "absent") == []


class TestCfdProcs:
    def test_uses_the_orchestrator_rank_budget(self):
        assert physics._cfd_procs({}, {"resources": {"mpi_ranks": 4}}) == 4

    def test_option_overrides_the_context(self):
        assert physics._cfd_procs({"procs": 2}, {"resources": {"mpi_ranks": 4}}) == 2

    def test_falls_back_to_slurm_then_to_one(self, monkeypatch):
        monkeypatch.delenv("SLURM_CPUS_PER_TASK", raising=False)
        assert physics._cfd_procs({}, None) == 1
        monkeypatch.setenv("SLURM_CPUS_PER_TASK", "8")
        assert physics._cfd_procs({}, {}) == 8


class TestRunCfdStage:
    def test_a_failed_build_is_reported_not_raised(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            physics,
            "build_cfd_case",
            lambda *a, **kw: (_ for _ in ()).throw(StageError("cfd build: exit 1")),
        )
        result = physics.run_cfd_stage(
            machine(), {}, {"work_dir": str(tmp_path)}, CFDConfig(n_rpm=72.0)
        )
        assert result["ok"] is False
        assert "cfd build" in result["error"]
        # Same shape as a reader failure, so the worker has one failure path.
        assert result["eta"] == result["vcav"] == result["dH"] == 0.0

    def test_solve_metadata_is_merged_into_the_reader_result(self, tmp_path, monkeypatch):
        case_dir = tmp_path / "tistos_ru_of_n_hydroflow"
        case_dir.mkdir()
        monkeypatch.setattr(physics, "build_cfd_case", lambda *a, **kw: case_dir)
        monkeypatch.setattr(
            physics, "solve_cfd", lambda *a, **kw: {"mpi_ranks": 3, "cleared_artifacts": ["500"]}
        )
        monkeypatch.setattr(
            "eigenfrequencies.io.cfd_eval.evaluate_cfd",
            lambda d, cfg: {"ok": True, "eta": -0.9, "vcav": 0.0, "dH": -2.4, "P": 1.0, "Q": 1.0},
        )
        result = physics.run_cfd_stage(
            machine(), {}, {"work_dir": str(tmp_path)}, CFDConfig(n_rpm=72.0)
        )
        assert result["ok"] is True
        assert result["mpi_ranks"] == 3
        assert result["cleared_artifacts"] == ["500"]
        assert result["work_dir"] == str(tmp_path)


class TestSolveCfd:
    def test_the_case_is_cleaned_before_the_solver_starts(self, tmp_path, monkeypatch):
        directory = tmp_path
        (directory / "tistos_files").mkdir(parents=True)
        (directory / "tistos_files" / "sbatch.tistos_ru_of.sh").write_text("#!/bin/sh\n")
        case_dir = directory / "case"
        (case_dir / "500").mkdir(parents=True)
        (case_dir / "postProcessing").mkdir()

        order = []

        def fake_run(cmd, **kwargs):
            order.append(sorted(p.name for p in case_dir.iterdir()))
            return ""

        monkeypatch.setattr(physics, "_run", fake_run)
        meta = physics.solve_cfd(
            case_dir, {"dtoo": {"runtime": "native"}, "cfd": {"procs": 2}}, directory
        )
        assert order == [[]], "solver must start on a case with no results in it"
        assert sorted(meta["cleared_artifacts"]) == ["500", "postProcessing"]
        assert meta["mpi_ranks"] == 2

    def test_a_missing_solve_script_is_a_stage_error(self, tmp_path):
        with pytest.raises(StageError, match="solve script not found"):
            physics.solve_cfd(tmp_path, {"dtoo": {"runtime": "native"}}, tmp_path)


class TestRunHelper:
    def test_timeout_is_reported_with_the_stage_name(self, tmp_path, monkeypatch):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=1.0, output="partial")

        monkeypatch.setattr(subprocess, "run", timeout)
        with pytest.raises(StageError, match="cfd solve: timed out"):
            physics._run(
                ["sleep", "2"], stage="cfd solve", timeout=1.0, log_path=tmp_path / "l.log"
            )
        # The command line heads every stage log, a timed-out one included.
        log = (tmp_path / "l.log").read_text()
        assert log.startswith("$ sleep 2\n")
        assert log.endswith("partial")

    def test_the_log_and_the_error_both_name_the_command(self, tmp_path):
        """A failing container stage often produces no output whatsoever, and
        "exit 127" on its own is not actionable. The command is assembled from a
        config, a machine YAML, a runtime and three mount lists — reconstructing
        it by hand costs an allocation."""
        with pytest.raises(StageError, match=r"command: sh -c 'exit 127'"):
            physics._run(
                ["sh", "-c", "exit 127"],
                stage="cfd solve",
                timeout=10.0,
                log_path=tmp_path / "l.log",
            )
        assert (tmp_path / "l.log").read_text().startswith("$ sh -c 'exit 127'\n")

    def test_a_non_zero_exit_carries_the_log_tail(self, tmp_path):
        with pytest.raises(StageError, match="boom"):
            physics._run(
                ["sh", "-c", "echo boom; exit 3"],
                stage="cfd build",
                timeout=30.0,
                log_path=tmp_path / "l.log",
            )
        assert "boom" in (tmp_path / "l.log").read_text()

    def test_output_is_returned_and_logged_on_success(self, tmp_path):
        out = physics._run(
            ["sh", "-c", "echo CFD_CASE_DIR /x"],
            stage="cfd build",
            timeout=30.0,
            log_path=tmp_path / "l.log",
        )
        assert "CFD_CASE_DIR /x" in out

    def test_missing_result_line_is_a_stage_error(self):
        with pytest.raises(StageError, match="no RESULT_JSON line"):
            physics._parse_result_line("nothing here\n", stage="modal solve")


class TestEntryPoint:
    def test_modal_failure_is_reported_on_the_result_line(self, tmp_path, capsys):
        spec = tmp_path / "spec.json"
        spec.write_text(json.dumps({"msh_path": str(tmp_path / "absent.msh")}))

        assert physics.main(["modal", str(spec)]) == 1
        payload = physics._parse_result_line(capsys.readouterr().out, stage="modal solve")
        assert payload["ok"] is False
        assert payload["error"]

    def test_usage_error_without_a_stage(self):
        assert physics.main([]) == 2
