"""Smoke tests for stable-baselines3 integration with EigenfreqEnv.

Runs 2-update learn() for PPO, SAC, and TD3 on a tiny sphere objective
to confirm the SB3 ↔ EigenfreqEnv wiring is functional.
Skipped entirely when stable-baselines3 is not installed.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

# Deferred heavy import — skip entire module if unavailable
sb3 = pytest.importorskip("stable_baselines3", reason="stable-baselines3 not installed")

from stable_baselines3 import PPO, SAC, TD3

from eigenfrequencies.config import DesignConfig
from eigenfrequencies.optimize.rl import EigenfreqEnv

# ---------------------------------------------------------------------------
# Shared fixture — tiny sphere on t_midspan3 preset
# ---------------------------------------------------------------------------

@pytest.fixture
def sphere_env():
    """EigenfreqEnv with a cheap sphere objective (sum of squares)."""
    os.environ["DESIGN_PRESET"] = "t_midspan3"
    bounds = DesignConfig().bounds

    def sphere(design: np.ndarray) -> float:
        return float(np.sum(design**2))

    return EigenfreqEnv(bounds=bounds, objective_fn=sphere, max_evals=64)


# ---------------------------------------------------------------------------
# PPO — construction + one learn() call
# ---------------------------------------------------------------------------

def test_ppo_learn_two_updates(sphere_env):
    """Given: a valid EigenfreqEnv.
    When: PPO is constructed and learn() is called for 2 updates.
    Then: no exception is raised and the model is still functional.
    """
    model = PPO(
        policy="MlpPolicy",
        env=sphere_env,
        n_steps=32,          # tiny rollout per update
        n_epochs=2,
        verbose=0,
        policy_kwargs={"net_arch": [16]},
    )
    # Two updates — enough to exercise the env interaction pipeline
    model.learn(total_timesteps=64)
    # Verify the model still predicts
    obs, _ = sphere_env.reset()
    action, _ = model.predict(obs, deterministic=True)
    assert action.shape == sphere_env.action_space.shape


# ---------------------------------------------------------------------------
# SAC — construction + one learn() call
# ---------------------------------------------------------------------------

def test_sac_learn_two_updates(sphere_env):
    """Given: a valid EigenfreqEnv.
    When: SAC is constructed and learn() is called for 2 updates.
    Then: no exception is raised and the model is still functional.
    """
    model = SAC(
        policy="MlpPolicy",
        env=sphere_env,
        buffer_size=256,
        learning_starts=0,
        verbose=0,
        policy_kwargs={"net_arch": [16]},
    )
    model.learn(total_timesteps=64)
    obs, _ = sphere_env.reset()
    action, _ = model.predict(obs, deterministic=True)
    assert action.shape == sphere_env.action_space.shape


# ---------------------------------------------------------------------------
# TD3 — construction + one learn() call
# ---------------------------------------------------------------------------

def test_td3_learn_two_updates(sphere_env):
    """Given: a valid EigenfreqEnv.
    When: TD3 is constructed and learn() is called for 2 updates.
    Then: no exception is raised and the model is still functional.
    """
    model = TD3(
        policy="MlpPolicy",
        env=sphere_env,
        buffer_size=256,
        learning_starts=0,
        verbose=0,
        policy_kwargs={"net_arch": [16]},
    )
    model.learn(total_timesteps=64)
    obs, _ = sphere_env.reset()
    action, _ = model.predict(obs, deterministic=True)
    assert action.shape == sphere_env.action_space.shape
