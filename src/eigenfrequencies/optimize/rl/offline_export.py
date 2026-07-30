"""Offline RL dataset exporter: de_history*.jsonl → d3rlpy MDPDataset.

Parses per-generation DE history JSONL files, extracts objective-space
observation vectors, builds action/reward/terminal arrays, and exports a
d3rlpy-compatible MDPDataset (HDF5) or a numpy npz fallback when d3rlpy is
unavailable.

Usage::

    eigenfrequencies rl-export --history de_history_combined.jsonl --out dataset.d3
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

import numpy as np

logger = logging.getLogger(__name__)

# Fields excluded from the observation vector — everything else is a feature.
_METADATA_FIELDS: frozenset[str] = frozenset(
    {"gen", "best", "mean", "ok", "n", "t_gen_s"}
)


def parse_history_jsonl(path: Path) -> tuple[list[dict], int]:
    """Parse a JSONL history file.

    Returns:
        (rows, skipped) where *rows* is the list of parseable dicts and
        *skipped* counts malformed (non-empty) lines.

    Raises:
        FileNotFoundError: if *path* does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"History file not found: {path}")

    rows: list[dict] = []
    skipped = 0
    for line_num, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            skipped += 1
            logger.warning("Skipping malformed JSON at %s line %d", path, line_num)
    return rows, skipped


def detect_feature_fields(rows: list[dict]) -> list[str]:
    """Return sorted list of non-metadata numeric fields present in *rows*.

    Uses the first row to discover the field set.  Returns an empty list when
    *rows* is empty.
    """
    if not rows:
        return []
    first = rows[0]
    fields = sorted(
        k
        for k in first
        if k not in _METADATA_FIELDS and isinstance(first[k], (int, float))
    )
    return fields


def _build_best_array(rows: list[dict]) -> np.ndarray:
    """Extract the ``best`` scalar from every row as float32."""
    return np.array([float(r["best"]) for r in rows], dtype=np.float32)


def build_observations(
    rows: list[dict],
    feature_fields: list[str],
    bounds_low: np.ndarray | None = None,
    bounds_high: np.ndarray | None = None,
) -> np.ndarray:
    """Build (n_rows, n_features) observation matrix.

    When *bounds_low* and *bounds_high* are both provided, values are
    normalised to [0, 1] via ``(x - low) / (high - low)``.
    """
    n = len(rows)
    dim = len(feature_fields)
    obs = np.zeros((n, dim), dtype=np.float32)
    for i, row in enumerate(rows):
        for j, field in enumerate(feature_fields):
            obs[i, j] = float(row[field])

    if bounds_low is not None and bounds_high is not None:
        rng = bounds_high - bounds_low
        obs = (obs - bounds_low) / rng
    return obs


def build_actions(observations: np.ndarray) -> np.ndarray:
    """Action = next observation.  Last action is all-zero (terminal)."""
    actions = np.zeros_like(observations)
    if len(observations) > 1:
        actions[:-1] = observations[1:]
    return actions


def build_rewards(
    rows: list[dict],
    mode: Literal["raw", "improvement"],
) -> np.ndarray:
    """Build per-step reward array.

    - ``raw``: reward = ``-best`` at every step.
    - ``improvement``: reward = ``-(best_{t+1} - best_t)``; final step = 0.
    """
    bests = _build_best_array(rows)
    n = len(rows)
    rewards = np.zeros(n, dtype=np.float32)

    if mode == "raw":
        rewards = -bests
    else:
        if n > 1:
            rewards[:-1] = -(bests[1:] - bests[:-1])
        # rewards[-1] stays 0 (no next step to compare against)
    return rewards


def build_terminals(n_rows: int) -> np.ndarray:
    """Return a boolean float32 array where only the last entry is 1.0."""
    terminals = np.zeros(n_rows, dtype=np.float32)
    if n_rows > 0:
        terminals[-1] = 1.0
    return terminals


def export_dataset(
    history_path: Path,
    out_path: Path | None = None,
    reward_mode: Literal["raw", "improvement"] = "improvement",
    bounds_low: list[float] | None = None,
    bounds_high: list[float] | None = None,
) -> tuple[int, int]:
    """Parse history, build arrays, save MDPDataset (or npz fallback).

    Returns:
        (n_rows, skipped) — number of parseable rows and count of
        malformed lines.

    Raises:
        FileNotFoundError: *history_path* missing.
        ValueError: no parseable rows, or bounds length mismatch.
    """
    rows, skipped = parse_history_jsonl(history_path)

    if not rows:
        raise ValueError(f"No parseable rows in {history_path}")

    feature_fields = detect_feature_fields(rows)
    if not feature_fields:
        raise ValueError(f"No feature fields detected in {history_path}")

    # Validate bounds
    bl = np.array(bounds_low, dtype=np.float32) if bounds_low else None
    bh = np.array(bounds_high, dtype=np.float32) if bounds_high else None
    if (bl is None) != (bh is None):
        raise ValueError("bounds_low and bounds_high must both be set or both None")
    if bl is not None and bh is not None and len(bl) != len(feature_fields):
        raise ValueError(
            f"bounds length ({len(bl)}) != feature count ({len(feature_fields)})"
        )

    observations = build_observations(rows, feature_fields, bl, bh)
    actions = build_actions(observations)
    rewards = build_rewards(rows, reward_mode)
    terminals = build_terminals(len(rows))

    out = out_path or history_path.with_suffix(".d3")

    try:
        from d3rlpy.dataset import MDPDataset

        dataset = MDPDataset(
            observations=observations,
            actions=actions,
            rewards=rewards,
            terminals=terminals,
        )
        dataset.dump(str(out))
    except ImportError:
        logger.info("d3rlpy not available — saving as compressed npz")
        save_path = str(out)
        if not save_path.endswith(".npz"):
            save_path += ".npz"
        np.savez_compressed(
            save_path,
            observations=observations,
            actions=actions,
            rewards=rewards,
            terminals=terminals,
        )

    return len(rows), skipped
