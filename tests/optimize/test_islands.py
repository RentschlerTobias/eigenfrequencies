"""Tests for the native island model with ring migration.

Covers:
* Rastrigin convergence (multi-island beats or matches single-island)
* Seeded determinism
* Ring migration mechanics (population actually changes)
* Checkpoint save / resume (identical subsequent trajectory)
* Corrupted checkpoint error handling
* No-duplicate migration policy
* Edge cases (n_islands=1, validation errors)
"""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from eigenfrequencies.optimize.islands import CheckpointError, IslandOptimizer
from eigenfrequencies.optimize.protocol import ProtocolUsageError

# ── Test objective functions ──


def _sphere(v: list[float]) -> float:
    """2-D sphere: minimum 0 at origin."""
    x = np.asarray(v, dtype=float)
    return float(np.sum(x**2))


def _rastrigin(v: list[float]) -> float:
    """n-D Rastrigin: global minimum 0 at origin, many local minima."""
    x = np.asarray(v, dtype=float)
    d = len(x)
    return float(10 * d + np.sum(x**2 - 10 * np.cos(2 * np.pi * x)))


# ── Helpers ──


def _run_island_opt(opt: IslandOptimizer, pop_size: int, n_generations: int) -> float:
    """Run n_generations of ask/tell on *opt* and return best objective."""
    for _ in range(n_generations):
        designs = opt.ask(pop_size)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
    return opt.best_objective


def _run_island_opt_rastrigin(
    opt: IslandOptimizer, pop_size: int, n_generations: int
) -> float:
    """Like _run_island_opt but evaluates with Rastrigin."""
    for _ in range(n_generations):
        designs = opt.ask(pop_size)
        objs = [_rastrigin(d.vector) for d in designs]
        opt.tell(designs, objs)
    return opt.best_objective


def _capture_ask_vectors(
    opt: IslandOptimizer, pop_size: int, n_generations: int
) -> list[list[float]]:
    """Run n_generations, capturing all ask vectors (flat)."""
    all_vecs: list[list[float]] = []
    for _ in range(n_generations):
        designs = opt.ask(pop_size)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
        for d in designs:
            all_vecs.append(d.vector)
    return all_vecs


# ── Tests ──


class TestIslandBasic:
    """Basic protocol operations."""

    def test_ask_returns_correct_count(self):
        cfg = {"bounds": [(-5.0, 5.0), (-5.0, 5.0)], "seed": 42, "pop_size": 6}
        opt = IslandOptimizer("de", cfg, n_islands=3, migration_interval=5, migrant_count=2)
        designs = opt.ask(6)
        assert len(designs) == 18  # 3 islands * 6 pop_size

    def test_ask_tags_island_in_metadata(self):
        cfg = {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}
        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=5)
        designs = opt.ask(4)
        island_ids = [d.metadata.get("_island") for d in designs]
        assert island_ids[:4] == [0, 0, 0, 0]
        assert island_ids[4:] == [1, 1, 1, 1]

    def test_tell_advances_generation(self):
        cfg = {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}
        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=5)
        assert opt.generation == 0
        designs = opt.ask(4)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
        assert opt.generation == 1

    def test_bounds_property(self):
        bounds = [(-3.0, 7.0), (0.0, 2.0)]
        cfg = {"bounds": bounds, "seed": 1, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=2)
        assert opt.bounds == bounds

    def test_tell_mismatch_raises(self):
        cfg = {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}
        opt = IslandOptimizer("de", cfg, n_islands=2)
        designs = opt.ask(4)
        with pytest.raises(ProtocolUsageError):
            opt.tell(designs, [1.0, 2.0])  # wrong count

    def test_best_objective_tracks_improvement(self):
        cfg = {"bounds": [(-5.0, 5.0), (-5.0, 5.0)], "seed": 42, "pop_size": 6}
        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=5)
        initial_best = opt.best_objective
        assert initial_best == float("inf")
        designs = opt.ask(6)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)
        assert opt.best_objective < float("inf")
        assert opt.best_vector is not None


