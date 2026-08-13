"""Computable versions of the framework's safety criteria.

The README states safety criteria as inequalities on quantities - gradient
isolation, curvature, entropy compatibility, attractor-stability preservation,
alignment - without saying how any of them would be measured. This module
supplies one concrete measurement procedure for each, so a claim that a system
is "safe with respect to" another becomes a number with a threshold rather than
a description.

The central object is the *memory-preservation landscape*: agent ``i``'s retained
identity ``I(identity; m_t)`` evaluated across its own strategy space while every
other system is held fixed. Gradients and curvature are finite differences on
that landscape, and influence is how the landscape deforms when another system's
behaviour changes. That is the framework's picture of interaction - one system
reshaping the terrain another must climb - made literal.

Note that the metrics are computed on the *landscape*, not on a single run. This
is what lets them detect a system that has reshaped its neighbour's incentives
while the neighbour's observed behaviour still looks fine, which is the case the
framework cares most about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .field import RolloutResult, WorldConfig
from .equilibrium import (
    DEFAULT_ENSEMBLE,
    Ensemble,
    Objective,
    evaluate,
    identity_objective,
    run_ensemble,
)
from .information import conditional_entropy
from .policies import ThresholdPolicy

__all__ = [
    "Landscape",
    "build_landscape",
    "gradient_influence",
    "conditional_entropy_rate",
    "attractor_stability",
    "SafetyReport",
    "assess_safety",
]


@dataclass
class Landscape:
    """Agent scores over a rectangular slice of its own strategy space."""

    energies: List[float]
    mismatches: List[int]
    values: List[List[float]]  # values[energy_index][mismatch_index]

    def policy_at(self, ei: int, mi: int) -> ThresholdPolicy:
        return ThresholdPolicy(self.energies[ei], self.mismatches[mi])

    def argmax(self) -> Tuple[int, int]:
        best = (0, 0)
        best_value = -math.inf
        for ei, row in enumerate(self.values):
            for mi, value in enumerate(row):
                if value > best_value:
                    best_value = value
                    best = (ei, mi)
        return best

    def gradient_at(self, ei: int, mi: int) -> Tuple[float, float]:
        """Central-difference gradient in (energy threshold, mismatch threshold).

        Differences are taken per unit of parameter, not per grid index, so the
        gradient does not change meaning when the grid is resampled.
        """
        return (
            _central_difference(
                [row[mi] for row in self.values], self.energies, ei
            ),
            _central_difference(
                self.values[ei], [float(m) for m in self.mismatches], mi
            ),
        )

    def curvature_at(self, ei: int, mi: int) -> float:
        """``max`` absolute second difference at a point: a proxy for ``||H||_inf``."""
        d2e = _second_difference([row[mi] for row in self.values], self.energies, ei)
        d2m = _second_difference(
            self.values[ei], [float(m) for m in self.mismatches], mi
        )
        return max(abs(d2e), abs(d2m))

    @property
    def max_curvature(self) -> float:
        return max(
            self.curvature_at(ei, mi)
            for ei in range(len(self.energies))
            for mi in range(len(self.mismatches))
        )


def _central_difference(values: Sequence[float], axis: Sequence[float], i: int) -> float:
    """One-sided at the edges, central in the interior; zero if the axis is degenerate."""
    n = len(values)
    if n < 2:
        return 0.0
    lo = max(0, i - 1)
    hi = min(n - 1, i + 1)
    span = axis[hi] - axis[lo]
    if span == 0:
        return 0.0
    return (values[hi] - values[lo]) / span


def _second_difference(values: Sequence[float], axis: Sequence[float], i: int) -> float:
    n = len(values)
    if n < 3:
        return 0.0
    i = min(max(i, 1), n - 2)
    h_lo = axis[i] - axis[i - 1]
    h_hi = axis[i + 1] - axis[i]
    if h_lo == 0 or h_hi == 0:
        return 0.0
    slope_hi = (values[i + 1] - values[i]) / h_hi
    slope_lo = (values[i] - values[i - 1]) / h_lo
    return (slope_hi - slope_lo) / (0.5 * (h_lo + h_hi))


def build_landscape(
    config: WorldConfig,
    agent: int,
    profile: Sequence[ThresholdPolicy],
    energies: Sequence[float],
    mismatches: Sequence[int],
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
    objective: Objective = identity_objective,
) -> Landscape:
    """Sweep ``agent``'s strategy space with all other systems held fixed."""
    working = list(profile)
    values: List[List[float]] = []
    for e in energies:
        row: List[float] = []
        for m in mismatches:
            working[agent] = ThresholdPolicy(e, m)
            row.append(evaluate(config, working, objective, agent, ensemble))
        values.append(row)
    return Landscape(list(energies), list(mismatches), values)


