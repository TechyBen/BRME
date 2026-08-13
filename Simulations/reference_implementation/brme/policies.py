"""Policies: the strategy space that equilibria are searched over.

The space is deliberately tiny and enumerable. Best responses can then be found
by exhaustive search rather than by an optimiser, so a reported equilibrium is an
actual fixed point of exact best responses and not an artefact of a search that
stalled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .field import Action, Observation, WorldConfig

__all__ = ["ThresholdPolicy", "FixedPolicy", "policy_grid"]


@dataclass(frozen=True)
class ThresholdPolicy:
    """A priority rule over the three attractor classes.

    The two thresholds set where the agent draws the line between the attractors:

    * ``energy_threshold`` - at or below this energy, acquire (E takes priority).
    * ``mismatch_threshold`` - otherwise, if at least this many cells are
      corrupted, error-correct (M); else improve the model (C).

    Setting ``mismatch_threshold`` to 0 means "always correct" and setting it
    above ``private_bits`` means "never correct", so the grid spans the full
    range from pure M to pure C behaviour.
    """

    energy_threshold: float
    mismatch_threshold: int

    def act(self, obs: Observation) -> Action:
        if obs.energy <= self.energy_threshold:
            return Action.HARVEST
        if obs.mismatch >= self.mismatch_threshold:
            return Action.HOLD
        return Action.PROBE

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"(e<={self.energy_threshold:g}, mm>={self.mismatch_threshold})"


@dataclass(frozen=True)
class FixedPolicy:
    """Always takes one action. Used for passive or scripted systems."""

    action: Action

    def act(self, obs: Observation) -> Action:  # noqa: ARG002 - fixed by design
        return self.action

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"always-{self.action.value}"


def policy_grid(config: WorldConfig, energy_steps: int = 6) -> List[ThresholdPolicy]:
    """Enumerate the strategy space for ``config``.

    ``energy_steps`` sets how finely the energy threshold is sampled between 0
    and ``max_energy``. The mismatch threshold is enumerated exhaustively, since
    it takes only ``private_bits + 2`` distinct values.
    """
    if energy_steps < 2:
        raise ValueError("energy_steps must be at least 2")
    energies = [
        config.max_energy * k / (energy_steps - 1) for k in range(energy_steps)
    ]
    return [
        ThresholdPolicy(energy_threshold=e, mismatch_threshold=m)
        for e in energies
        for m in range(config.private_bits + 2)
    ]