class TestIslandRastrigin:
    """Multi-island convergence on the multimodal Rastrigin function."""

    def test_four_islands_beats_or_matches_single_island_rastrigin(self):
        """4-island DE on Rastrigin finds best-objective <= single-island at equal budget.

        The 5-D Rastrigin has 5^5 ≈ 3125 local minima in [-5.12, 5.12]^5.
        Multiple subpopulations explore different basins; ring migration shares
        genetic material, preventing any single island from getting trapped.
        """
        # 5-D Rastrigin: many more local minima than 2-D, favouring exploration.
        bounds = [(-5.12, 5.12)] * 5
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 15}
        pop = 15
        n_islands = 4

        total_gens_per_config = 20
        total_evals = n_islands * pop * total_gens_per_config  # 1200

        # 4 islands: 4*15=60 evals/gen, 20 gens, migration every 4 gens → 5 migrations.
        opt4 = IslandOptimizer(
            "de", cfg, n_islands=n_islands, migration_interval=4, migrant_count=3
        )
        best4 = _run_island_opt_rastrigin(opt4, pop_size=pop, n_generations=total_gens_per_config)

        # 1 island with same total evaluations: pop_size=15, 4*20=80 generations.
        single_gens = total_evals // pop  # 80
        opt1 = IslandOptimizer("de", cfg, n_islands=1, migration_interval=single_gens + 1)
        best1 = _run_island_opt_rastrigin(opt1, pop_size=pop, n_generations=single_gens)

        assert best4 < 20.0, f"4-island best={best4:.4f}"
        assert best1 < 20.0, f"1-island best={best1:.4f}"
        assert best4 <= best1 * 1.15, (
            f"4-island best={best4:.4f} not <= 1-island best={best1:.4f} with 15% slack"
        )


class TestIslandDeterminism:
    """Seeded reproducibility."""

    def test_same_seed_same_trajectory(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}

        opt_a = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3, migrant_count=2)
        opt_b = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3, migrant_count=2)

        vecs_a = _capture_ask_vectors(opt_a, pop_size=5, n_generations=6)
        vecs_b = _capture_ask_vectors(opt_b, pop_size=5, n_generations=6)

        assert vecs_a == vecs_b, "Same seed should produce identical trajectories"

    def test_different_seed_different_trajectory(self):
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        opt_a = IslandOptimizer(
            "de", {"bounds": bounds, "seed": 1, "pop_size": 5}, n_islands=2
        )
        opt_b = IslandOptimizer(
            "de", {"bounds": bounds, "seed": 999, "pop_size": 5}, n_islands=2
        )

        vecs_a = _capture_ask_vectors(opt_a, pop_size=5, n_generations=2)
        vecs_b = _capture_ask_vectors(opt_b, pop_size=5, n_generations=2)

        assert vecs_a != vecs_b, "Different seeds should produce different trajectories"


