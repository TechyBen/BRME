"""Equilibrium solvers: BRME and a payoff-maximising control.

The framework's claim is comparative - that equilibrating on *memory
preservation* yields different, more noise-tolerant outcomes than equilibrating
on *payoff*. A comparison like that is only meaningful if both sides are solved
identically, so the solvers here differ in exactly one place: the objective each
agent best-responds on. Same strategy space, same search, same ensemble, same
seeds.

Objectives
----------
* ``identity_objective`` - ``I(identity; m_t)``, normalised. The BRME objective.
* ``literal_memory_objective`` - ``I(m_t; m_{t+1})`` exactly as the formalisation
  writes it. Retained so experiments can measure how badly it misbehaves.
* ``payoff_objective`` - mean energy held. The utility-maximising control, in the
  spirit of a Nash equilibrium over the same strategy space.

Ensembles
---------
Identity retention is only estimable across systems with *different* identities,
so every evaluation runs a scheduled ensemble of signature assignments rather
than a single rollout. The schedule gives each agent a uniform marginal over all
possible signatures while keeping agents distinct from one another, so the
estimator sees a well-conditioned contingency table instead of whatever a random
draw happened to produce.

Best-response dynamics need not converge. Cycles are detected and reported rather
than silently truncated: a cycle is a real result about the game.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Callable, List, Sequence, Tuple

from .field import RolloutResult, WorldConfig, rollout
from .information import identity_retention, memory_preservation
from .policies import ThresholdPolicy, policy_grid

__all__ = [
    "Ensemble",
    "Objective",
    "identity_objective",
    "literal_memory_objective",
    "payoff_objective",
    "signature_schedule",
    "run_ensemble",
    "evaluate",
    "best_response",
    "solve_equilibrium",
    "EquilibriumResult",
]

Objective = Callable[[Sequence[RolloutResult], int, WorldConfig], float]


def signature_schedule(config: WorldConfig) -> List[List[Tuple[int, ...]]]:
    """All signature assignments used in one ensemble.

    Assignment ``k`` gives agent ``i`` the signature encoding ``(k + i * stride)``
    modulo the number of possible signatures. Over the full schedule each agent's
    signature is uniform across the space, and agents are offset from one another
    so they never share an identity when the space is large enough. Uniform
    marginals matter: they put the identity variable at full entropy, which is
    what makes ``I(identity; m_t)`` comparable across conditions.
    """
    bits = config.private_bits
    n_sigs = 1 << bits
    stride = max(1, n_sigs // max(1, config.n_agents))
    schedule: List[List[Tuple[int, ...]]] = []
    for k in range(n_sigs):
        assignment = []
        for i in range(config.n_agents):
            value = (k + i * stride) % n_sigs
            assignment.append(tuple((value >> b) & 1 for b in range(bits)))
        schedule.append(assignment)
    return schedule


@dataclass(frozen=True)
class Ensemble:
    """How thoroughly each policy profile is measured.

    ``steps`` is per rollout; the ensemble runs one rollout per signature
    assignment per seed, so the pooled sample count is
    ``len(signature_schedule) * len(seeds) * steps``.
    """

    steps: int = 250
    burn_in: int = 80
    seeds: Tuple[int, ...] = (11, 23)

    def sample_count(self, config: WorldConfig) -> int:
        return len(signature_schedule(config)) * len(self.seeds) * self.steps


DEFAULT_ENSEMBLE = Ensemble()


def run_ensemble(
    config: WorldConfig,
    profile: Sequence[ThresholdPolicy],
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
) -> List[RolloutResult]:
    """Run every (signature assignment, seed) pair for one policy profile."""
    if len(profile) != config.n_agents:
        raise ValueError(f"expected {config.n_agents} policies, got {len(profile)}")
    results: List[RolloutResult] = []
    for assignment in signature_schedule(config):
        for seed in ensemble.seeds:
            results.append(
                rollout(
                    config,
                    profile,
                    steps=ensemble.steps,
                    seed=seed,
                    burn_in=ensemble.burn_in,
                    signatures=assignment,
                )
            )
    return results


# -- objectives ------------------------------------------------------------


def identity_objective(
    results: Sequence[RolloutResult], i: int, config: WorldConfig
) -> float:
    """``I(identity; m_t)`` for agent ``i``, pooled across the ensemble.

    Returns a fraction of the private block's capacity, so 1.0 means the identity
    is perfectly recoverable from the current memory state and 0.0 means it has
    been erased.
    """
    identities: List[Tuple[int, ...]] = []
    states: List[Tuple[int, ...]] = []
    for result in results:
        trace = result.agents[i]
        identities.extend([trace.signature] * len(trace.private_states))
        states.extend(trace.private_states)
    return identity_retention(identities, states, max_bits=config.identity_capacity)


def literal_memory_objective(
    results: Sequence[RolloutResult], i: int, config: WorldConfig
) -> float:
    """``I(m_t; m_{t+1})`` exactly as the formalisation states it.

    Averaged over the ensemble. See ``information.memory_preservation`` for why
    this is degenerate as an objective; it is kept so the degeneracy can be
    measured rather than argued about.
    """
    if not results:
        return 0.0
    return sum(
        memory_preservation(r.agents[i].region_states, max_bits=config.region_capacity)
        for r in results
    ) / len(results)


def payoff_objective(
    results: Sequence[RolloutResult], i: int, config: WorldConfig
) -> float:
    """Mean energy held by agent ``i`` - the utility-maximising control."""
    if not results:
        return 0.0
    return sum(r.agents[i].mean_energy for r in results) / (
        len(results) * config.max_energy
    )


# -- solving ---------------------------------------------------------------


@dataclass
class EquilibriumResult:
    """Outcome of iterated best response."""

    profile: Tuple[ThresholdPolicy, ...]
    scores: Tuple[float, ...]
    converged: bool
    cycled: bool
    rounds: int
    history: List[Tuple[ThresholdPolicy, ...]] = dc_field(default_factory=list)

    @property
    def status(self) -> str:
        if self.converged:
            return "fixed-point"
        return "cycle" if self.cycled else "unconverged"


def evaluate(
    config: WorldConfig,
    profile: Sequence[ThresholdPolicy],
    objective: Objective,
    agent: int,
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
) -> float:
    """Score ``agent`` under ``profile`` over the full ensemble."""
    return objective(run_ensemble(config, profile, ensemble), agent, config)


def best_response(
    config: WorldConfig,
    profile: Sequence[ThresholdPolicy],
    agent: int,
    objective: Objective,
    grid: Sequence[ThresholdPolicy],
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
    tolerance: float = 0.005,
) -> Tuple[ThresholdPolicy, float]:
    """Exhaustively find ``agent``'s best response, holding others fixed.

    A challenger must beat the incumbent by more than ``tolerance`` to displace
    it. Without that margin, best-response dynamics chase differences smaller
    than the estimator's own noise and cycle forever between policies that are
    statistically indistinguishable.
    """
    working = list(profile)
    incumbent = working[agent]
    best_policy = incumbent
    incumbent_score = evaluate(config, working, objective, agent, ensemble)
    best_score = incumbent_score

    for candidate in grid:
        if candidate == incumbent:
            continue
        working[agent] = candidate
        score = evaluate(config, working, objective, agent, ensemble)
        if score > best_score:
            best_score = score
            best_policy = candidate
        working[agent] = incumbent

    if best_score - incumbent_score <= tolerance:
        return incumbent, incumbent_score
    return best_policy, best_score


def solve_equilibrium(
    config: WorldConfig,
    objective: Objective,
    initial: Sequence[ThresholdPolicy] | None = None,
    grid: Sequence[ThresholdPolicy] | None = None,
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
    max_rounds: int = 6,
    tolerance: float = 0.005,
) -> EquilibriumResult:
    """Iterate exact best responses until a fixed point or a repeated profile."""
    if grid is None:
        grid = policy_grid(config)
    if initial is None:
        initial = [grid[len(grid) // 2] for _ in range(config.n_agents)]
    profile = list(initial)

    seen = {tuple(profile)}
    history = [tuple(profile)]
    converged = False
    cycled = False
    rounds = 0

    for rounds in range(1, max_rounds + 1):
        changed = False
        for agent in range(config.n_agents):
            policy, _ = best_response(
                config, profile, agent, objective, grid, ensemble, tolerance
            )
            if policy != profile[agent]:
                profile[agent] = policy
                changed = True

        snapshot = tuple(profile)
        history.append(snapshot)

        if not changed:
            converged = True
            break
        if snapshot in seen:
            cycled = True
            break
        seen.add(snapshot)

    scores = tuple(
        evaluate(config, profile, objective, i, ensemble)
        for i in range(config.n_agents)
    )
    return EquilibriumResult(
        profile=tuple(profile),
        scores=scores,
        converged=converged,
        cycled=cycled,
        rounds=rounds,
        history=history,
    )
