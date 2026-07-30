"""Tests for EigenfreqEnv — gymnasium RL environment for eigenfrequency optimisation."""

import numpy as np
import pytest
from gymnasium.utils.env_checker import check_env

from eigenfrequencies.config import CFDConfig, DesignConfig, ObjectiveConfig, OptimizationConfig
from eigenfrequencies.config_yaml import ConfigError
from eigenfrequencies.optimize.rl import EigenfreqEnv

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def beam_cfg():
    """Load beam.yaml config objects used by several tests."""
    from eigenfrequencies.config_yaml import load_config
    return load_config("examples/configs/beam.yaml")


@pytest.fixture
def midspan3_bounds():
    """t_midspan3 design bounds — 3 dims, cheap for env_checker."""
    import os
    os.environ["DESIGN_PRESET"] = "t_midspan3"
    dc = DesignConfig()
    return dc.bounds


# ---------------------------------------------------------------------------
# 1. env_checker on beam config
# ---------------------------------------------------------------------------

def test_env_checker_passes_on_beam_config(beam_cfg):
    """Given: env with design bounds from t_midspan3 preset and a simple objective.
    When: env_checker runs.
    Then: the environment passes all Gymnasium API checks.
    """
    import os
    os.environ["DESIGN_PRESET"] = "t_midspan3"
    bounds = DesignConfig().bounds

    def sphere(design: np.ndarray) -> float:
        return float(np.sum(design**2))

    env = EigenfreqEnv(bounds=bounds, objective_fn=sphere, max_evals=5)
    check_env(env, skip_render_check=True)


# ---------------------------------------------------------------------------
# 2. 50 random steps never leave bounds
# ---------------------------------------------------------------------------

def test_random_steps_stay_inside_bounds():
    """Given: env with known bounds.
    When: 50 random actions are stepped.
    Then: every design vector stays within [min, max] for all dimensions.
    """
    bounds = [(0.0, 1.0), (-5.0, 5.0), (10.0, 20.0)]
    calls = []

    def record_objective(design: np.ndarray) -> float:
        calls.append(design.copy())
        return float(np.sum(design**2))

    env = EigenfreqEnv(bounds=bounds, objective_fn=record_objective, max_evals=100)
    env.reset(seed=0)

    rng = np.random.default_rng(123)
    for _ in range(50):
        action = rng.uniform(-1.0, 1.0, size=3).astype(np.float32)
        env.step(action)

    for design in calls:
        for d, (lo, hi) in zip(design, bounds):
            assert lo <= d <= hi, f"design value {d} outside [{lo}, {hi}]"


# ---------------------------------------------------------------------------
# 3. Reward equals -combined_objective on recorded input
# ---------------------------------------------------------------------------

def test_reward_equals_negative_combined_objective():
    """Given: env whose objective_fn wraps combined_objective output.
    When: step is called with a known action.
    Then: reward == -combined_objective value AND info carries the objective.
    """
    from eigenfrequencies.penalty.objective import combined_objective

    cfd_cfg = CFDConfig(n_rpm=72.0)
    opt_cfg = OptimizationConfig(n_rpm=72.0)
    obj_cfg = ObjectiveConfig()

    # Known CFD / frequency inputs that produce a deterministic total
    cfd = {"eta": -0.9, "vcav": 1e-7, "dH": -2.5}
    freqs = [30.0, 60.0, 90.0, 120.0]

    expected_total, _ = combined_objective(
        cfd, freqs, cfd_cfg, opt_cfg, obj_cfg
    )

    def objective_fn(design: np.ndarray) -> float:
        # Always returns the same pre-computed value — this mirrors what
        # a real eval loop would do after running CFD + FEA.
        return expected_total

    bounds = [(0.005, 0.06)]
    env = EigenfreqEnv(bounds=bounds, objective_fn=objective_fn)
    env.reset(seed=42)
    _, reward, _, _, info = env.step(np.array([0.0]))

    assert reward == pytest.approx(-expected_total)
    assert info["objective"] == pytest.approx(expected_total)
    assert info["step"] == 1


# ---------------------------------------------------------------------------
# 4. Deterministic reset
# ---------------------------------------------------------------------------