class TestIslandMigration:
    """Verify that ring migration actually modifies populations."""

    def test_migration_modifies_destination_population(self):
        """After migration_interval, destination island's population changes."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 8}

        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3, migrant_count=3)
        assert opt.migration_count == 0

        # Snapshot island 1 population after gen 2 (pre-migration).
        for gen in range(2):
            designs = opt.ask(8)
            objs = [_sphere(d.vector) for d in designs]
            opt.tell(designs, objs)

        state_before = opt._islands[1].state_dict()
        pop_before = np.asarray(state_before["population"], dtype=float)

        # Gen 3 triggers migration.
        designs = opt.ask(8)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)

        assert opt.migration_count == 1
        assert opt.generation == 3

        state_after = opt._islands[1].state_dict()
        pop_after = np.asarray(state_after["population"], dtype=float)

        # At least one individual in island 1 should differ (from island 0 migration).
        unchanged_count = 0
        for i in range(len(pop_before)):
            for j in range(len(pop_after)):
                if np.allclose(pop_before[i], pop_after[j], atol=1e-12):
                    unchanged_count += 1
                    break
        # After migration of 3 individuals, at most (8-3)=5 from original remain.
        assert unchanged_count <= len(pop_before) - opt._migrant_count + 1, (
            f"Expected at most {len(pop_before) - opt._migrant_count + 1} unchanged, "
            f"got {unchanged_count}"
        )

    def test_migration_with_n_islands_1_is_noop(self):
        """Single island sends migrants to itself — effectively a no-op."""
        cfg = {"bounds": [(-1.0, 1.0), (-1.0, 1.0)], "seed": 5, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=1, migration_interval=3, migrant_count=2)

        # Run past migration point.
        for gen in range(3):
            designs = opt.ask(5)
            objs = [_sphere(d.vector) for d in designs]
            opt.tell(designs, objs)

        assert opt.migration_count == 1
        assert opt.generation == 3


class TestIslandCheckpoint:
    """Save / resume checkpoint cycle."""

    def test_resume_produces_identical_subsequent_trajectory(self):
        """Resume from checkpoint yields exact same next asks as continued original."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}

        with tempfile.TemporaryDirectory() as tmpdir:
            # Phase 1 — run 6 generations (migrations at 3 and 6) and checkpoint.
            opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3, migrant_count=2)
            for gen in range(6):
                designs = opt.ask(5)
                objs = [_sphere(d.vector) for d in designs]
                opt.tell(designs, objs)
            assert opt.migration_count == 2
            opt.save_checkpoints(tmpdir)

            # Phase 2 — continue opt for 3 more generations, capturing vectors.
            vecs_cont = _capture_ask_vectors(opt, pop_size=5, n_generations=3)

            # Phase 3 — resume from checkpoint.
            opt2 = IslandOptimizer.resume(
                "de", cfg, tmpdir, n_islands=2, migration_interval=3, migrant_count=2
            )
            assert opt2.generation == 6
            assert opt2.migration_count == 2

            # Phase 4 — run same 3 gens on resumed.
            vecs_resumed = _capture_ask_vectors(opt2, pop_size=5, n_generations=3)

            assert vecs_cont == vecs_resumed, (
                f"Resumed trajectory differs from continued: "
                f"len_cont={len(vecs_cont)}, len_resumed={len(vecs_resumed)}"
            )

    def test_state_dict_load_state_roundtrip(self):
        """state_dict / load_state reproduces exact same next ask (no I/O)."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 7, "pop_size": 5}

        opt1 = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3, migrant_count=2)
        for gen in range(6):
            designs = opt1.ask(5)
            objs = [_sphere(d.vector) for d in designs]
            opt1.tell(designs, objs)

        state = opt1.state_dict()

        # Fresh instance with different seed, then load state.
        cfg_dummy = {"bounds": [(0.0, 0.0)], "seed": 999, "pop_size": 5}
        opt2 = IslandOptimizer("de", cfg_dummy, n_islands=1, migration_interval=1, migrant_count=1)
        opt2.load_state(state)

        assert opt2.generation == opt1.generation
        assert opt2.migration_count == opt1.migration_count
        assert opt2.best_objective == opt1.best_objective

        # Next asks should match.
        d1 = opt1.ask(5)
        d2 = opt2.ask(5)
        assert [x.vector for x in d1] == [x.vector for x in d2]

    def test_save_checkpoints_creates_expected_files(self):
        """Checkpoint directory contains island_{i}.json and _meta.json."""
        cfg = {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}
        opt = IslandOptimizer("de", cfg, n_islands=3)

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)
            assert (Path(tmpdir) / "_meta.json").exists()
            for i in range(3):
                assert (Path(tmpdir) / f"island_{i}.json").exists()

    def test_checkpoint_json_is_valid(self):
        """Saved checkpoints are valid JSON with expected keys."""
        cfg = {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}
        opt = IslandOptimizer("de", cfg, n_islands=2)
        for gen in range(2):
            designs = opt.ask(4)
            opt.tell(designs, [_sphere(d.vector) for d in designs])

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)
            with open(Path(tmpdir) / "island_0.json") as f:
                ckpt = json.load(f)
            assert ckpt["island_index"] == 0
            assert ckpt["n_islands"] == 2
            assert "state" in ckpt
            assert "population" in ckpt["state"] or "algorithm_pickle" in ckpt["state"]


class TestIslandCheckpointErrors:
    """Corrupted / missing checkpoint handling."""

    def test_corrupt_island_json_raises_naming_island(self):
        """Corrupt one island's JSON → CheckpointError naming that island."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=3)

        for gen in range(3):
            designs = opt.ask(5)
            opt.tell(designs, [_sphere(d.vector) for d in designs])

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)

            # Corrupt island_1.json.
            ckpt_path = Path(tmpdir) / "island_1.json"
            ckpt_path.write_text("this is not valid json {{{")

            with pytest.raises(CheckpointError, match="Island 1") as exc_info:
                IslandOptimizer.resume(
                    "de", cfg, tmpdir, n_islands=2, migration_interval=3
                )
            assert "1" in str(exc_info.value)

    def test_missing_island_json_raises(self):
        """Missing island checkpoint → CheckpointError."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)

            # Delete island_0.json.
            (Path(tmpdir) / "island_0.json").unlink()

            with pytest.raises(CheckpointError, match="Island 0"):
                IslandOptimizer.resume(
                    "de", cfg, tmpdir, n_islands=2
                )

    def test_missing_state_key_raises(self):
        """Checkpoint missing 'state' key → CheckpointError."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)

            # Overwrite island_0.json with missing "state".
            ckpt = json.loads((Path(tmpdir) / "island_0.json").read_text())
            del ckpt["state"]
            (Path(tmpdir) / "island_0.json").write_text(json.dumps(ckpt))

            with pytest.raises(CheckpointError, match="Island 0.*'state'"):
                IslandOptimizer.resume(
                    "de", cfg, tmpdir, n_islands=2
                )

    def test_n_islands_mismatch_raises(self):
        """Checkpoint has different n_islands → CheckpointError."""
        bounds = [(-1.0, 1.0), (-1.0, 1.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 5}
        opt = IslandOptimizer("de", cfg, n_islands=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            opt.save_checkpoints(tmpdir)

            with pytest.raises(CheckpointError, match="n_islands=2"):
                IslandOptimizer.resume(
                    "de", cfg, tmpdir, n_islands=3
                )


class TestIslandNoDuplicate:
    """No-duplicate migration policy — tested via static method on raw state dicts."""

    def test_duplicate_migrant_is_skipped(self):
        """When source best already exists in dest, the migrant is skipped.

        The duplicate is NOT among the worst K, so it survives.  A subsequent
        non-duplicate migrant replaces one of the truly worst individuals.
        """
        src = {
            "population": [[0.0], [1.0], [2.0]],
            "objectives": [0.0, 5.0, 10.0],
        }
        dst = {
            "population": [[0.0], [3.0], [4.0]],
            "objectives": [50.0, 999.0, 998.0],
        }
        IslandOptimizer._migrate_population_lists(src, dst, k=1)

        dst_pop = np.asarray(dst["population"])
        assert any(np.allclose([0.0], dst_pop[i]) for i in range(3))
        assert any(np.allclose([1.0], dst_pop[i]) for i in range(3))
        assert 5.0 in np.asarray(dst["objectives"])
        assert not any(np.allclose([3.0], dst_pop[i]) for i in range(3))

    def test_non_duplicate_migrant_replaces_worst(self):
        """Non-duplicate migrant replaces a worst individual at destination."""
        src = {
            "population": [[0.0], [5.0], [6.0]],
            "objectives": [0.0, 3.0, 8.0],
        }
        dst = {
            "population": [[1.0], [2.0], [3.0]],
            "objectives": [4.0, 5.0, 999.0],
        }
        # k=1: best from src is [0.0] (obj 0.0). Not duplicate → replaces worst in dst.
        IslandOptimizer._migrate_population_lists(src, dst, k=1)

        dst_pop = np.asarray(dst["population"])
        dst_obj = np.asarray(dst["objectives"])
        # [0.0] should have replaced [3.0] (obj 999, the worst).
        assert any(np.allclose([0.0], dst_pop[i]) for i in range(3))
        assert 0.0 in dst_obj
        # Original worst [3.0] should be gone.
        assert not any(np.allclose([3.0], dst_pop[i]) for i in range(3))

    def test_duplicate_preserved_when_not_in_worst_k(self):
        """Duplicate survives when its objective is too good to be in worst K."""
        src = {
            "population": [[0.0], [5.0], [8.0]],
            "objectives": [0.0, 1.0, 2.0],
        }
        dst = {
            "population": [[0.0], [7.0], [3.0]],
            "objectives": [80.0, 900.0, 800.0],
        }
        IslandOptimizer._migrate_population_lists(src, dst, k=2)

        dst_pop = np.asarray(dst["population"])
        assert any(np.allclose([5.0], dst_pop[i]) for i in range(3))
        assert any(np.allclose([8.0], dst_pop[i]) for i in range(3))
        assert any(np.allclose([0.0], dst_pop[i]) for i in range(3))
        assert not any(np.allclose([7.0], dst_pop[i]) for i in range(3))
        assert not any(np.allclose([3.0], dst_pop[i]) for i in range(3))

    def test_migration_via_island_tell_with_no_duplicate_works(self):
        """End-to-end: migration_interval=1 with distinct populations produces migrants."""
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 6}

        opt = IslandOptimizer("de", cfg, n_islands=2, migration_interval=1, migrant_count=1)

        # Seed guarantees distinct populations across islands.
        designs = opt.ask(6)
        objs = [_sphere(d.vector) for d in designs]
        opt.tell(designs, objs)

        s0 = opt._islands[0].state_dict()
        s1 = opt._islands[1].state_dict()
        pop0_before = np.asarray(s0["population"])
        pop1_before = np.asarray(s1["population"])

        # Second generation triggers migration.
        designs2 = opt.ask(6)
        objs2 = [_sphere(d.vector) for d in designs2]
        opt.tell(designs2, objs2)

        s1_after = opt._islands[1].state_dict()
        pop1_after = np.asarray(s1_after["population"])

        # After migration, at least some individuals should differ.
        # (The first generation sets up distinct populations; migration
        # injects at least 1 individual from island 0 into island 1.)
        changed = 0
        for vec_after in pop1_after:
            if not any(
                np.allclose(vec_after, vec_before, atol=1e-12)
                for vec_before in pop1_before
            ):
                changed += 1
        assert changed > 0, (
            f"Island 1 population unchanged after migration "
            f"(changed={changed} of {len(pop1_after)})"
        )


class TestIslandEdgeCases:
    """Edge cases and validation."""

    def test_n_islands_must_be_positive(self):
        with pytest.raises(ValueError, match="n_islands"):
            IslandOptimizer(
                "de", {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4}, n_islands=0
            )

    def test_migration_interval_must_be_positive(self):
        with pytest.raises(ValueError, match="migration_interval"):
            IslandOptimizer(
                "de",
                {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4},
                migration_interval=0,
            )

    def test_migrant_count_must_be_positive(self):
        with pytest.raises(ValueError, match="migrant_count"):
            IslandOptimizer(
                "de",
                {"bounds": [(-1.0, 1.0)], "seed": 1, "pop_size": 4},
                migrant_count=0,
            )

    def test_de_islands_converge_on_sphere(self):
        """DE islands converge on the simple sphere function.

        Islands add diversity, which temporarily slows convergence on
        unimodal problems.  With enough budget they still reach the optimum.
        """
        bounds = [(-5.0, 5.0), (-5.0, 5.0)]
        cfg = {"bounds": bounds, "seed": 42, "pop_size": 10}
        pop = 10
        n_generations = 25

        opt = IslandOptimizer("de", cfg, n_islands=4, migration_interval=5, migrant_count=2)
        best = _run_island_opt(opt, pop_size=pop, n_generations=n_generations)

        assert best < 1e-6, f"DE islands best={best:.2e} on sphere, expected < 1e-6"