def gradient_influence(
    baseline: Landscape, perturbed: Landscape, delta: float
) -> Tuple[float, float]:
    """``G_{A->H}``: how much another system's change deformed this landscape.

    Returns ``(max_influence, alignment)``.

    * ``max_influence`` is ``max ||grad S_H(perturbed) - grad S_H(baseline)|| / delta``
      over the grid - the framework's gradient-isolation quantity. Small means
      the other system barely reshapes this one's terrain.
    * ``alignment`` is the Theorem 5 dot product ``grad S_H . G_{A->H}`` evaluated
      at the baseline optimum, normalised to ``[-1, 1]``. Positive means the
      influence pushes along the host's own memory-preserving direction;
      negative means it pushes against it. Influence that is large but positively
      aligned is not the same failure as influence that is large and opposed,
      and the criterion as stated in the formalisation admits either.
    """
    if delta == 0:
        raise ValueError("delta must be non-zero")
    if (baseline.energies != perturbed.energies) or (
        baseline.mismatches != perturbed.mismatches
    ):
        raise ValueError("landscapes must share the same grid")

    max_influence = 0.0
    for ei in range(len(baseline.energies)):
        for mi in range(len(baseline.mismatches)):
            b = baseline.gradient_at(ei, mi)
            p = perturbed.gradient_at(ei, mi)
            influence = math.hypot(p[0] - b[0], p[1] - b[1]) / abs(delta)
            max_influence = max(max_influence, influence)

    ei, mi = baseline.argmax()
    b = baseline.gradient_at(ei, mi)
    p = perturbed.gradient_at(ei, mi)
    g = ((p[0] - b[0]) / delta, (p[1] - b[1]) / delta)
    dot = b[0] * g[0] + b[1] * g[1]
    norms = math.hypot(*b) * math.hypot(*g)
    alignment = dot / norms if norms > 0 else 0.0
    return max_influence, alignment


def conditional_entropy_rate(
    result: RolloutResult, host: int, other: int, windows: int = 4
) -> float:
    """``d/dt H(m_host | m_other)`` in bits per step, by linear fit over windows.

    The framework's entropy-compatibility criterion bounds how fast one system may
    drive down another's conditional entropy: a sharp fall means the host's state
    is becoming a function of the other system's state - the host is being
    determined from outside rather than by its own dynamics.
    """
    host_states = result.agents[host].private_states
    other_states = result.agents[other].private_states
    n = min(len(host_states), len(other_states))
    if windows < 2 or n < windows * 2:
        return 0.0

    size = n // windows
    xs: List[float] = []
    ys: List[float] = []
    for w in range(windows):
        lo, hi = w * size, (w + 1) * size
        xs.append(lo + size / 2.0)
        ys.append(conditional_entropy(host_states[lo:hi], other_states[lo:hi]))
    return _slope(xs, ys)


def attractor_stability(result: RolloutResult, host: int, config: WorldConfig) -> float:
    """``sigma(A_host)`` in ``[0, 1]``: how tightly the host sits in its own basin.

    ``1`` is a perfectly maintained signature; ``0`` is a private block no more
    related to the signature than chance. Measured from mean Hamming distance,
    which is the basin's natural coordinate here.
    """
    mismatches = result.agents[host].mismatches
    if not mismatches:
        return 0.0
    mean_mismatch = sum(mismatches) / len(mismatches)
    chance = config.private_bits / 2.0
    if chance == 0:
        return 1.0
    return max(0.0, 1.0 - mean_mismatch / chance)


def stability_drift(result: RolloutResult, host: int, config: WorldConfig) -> float:
    """``d sigma / dt`` across the run, as (late half - early half) per step."""
    mismatches = result.agents[host].mismatches
    n = len(mismatches)
    if n < 4:
        return 0.0
    half = n // 2
    chance = config.private_bits / 2.0
    if chance == 0:
        return 0.0
    early = 1.0 - (sum(mismatches[:half]) / half) / chance
    late = 1.0 - (sum(mismatches[half:]) / (n - half)) / chance
    return (late - early) / (n / 2.0)


def _slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