def test_reset_deterministic_with_seed():
    """Given: two env instances with the same bounds and objective.
    When: both are reset with seed=42.
    Then: they produce the identical initial observation.
    """
    bounds = [(0.0, 1.0), (0.0, 1.0)]

    def sphere(design: np.ndarray) -> float:
        return float(np.sum(design**2))

    env1 = EigenfreqEnv(bounds=bounds, objective_fn=sphere)
    env2 = EigenfreqEnv(bounds=bounds, objective_fn=sphere)

    obs1, _ = env1.reset(seed=42)
    obs2, _ = env2.reset(seed=42)

    np.testing.assert_array_equal(obs1, obs2)


def test_reset_different_seeds_produce_different_observations():
    """Given: two env instances.
    When: reset with different seeds (42 vs 99).
    Then: initial observations differ.
    """
    bounds = [(0.0, 1.0), (0.0, 1.0)]

    def sphere(design: np.ndarray) -> float:
        return float(np.sum(design**2))

    env1 = EigenfreqEnv(bounds=bounds, objective_fn=sphere)
    env2 = EigenfreqEnv(bounds=bounds, objective_fn=sphere)

    obs1, _ = env1.reset(seed=42)
    obs2, _ = env2.reset(seed=99)

    assert not np.array_equal(obs1, obs2)


# ---------------------------------------------------------------------------
# 5. Bounds validation — min > max raises ConfigError
# ---------------------------------------------------------------------------

def test_empty_bounds_raises():
    """Given: an empty bounds list.
    Then: ConfigError is raised at construction.
    """
    with pytest.raises(ConfigError, match="empty"):
        EigenfreqEnv(bounds=[], objective_fn=lambda x: 0.0)


def test_min_greater_than_max_raises():
    """Given: bounds where min > max.
    Then: ConfigError is raised at construction (not at first step).
    """
    with pytest.raises(ConfigError, match="min .* > max"):
        EigenfreqEnv(bounds=[(1.0, 0.0)], objective_fn=lambda x: 0.0)


def test_multidim_bounds_with_one_invalid_raises():
    """Given: bounds where one dimension has min > max.
    Then: ConfigError names the dimension index.
    """
    with pytest.raises(ConfigError, match="dimension 1.*min.*>.*max"):
        EigenfreqEnv(
            bounds=[(0.0, 1.0), (5.0, 3.0), (0.0, 10.0)],
            objective_fn=lambda x: 0.0,
        )


# ---------------------------------------------------------------------------
# 6. Episode termination
# ---------------------------------------------------------------------------

def test_episode_terminates_at_max_evals():
    """Given: env with max_evals=3.
    When: 3 steps are taken.
    Then: step 3 returns terminated=True.
    """
    bounds = [(0.0, 1.0)]
    env = EigenfreqEnv(bounds=bounds, objective_fn=lambda x: float(x[0]), max_evals=3)
    env.reset(seed=0)

    _, _, term1, _, _ = env.step(np.array([0.5]))
    assert not term1

    _, _, term2, _, _ = env.step(np.array([0.5]))
    assert not term2

    _, _, term3, _, _ = env.step(np.array([0.5]))
    assert term3


def test_episode_terminates_at_target_objective():
    """Given: env with target_objective=0.5.
    When: step produces objective <= 0.5.
    Then: terminated=True.
    """
    bounds = [(0.0, 1.0)]
    env = EigenfreqEnv(
        bounds=bounds,
        objective_fn=lambda x: float(x[0]),
        max_evals=100,
        target_objective=0.5,
    )
    env.reset(seed=0)

    # Action 0 → design 0.5 → objective 0.5 → reaches target
    _, _, terminated, _, info = env.step(np.array([-1.0]))  # maps to design 0.0, obj=0.0
    assert terminated
    assert info["objective"] <= 0.5


# ---------------------------------------------------------------------------
# 7. Observation and action space shapes
# ---------------------------------------------------------------------------

def test_spaces_match_dim():
    """Given: bounds with 5 dimensions.
    Then: action_space.shape == (5,) and observation_space.shape == (6,).
    """
    bounds = [(0.0, 1.0)] * 5
    env = EigenfreqEnv(bounds=bounds, objective_fn=lambda x: 0.0)

    assert env.action_space.shape == (5,)
    assert env.observation_space.shape == (6,)


def test_action_space_is_normalized():
    """Given: env with arbitrary bounds.
    Then: action_space is Box(-1, 1) regardless of design bounds.
    """
    bounds = [(100.0, 200.0), (-50.0, 50.0)]
    env = EigenfreqEnv(bounds=bounds, objective_fn=lambda x: 0.0)

    assert env.action_space.low == pytest.approx(-1.0)
    assert env.action_space.high == pytest.approx(1.0)
