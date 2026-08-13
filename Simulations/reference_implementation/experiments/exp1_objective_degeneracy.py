"""Experiment 1: is ``I(m_t; m_{t+1})`` a usable objective?

The framework's central quantity is the mutual information between a system's
consecutive memory states, and BRME is defined as best-responding on it. This
experiment checks whether that quantity actually tracks what the prose says it
tracks - a system holding onto its identity.

It does not. The measure is bounded by the marginal entropy ``H(m)``, so a
system that holds its memory perfectly has almost nothing left to be informative
about and scores near zero, while a system decaying gently through many states
scores highly. The experiment quantifies the gap by ranking the whole strategy
space under both readings and correlating them.

Run:  python3 experiments/exp1_objective_degeneracy.py [--quick]
"""

from __future__ import annotations

from _common import Timer, banner, ensemble_for, section, table, verdict

from brme.field import Action, WorldConfig
from brme.equilibrium import (
    identity_objective,
    literal_memory_objective,
    run_ensemble,
)
from brme.policies import ThresholdPolicy, policy_grid


def spearman(xs, ys) -> float:
    """Rank correlation, the honest statistic when only the ordering matters."""

    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mean_rank = (i + j) / 2.0
            for k in range(i, j + 1):
                out[order[k]] = mean_rank
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (
        sum((a - mx) ** 2 for a in rx) ** 0.5 * sum((b - my) ** 2 for b in ry) ** 0.5
    )
    return num / den if den else 0.0


def main() -> None:
    banner(
        "EXPERIMENT 1 - Degeneracy of the stated memory-preservation objective",
        "Does I(m_t; m_{t+1}) rank policies by how well they preserve identity?",
        "It does not: the two rankings should be uncorrelated or inverted, and "
        "the\n            top-scoring policy under the literal measure should be a "
        "badly degraded one.",
    )

    config = WorldConfig()
    ensemble = ensemble_for()
    grid = policy_grid(config)

    rows = []
    literal_scores, identity_scores = [], []
    for policy in grid:
        results = run_ensemble(config, [policy, policy], ensemble)
        literal = literal_memory_objective(results, 0, config)
        identity = identity_objective(results, 0, config)
        mismatch = sum(
            sum(r.agents[0].mismatches) / len(r.agents[0].mismatches) for r in results
        ) / len(results)
        harvest = sum(
            r.agents[0].action_fraction(Action.HARVEST) for r in results
        ) / len(results)
        literal_scores.append(literal)
        identity_scores.append(identity)
        rows.append((policy, literal, identity, mismatch, harvest))

    section("Every policy, scored both ways")
    print(
        "  literal   = I(m_t; m_{t+1}) / region capacity, as the formalisation states it\n"
        "  identity  = I(signature; m_t) / private capacity, the intended meaning\n"
        "  corrupted = mean Hamming distance from the agent's own signature (lower is healthier)\n"
    )
    ranked = sorted(rows, key=lambda r: -r[1])
    table(
        ["policy", "literal", "identity", "corrupted", "harvest"],
        [
            (str(p), f"{lit:.3f}", f"{ident:.3f}", f"{mm:.2f}", f"{hv:.2f}")
            for p, lit, ident, mm, hv in ranked
        ],
    )

    rho = spearman(literal_scores, identity_scores)
    best_literal = max(rows, key=lambda r: r[1])
    best_identity = max(rows, key=lambda r: r[2])

    section("Result")
    print(f"  Spearman rank correlation (literal vs identity): {rho:+.3f}")
    print(
        f"  Best under literal measure:  {best_literal[0]}  "
        f"literal={best_literal[1]:.3f}  identity={best_literal[2]:.3f}  "
        f"corrupted={best_literal[3]:.2f}/{config.private_bits}"
    )
    print(
        f"  Best under identity measure: {best_identity[0]}  "
        f"literal={best_identity[1]:.3f}  identity={best_identity[2]:.3f}  "
        f"corrupted={best_identity[3]:.2f}/{config.private_bits}"
    )

    identity_gap = best_identity[2] - best_literal[2]
    verdict(
        "I(m_t; m_{t+1}) is a faithful objective for memory preservation",
        rho > 0.5,
        f"rank correlation with identity retention is {rho:+.3f}; the policy the "
        f"literal measure\n              prefers retains {identity_gap:.3f} less "
        f"identity than the policy that actually maximises it.",
    )
    print(
        "\n  Reading: the literal measure is capped by H(m), so it rewards a memory\n"
        "  that keeps changing predictably and penalises one that stays put. Every\n"
        "  other experiment here therefore best-responds on I(signature; m_t)\n"
        "  instead. This is a defect in the formalisation, not in BRME's idea:\n"
        "  substituting the identity form leaves the rest of the framework intact."
    )


if __name__ == "__main__":
    with Timer():
        main()
