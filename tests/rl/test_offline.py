"""Tests for offline RL dataset exporter (de_history*.jsonl → d3rlpy MDPDataset)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from eigenfrequencies.optimize.rl.offline_export import (
    build_actions,
    build_observations,
    build_rewards,
    build_terminals,
    detect_feature_fields,
    export_dataset,
    parse_history_jsonl,
)

# -- Paths to real history files --------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HISTORY_DIR = _REPO_ROOT / "turbine_runner"

_HISTORY_RESONANCE = _HISTORY_DIR / "de_history_resonance_only.jsonl"
_HISTORY_COMBINED = _HISTORY_DIR / "de_history_combined.jsonl"
_HISTORY_CFD = _HISTORY_DIR / "de_history_cfd_only.jsonl"


# -- Helpers ----------------------------------------------------------------

def _write_jsonl(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")


def _resolve_npz(p: Path) -> Path:
    """Return *p* if it exists, else ``p`` with ``.npz`` appended."""
    if p.exists():
        return p
    alt = p.with_suffix(p.suffix + ".npz")
    if alt.exists():
        return alt
    return p


# ---------------------------------------------------------------------------
# 1. parse_history_jsonl
# ---------------------------------------------------------------------------


class TestParseHistoryJsonl:
    def test_parse_resonance_only_returns_rows_and_zero_skipped(self):
        """Given: the real de_history_resonance_only.jsonl (13 lines).
        Then: all 13 rows parse, skipped=0.
        """
        rows, skipped = parse_history_jsonl(_HISTORY_RESONANCE)
        assert len(rows) == 13
        assert skipped == 0
        assert all(isinstance(r, dict) for r in rows)

    def test_parse_combined_returns_101_rows(self):
        """Given: de_history_combined.jsonl (101 lines).
        Then: 101 rows parsed, skipped=0.
        """
        rows, skipped = parse_history_jsonl(_HISTORY_COMBINED)
        assert len(rows) == 101
        assert skipped == 0

    def test_parse_cfd_only_returns_101_rows(self):
        """Given: de_history_cfd_only.jsonl (101 lines).
        Then: 101 rows parsed, skipped=0.
        """
        rows, skipped = parse_history_jsonl(_HISTORY_CFD)
        assert len(rows) == 101
        assert skipped == 0

    def test_corrupt_line_reported_as_skipped(self, tmp_path: Path):
        """Given: a JSONL with one corrupt line between two good lines.
        Then: skipped=1, the good lines are still parsed.
        """
        p = tmp_path / "corrupt.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 1.0, "f1": 10.0}),
                "this is not json {{{",
                json.dumps({"gen": 2, "best": 0.8, "f1": 12.0}),
            ],
        )
        rows, skipped = parse_history_jsonl(p)
        assert len(rows) == 2
        assert skipped == 1
        assert rows[0]["gen"] == 0
        assert rows[1]["gen"] == 2

    def test_missing_file_raises(self):
        """Given: a nonexistent file path.
        Then: FileNotFoundError is raised.
        """
        with pytest.raises(FileNotFoundError):
            parse_history_jsonl(Path("/nonexistent/history.jsonl"))

    def test_empty_file_yields_zero_rows(self, tmp_path: Path):
        """Given: an empty file.
        Then: rows=[], skipped=0.
        """
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        rows, skipped = parse_history_jsonl(p)
        assert rows == []
        assert skipped == 0

    def test_blank_lines_are_ignored(self, tmp_path: Path):
        """Given: a file with blank lines between data lines.
        Then: blank lines are skipped, not counted as corrupt.
        """
        p = tmp_path / "blanks.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 1.0, "f1": 10.0}),
                "",
                "   ",
                json.dumps({"gen": 1, "best": 0.9, "f1": 11.0}),
            ],
        )
        rows, skipped = parse_history_jsonl(p)
        assert len(rows) == 2
        assert skipped == 0


# ---------------------------------------------------------------------------
# 2. detect_feature_fields
# ---------------------------------------------------------------------------


class TestDetectFeatureFields:
    def test_resonance_only_fields(self):
        """Given: de_history_resonance_only rows.
        Then: feature fields = ['f1', 'f_resonance'] (sorted).
        """
        rows, _ = parse_history_jsonl(_HISTORY_RESONANCE)
        fields = detect_feature_fields(rows)
        assert fields == ["f1", "f_resonance"]

    def test_combined_fields(self):
        """Given: de_history_combined rows.
        Then: feature fields include f_resonance, f_cfd, eta, vcav, dH.
        """
        rows, _ = parse_history_jsonl(_HISTORY_COMBINED)
        fields = detect_feature_fields(rows)
        expected = ["dH", "eta", "f_cfd", "f_resonance", "vcav"]
        assert fields == expected

    def test_cfd_only_fields(self):
        """Given: de_history_cfd_only rows.
        Then: feature fields exclude f_resonance.
        """
        rows, _ = parse_history_jsonl(_HISTORY_CFD)
        fields = detect_feature_fields(rows)
        assert "f_resonance" not in fields
        assert "f_cfd" in fields

    def test_empty_rows_yields_empty(self):
        """Given: empty row list.
        Then: fields is empty list.
        """
        assert detect_feature_fields([]) == []


# ---------------------------------------------------------------------------
# 3. build_observations / build_actions / build_rewards / build_terminals
# ---------------------------------------------------------------------------


class TestBuildArrays:
    @pytest.fixture
    def simple_rows(self):
        return [
            {"gen": 0, "best": 10.0, "mean": 11.0, "f1": 100.0, "f2": 200.0},
            {"gen": 1, "best": 8.0, "mean": 9.0, "f1": 90.0, "f2": 180.0},
            {"gen": 2, "best": 5.0, "mean": 6.0, "f1": 80.0, "f2": 160.0},
        ]

    def test_observations_shape(self, simple_rows):
        """Given: 3 rows, 2 feature fields.
        Then: observations shape = (3, 2).
        """
        fields = detect_feature_fields(simple_rows)
        obs = build_observations(simple_rows, fields)
        assert obs.shape == (3, 2)  # f1, f2

    def test_observations_normalised(self, simple_rows):
        """Given: bounds_low=[80, 150], bounds_high=[100, 200].
        Then: observations are in [0, 1].
        """
        fields = detect_feature_fields(simple_rows)
        bl = np.array([80.0, 150.0], dtype=np.float32)
        bh = np.array([100.0, 200.0], dtype=np.float32)
        obs = build_observations(simple_rows, fields, bl, bh)
        assert np.all(obs >= 0.0) and np.all(obs <= 1.0)
        # First row: f1=100, f2=200 → (1.0, 1.0)
        assert obs[0, 0] == pytest.approx(1.0)
        assert obs[0, 1] == pytest.approx(1.0)

    def test_actions_are_next_observation(self, simple_rows):
        """Given: 3 observations.
        Then: actions[0] == obs[1], actions[1] == obs[2], actions[2] == zeros.
        """
        fields = detect_feature_fields(simple_rows)
        obs = build_observations(simple_rows, fields)
        actions = build_actions(obs)
        np.testing.assert_array_equal(actions[0], obs[1])
        np.testing.assert_array_equal(actions[1], obs[2])
        np.testing.assert_array_equal(actions[2], np.zeros_like(obs[2]))

    def test_rewards_raw(self, simple_rows):
        """Given: reward_mode='raw'.
        Then: reward = -best for each row.
        """
        rewards = build_rewards(simple_rows, "raw")
        np.testing.assert_array_equal(
            rewards, np.array([-10.0, -8.0, -5.0], dtype=np.float32)
        )

    def test_rewards_improvement(self, simple_rows):
        """Given: reward_mode='improvement'.
        Then: reward[t] = -(best[t+1] - best[t]), last = 0.
        """
        rewards = build_rewards(simple_rows, "improvement")
        # best: [10, 8, 5]
        # improvements: [-(8-10)=2, -(5-8)=3, 0]
        np.testing.assert_array_equal(
            rewards, np.array([2.0, 3.0, 0.0], dtype=np.float32)
        )

    def test_terminals_last_is_one(self):
        """Given: 3 rows.
        Then: terminals = [0, 0, 1].
        """
        terminals = build_terminals(3)
        np.testing.assert_array_equal(
            terminals, np.array([0.0, 0.0, 1.0], dtype=np.float32)
        )

    def test_single_row_actions_and_rewards(self):
        """Given: a single-row history.
        Then: actions = zeros, rewards_improvement = [0], terminals = [1].
        """
        rows = [{"gen": 0, "best": 5.0, "f1": 10.0}]
        fields = detect_feature_fields(rows)
        obs = build_observations(rows, fields)
        actions = build_actions(obs)
        rewards = build_rewards(rows, "improvement")
        terminals = build_terminals(1)
        np.testing.assert_array_equal(actions, np.zeros((1, 1), dtype=np.float32))
        np.testing.assert_array_equal(rewards, np.array([0.0], dtype=np.float32))
        np.testing.assert_array_equal(terminals, np.array([1.0], dtype=np.float32))


# ---------------------------------------------------------------------------
# 4. export_dataset integration
# ---------------------------------------------------------------------------


class TestExportDataset:
    def test_export_resonance_only(self, tmp_path: Path):
        """Given: the real resonance_only history.
        Then: export_dataset returns (13, 0) and writes a file.
        """
        out = tmp_path / "resonance.d3"
        n_rows, skipped = export_dataset(
            history_path=_HISTORY_RESONANCE,
            out_path=out,
            reward_mode="improvement",
        )
        assert n_rows == 13
        assert skipped == 0
        resolved = _resolve_npz(out)
        assert resolved.exists()
        data = np.load(str(resolved))
        assert data["observations"].shape == (13, 2)
        assert data["actions"].shape == (13, 2)
        assert data["rewards"].shape == (13,)
        assert data["terminals"].shape == (13,)

    def test_export_combined(self, tmp_path: Path):
        """Given: the real combined history.
        Then: export_dataset returns (101, 0), 5 features.
        """
        out = tmp_path / "combined.d3"
        n_rows, skipped = export_dataset(
            history_path=_HISTORY_COMBINED,
            out_path=out,
            reward_mode="raw",
        )
        assert n_rows == 101
        assert skipped == 0
        data = np.load(str(_resolve_npz(out)))
        assert data["observations"].shape == (101, 5)

    def test_export_cfd_only(self, tmp_path: Path):
        """Given: the real cfd_only history.
        Then: export_dataset returns (101, 0), 4 features (no f_resonance).
        """
        out = tmp_path / "cfd.d3"
        n_rows, skipped = export_dataset(
            history_path=_HISTORY_CFD,
            out_path=out,
            reward_mode="improvement",
        )
        assert n_rows == 101
        assert skipped == 0
        data = np.load(str(_resolve_npz(out)))
        assert data["observations"].shape == (101, 4)

    def test_export_with_bounds(self, tmp_path: Path):
        """Given: explicit normalisation bounds that cover the data.
        Then: observations are in [0, 1].
        """
        out = tmp_path / "bounded.d3"
        # Fields sorted alphabetically: ["f1", "f_resonance"]
        # f1 ∈ [25.84, 32.11], f_resonance ∈ [4.90, 7.36]
        n_rows, skipped = export_dataset(
            history_path=_HISTORY_RESONANCE,
            out_path=out,
            reward_mode="improvement",
            bounds_low=[20.0, 0.0],
            bounds_high=[40.0, 10.0],
        )
        assert n_rows == 13
        assert skipped == 0
        data = np.load(str(_resolve_npz(out)))
        obs = data["observations"]
        assert np.all(obs >= 0.0)
        assert np.all(obs <= 1.0)

    def test_export_with_corrupt_line(self, tmp_path: Path):
        """Given: a history file with one corrupt JSON line.
        Then: skipped=1, still exports the rest.
        """
        p = tmp_path / "partial.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 5.0, "f1": 10.0}),
                "not json at all {{{",
                json.dumps({"gen": 1, "best": 4.0, "f1": 11.0}),
                json.dumps({"gen": 2, "best": 3.0, "f1": 12.0}),
            ],
        )
        out = tmp_path / "partial.d3"
        n_rows, skipped = export_dataset(
            history_path=p,
            out_path=out,
            reward_mode="improvement",
        )
        assert n_rows == 3
        assert skipped == 1
        data = np.load(str(_resolve_npz(out)))
        assert data["observations"].shape == (3, 1)

    def test_export_uses_default_out_path(self, tmp_path: Path):
        """Given: no explicit --out.
        Then: output written to <history_stem>.d3 (or .d3.npz).
        """
        p = tmp_path / "test_history.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 5.0, "f1": 10.0}),
                json.dumps({"gen": 1, "best": 4.0, "f1": 11.0}),
            ],
        )
        n_rows, skipped = export_dataset(history_path=p)
        assert n_rows == 2
        assert skipped == 0
        default_out = tmp_path / "test_history.d3"
        resolved = _resolve_npz(default_out)
        assert resolved.exists()

    def test_bounds_mismatch_raises(self, tmp_path: Path):
        """Given: bounds with wrong length.
        Then: ValueError raised before writing.
        """
        p = tmp_path / "mismatch.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 5.0, "f1": 10.0}),
                json.dumps({"gen": 1, "best": 4.0, "f1": 11.0}),
            ],
        )
        with pytest.raises(ValueError, match="bounds length"):
            export_dataset(
                history_path=p,
                bounds_low=[0.0, 0.0],
                bounds_high=[1.0, 1.0],
            )

    def test_asymmetric_bounds_raises(self, tmp_path: Path):
        """Given: bounds_low set but bounds_high None.
        Then: ValueError raised.
        """
        p = tmp_path / "asym.jsonl"
        _write_jsonl(
            p,
            [
                json.dumps({"gen": 0, "best": 5.0, "f1": 10.0}),
                json.dumps({"gen": 1, "best": 4.0, "f1": 11.0}),
            ],
        )
        with pytest.raises(ValueError, match="both be set"):
            export_dataset(
                history_path=p,
                bounds_low=[0.0],
                bounds_high=None,
            )

    def test_no_parseable_rows_raises(self, tmp_path: Path):
        """Given: a file with only corrupt lines.
        Then: ValueError raised.
        """
        p = tmp_path / "all_corrupt.jsonl"
        _write_jsonl(p, ["garbage {{{", "more garbage"])
        with pytest.raises(ValueError, match="No parseable rows"):
            export_dataset(history_path=p)

    def test_missing_file_raises_in_export(self, tmp_path: Path):
        """Given: nonexistent history path.
        Then: FileNotFoundError propagates.
        """
        with pytest.raises(FileNotFoundError):
            export_dataset(history_path=Path("/nonexistent/history.jsonl"))


# ---------------------------------------------------------------------------
# 5. CQL smoke test (skip if d3rlpy absent)
# ---------------------------------------------------------------------------

try:
    import d3rlpy  # noqa: F401

    _D3RLPY_AVAILABLE = True
except ImportError:
    _D3RLPY_AVAILABLE = False

_D3RLPY_REASON = "d3rlpy not installed"


@pytest.mark.skipif(not _D3RLPY_AVAILABLE, reason=_D3RLPY_REASON)
class TestCqlSmoke:
    def test_cql_two_epochs_on_resonance_only(self, tmp_path: Path):
        """Given: the resonance_only dataset exported and loaded as MDPDataset.
        When: CQL runs for 2 epochs.
        Then: training completes and writes metrics JSON.
        """
        from d3rlpy.algos import CQLConfig
        from d3rlpy.dataset import MDPDataset

        rows, _ = parse_history_jsonl(_HISTORY_RESONANCE)
        fields = detect_feature_fields(rows)
        obs = build_observations(rows, fields)
        acts = build_actions(obs)
        rews = build_rewards(rows, "improvement")
        terms = build_terminals(len(rows))

        dataset = MDPDataset(
            observations=obs,
            actions=acts,
            rewards=rews,
            terminals=terms,
        )

        cql = CQLConfig(
            actor_learning_rate=1e-4,
            critic_learning_rate=3e-4,
            temp_learning_rate=1e-4,
            batch_size=4,
            n_steps=1,
            gamma=0.99,
        ).create(device="cpu")

        # 2-epoch smoke: fit should not crash
        metrics = {}
        for epoch in range(2):
            result = cql.fit(
                dataset,
                n_steps=min(len(dataset), 10),
                n_steps_per_epoch=min(len(dataset), 10),
                evaluators={"td_error": d3rlpy.metrics.TDErrorEvaluator()},
            )
            if result:
                for entry in result:
                    metrics.update(entry)

        metrics_path = tmp_path / "cql_metrics.json"
        metrics_path.write_text(json.dumps(metrics, indent=2, default=str))
        assert metrics_path.exists()

        # The agent should produce actions of the right shape
        action = cql.predict(np.array([obs[0]]))
        assert action.shape == (1, len(fields))

    def test_cql_on_cfd_only(self, tmp_path: Path):
        """Given: the cfd_only dataset.
        When: CQL runs for 2 epochs.
        Then: training completes.
        """
        from d3rlpy.algos import CQLConfig
        from d3rlpy.dataset import MDPDataset

        rows, _ = parse_history_jsonl(_HISTORY_CFD)
        fields = detect_feature_fields(rows)
        obs = build_observations(rows, fields)
        acts = build_actions(obs)
        rews = build_rewards(rows, "raw")
        terms = build_terminals(len(rows))

        dataset = MDPDataset(
            observations=obs,
            actions=acts,
            rewards=rews,
            terms=terms,
        )

        cql = CQLConfig(
            batch_size=4,
            n_steps=1,
        ).create(device="cpu")

        for _ in range(2):
            cql.fit(
                dataset,
                n_steps=min(len(dataset), 10),
                n_steps_per_epoch=min(len(dataset), 10),
            )

        action = cql.predict(np.array([obs[0]]))
        assert action.shape == (1, len(fields))
