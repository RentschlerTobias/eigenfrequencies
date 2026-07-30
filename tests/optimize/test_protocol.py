"""Tests for the optimizer protocol (ABC, Design, registry, errors)."""

import numpy as np
import pytest

from eigenfrequencies.optimize.protocol import (
    Design,
    Optimizer,
    ProtocolUsageError,
    create,
    register,
)


class DummyOptimizer(Optimizer):
    """Minimal concrete Optimizer for protocol testing."""

    def __init__(self, bounds, seed=0):
        self._bounds = bounds
        self._rng = np.random.default_rng(seed)
        self._population = None
        self._objectives = None

    @property
    def bounds(self):
        return list(self._bounds)

    def ask(self, n: int) -> list[Design]:
        vecs = [self._rng.random(len(self._bounds)).tolist() for _ in range(n)]
        return [Design(vector=v) for v in vecs]

    def tell(self, designs: list[Design], objectives: list[float]) -> None:
        if len(designs) != len(objectives):
            raise ProtocolUsageError("length mismatch")
        self._population = [d.vector for d in designs]
        self._objectives = list(objectives)

    def state_dict(self) -> dict:
        return {
            "bounds": self._bounds,
            "population": self._population,
            "objectives": self._objectives,
            "rng_state": self._rng.bit_generator.state,
        }

    def load_state(self, state: dict) -> None:
        self._bounds = [tuple(b) for b in state["bounds"]]
        self._population = state.get("population")
        self._objectives = state.get("objectives")
        self._rng.bit_generator.state = state["rng_state"]


def test_design_is_frozen():
    d = Design(vector=[1.0, 2.0])
    with pytest.raises(AttributeError):
        d.vector = [3.0, 4.0]


def test_design_metadata_default():
    d = Design(vector=[1.0])
    assert d.metadata == {}


def test_ask_returns_requested_count():
    opt = DummyOptimizer(bounds=[(0.0, 1.0), (-1.0, 1.0)])
    designs = opt.ask(5)
    assert len(designs) == 5
    assert all(len(d.vector) == 2 for d in designs)


def test_tell_updates_state():
    opt = DummyOptimizer(bounds=[(0.0, 1.0)])
    designs = opt.ask(3)
    opt.tell(designs, [1.0, 2.0, 3.0])
    assert opt._population is not None
    assert opt._objectives == [1.0, 2.0, 3.0]


def test_tell_mismatched_lengths_raises():
    opt = DummyOptimizer(bounds=[(0.0, 1.0)])
    designs = opt.ask(3)
    with pytest.raises(ProtocolUsageError):
        opt.tell(designs, [1.0, 2.0])


def test_state_roundtrip_reproduces_ask():
    """state_dict → load_state → next ask must match the original sequence."""
    opt1 = DummyOptimizer(bounds=[(0.0, 1.0), (0.0, 1.0)], seed=42)
    d1a = opt1.ask(4)
    opt1.tell(d1a, [1.0, 2.0, 3.0, 4.0])

    # Capture state *before* the next ask so the restored RNG produces
    # the same sequence.
    state = opt1.state_dict()
    d1b = opt1.ask(4)

    opt2 = DummyOptimizer(bounds=[(0.0, 0.0)], seed=999)  # different init
    opt2.load_state(state)
    d2b = opt2.ask(4)

    assert [d.vector for d in d1b] == [d.vector for d in d2b]


def test_register_and_create():
    register("dummy_for_test", lambda cfg: DummyOptimizer(bounds=cfg["bounds"], seed=cfg.get("seed", 0)))
    opt = create("dummy_for_test", {"bounds": [(0.0, 1.0)], "seed": 7})
    assert isinstance(opt, DummyOptimizer)
    assert opt.bounds == [(0.0, 1.0)]


def test_create_unknown_raises():
    with pytest.raises(ValueError, match="Unknown optimizer"):
        create("definitely_not_registered", {})