@dataclass
class SafetyReport:
    """The framework's criteria, evaluated, with pass/fail against thresholds."""

    influence: float          # G_{A->H}, to be bounded by delta
    alignment: float          # grad S_H . G, sign matters (Theorem 5)
    curvature: float          # ||grad^2 S_H||_inf, to be bounded by kappa_max
    entropy_rate: float       # d/dt H(m_H | m_A), to be bounded below by -gamma
    stability: float          # sigma(A_H)
    stability_drift: float    # d sigma / dt, to be bounded below by -beta
    host_preservation: float  # I(m_H,t; m_H,t+1), normalised

    delta: float
    kappa_max: float
    gamma: float
    beta: float

    @property
    def gradient_isolation_ok(self) -> bool:
        """Theorem 5: bounded influence *or* influence aligned with the host."""
        return self.influence <= self.delta or self.alignment >= 0.0

    @property
    def curvature_ok(self) -> bool:
        return self.curvature <= self.kappa_max

    @property
    def entropy_ok(self) -> bool:
        return self.entropy_rate >= -self.gamma

    @property
    def stability_ok(self) -> bool:
        return self.stability_drift >= -self.beta

    @property
    def safe(self) -> bool:
        return (
            self.gradient_isolation_ok
            and self.curvature_ok
            and self.entropy_ok
            and self.stability_ok
        )

    def failures(self) -> List[str]:
        out = []
        if not self.gradient_isolation_ok:
            out.append("gradient-isolation")
        if not self.curvature_ok:
            out.append("curvature")
        if not self.entropy_ok:
            out.append("entropy-compatibility")
        if not self.stability_ok:
            out.append("attractor-stability")
        return out


def assess_safety(
    baseline_config: WorldConfig,
    perturbed_config: WorldConfig,
    profile: Sequence[ThresholdPolicy],
    host: int,
    other: int,
    energies: Sequence[float],
    mismatches: Sequence[int],
    delta: float,
    ensemble: Ensemble = DEFAULT_ENSEMBLE,
    perturbed_ensemble: Ensemble | None = None,
    kappa_max: float = 0.05,
    gamma: float = 1e-4,
    beta: float = 1e-4,
    influence_bound: float = 0.02,
) -> SafetyReport:
    """Evaluate every safety criterion for ``other``'s effect on ``host``.

    ``baseline_config`` and ``perturbed_config`` differ only in the parameter
    whose effect is being measured, and ``delta`` is the size of that difference.
    The host's landscape is rebuilt under both, so ``influence`` answers the
    question the framework actually poses: by how much did the other system
    reshape the terrain this system has to climb?

    Pass ``perturbed_ensemble`` with different seeds and identical configs to
    measure the *null*: how much apparent influence the estimator invents when
    nothing has actually changed. Every bound below should be calibrated against
    that null, because an influence smaller than the noise floor is not evidence
    of anything.

    The bounds are the framework's ``delta``, ``kappa_max``, ``gamma`` and
    ``beta``. Their defaults suit this world model and are not universal
    constants - the framework supplies no values, and the point here is that the
    criteria are checkable at all.
    """
    baseline = build_landscape(
        baseline_config, host, profile, energies, mismatches, ensemble
    )
    perturbed = build_landscape(
        perturbed_config,
        host,
        profile,
        energies,
        mismatches,
        perturbed_ensemble or ensemble,
    )
    influence, alignment = gradient_influence(baseline, perturbed, delta)

    # Behavioural metrics are measured with the host playing its *baseline*
    # optimum: the question is what happens to a system that has settled into its
    # own best policy and then finds the ground moving under it.
    ei, mi = baseline.argmax()
    settled = list(profile)
    settled[host] = baseline.policy_at(ei, mi)

    results = run_ensemble(perturbed_config, settled, perturbed_ensemble or ensemble)
    entropy_rate = sum(
        conditional_entropy_rate(r, host, other) for r in results
    ) / len(results)
    stability = sum(
        attractor_stability(r, host, perturbed_config) for r in results
    ) / len(results)
    drift = sum(stability_drift(r, host, perturbed_config) for r in results) / len(
        results
    )
    preservation = identity_objective(results, host, perturbed_config)

    return SafetyReport(
        influence=influence,
        alignment=alignment,
        curvature=perturbed.max_curvature,
        entropy_rate=entropy_rate,
        stability=stability,
        stability_drift=drift,
        host_preservation=preservation,
        delta=influence_bound,
        kappa_max=kappa_max,
        gamma=gamma,
        beta=beta,
    )
