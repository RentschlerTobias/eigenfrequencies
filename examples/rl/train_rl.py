"""Train an RL agent (PPO / SAC / TD3) on the beam-spline eigenfrequency problem.

Usage:
    python examples/rl/train_rl.py                          # PPO, default 2048 steps
    python examples/rl/train_rl.py --algo ppo --steps 512  # tiny smoke run
    python examples/rl/train_rl.py --algo sac --steps 2048
    python examples/rl/train_rl.py --algo dqn               # exits 2 — unsupported

Output:
    rl_history.json — JSON list of {"timestep": N, "reward": M} per eval.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import typer

# Resolve project root (examples/rl/ → repo root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from eigenfrequencies.config import DesignConfig
from eigenfrequencies.optimize.rl import EigenfreqEnv

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = typer.Typer(invoke_without_command=True)


@app.command()
def main(
    algo: str = typer.Option("ppo", "--algo", help="ppo | sac | td3 | dqn"),
    steps: int = typer.Option(2048, "--steps", help="Total environment steps"),
    eval_interval: int = typer.Option(512, "--eval-interval", help="Eval frequency"),
    seed: int | None = typer.Option(None, "--seed"),
) -> None:
    # DQN does not support continuous Box action spaces — exit 2 per requirement
    if algo == "dqn":
        typer.secho(
            "DQN is unsupported for continuous Box action space.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    # ---------------------------------------------------------------------------
    # Build environment
    # ---------------------------------------------------------------------------
    preset = os.environ.get("DESIGN_PRESET", "t_midspan3")
    os.environ["DESIGN_PRESET"] = preset
    bounds = DesignConfig().bounds

    def sphere_objective(design: np.ndarray) -> float:
        """Simple sphere: sum of squared design variables (minimisation target)."""
        return float(np.sum(design**2))

    env = EigenfreqEnv(
        bounds=bounds,
        objective_fn=sphere_objective,
        max_evals=steps,
    )

    # ---------------------------------------------------------------------------
    # Import the selected algorithm (defer heavy import)
    # ---------------------------------------------------------------------------
    try:
        from stable_baselines3 import PPO, SAC, TD3
    except ImportError as exc:
        typer.secho(
            f"stable-baselines3 is required for RL training: {exc}",
            fg=typer.colors.RED,
            err=True,
        )
        raise SystemExit(1) from exc

    alg_map = {"ppo": PPO, "sac": SAC, "td3": TD3}
    if algo not in alg_map:
        typer.secho(
            f"Unknown algorithm {algo!r}. Choose: {' | '.join(alg_map)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)

    model_cls = alg_map[algo]
    policy_kwargs = {"net_arch": [32, 32]}  # tiny network for smoke/beam budgets

    common_kwargs = {
        "policy": "MlpPolicy",
        "env": env,
        "verbose": 0,
        "seed": seed,
        "policy_kwargs": policy_kwargs,
    }

    if algo == "ppo":
        model = PPO(**common_kwargs)
    elif algo == "sac":
        model = SAC(**common_kwargs)
    else:  # td3
        model = TD3(**common_kwargs)

    # ---------------------------------------------------------------------------
    # Training loop with eval history
    # ---------------------------------------------------------------------------
    history: list[dict] = []
    n_eval_episodes = 5  # episodes per eval

    typer.secho(f"Training {algo.upper()} on beam-spline (steps={steps})…", fg=typer.colors.GREEN)

    total_steps = 0
    while total_steps < steps:
        chunk = min(eval_interval, steps - total_steps)
        model.learn(total_timesteps=chunk, reset_num_timesteps=False)

        # Quick eval: run n episodes and record mean reward
        eval_rewards: list[float] = []
        for _ in range(n_eval_episodes):
            obs, _ = env.reset()
            done = False
            ep_reward = 0.0
            while not done:
                action, _ = model.predict(obs, deterministic=False)
                obs, reward, terminated, truncated, _ = env.step(action)
                done = terminated or truncated
                ep_reward += reward
            eval_rewards.append(ep_reward)

        mean_reward = float(np.mean(eval_rewards))
        history.append({"timestep": total_steps + chunk, "reward": mean_reward})
        typer.echo(f"  step {total_steps + chunk:>6} | mean eval reward: {mean_reward:>10.4f}")
        total_steps += chunk

    # ---------------------------------------------------------------------------
    # Persist history
    # ---------------------------------------------------------------------------
    out_path = _PROJECT_ROOT / "rl_history.json"
    with open(out_path, "w") as fh:
        json.dump(history, fh, indent=2)
    typer.secho(f"Saved rl_history.json ({len(history)} eval points)", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
