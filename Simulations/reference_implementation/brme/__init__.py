"""A runnable reference implementation of the BRME framework.

The repository's prose makes empirical claims - that instrumental convergence is
a conditional phase rather than a law, that memory-preserving equilibria are more
noise-tolerant than payoff-maximising ones, that safety criteria are computable.
This package turns each of those into something that can be measured and, in
principle, refuted.

Standard library only, so ``python3 experiments/<name>.py`` runs anywhere.
"""

from .field import Action, AgentTrace, Observation, RolloutResult, World, WorldConfig, rollout
from .information import (
    conditional_entropy,
    entropy,
    identity_retention,
    memory_preservation,
    mutual_information,
    normalised_mutual_information,
)
from .policies import FixedPolicy, ThresholdPolicy, policy_grid
from .equilibrium import (
    DEFAULT_ENSEMBLE,
    Ensemble,
    EquilibriumResult,
    best_response,
    evaluate,
    identity_objective,
    literal_memory_objective,
    payoff_objective,
    run_ensemble,
    signature_schedule,
    solve_equilibrium,
)
from .safety import (
    Landscape,
    SafetyReport,
    attractor_stability,
    build_landscape,
    conditional_entropy_rate,
    gradient_influence,
    stability_drift,
)

__version__ = "0.1.0"

__all__ = [
    "Action",
    "AgentTrace",
    "DEFAULT_ENSEMBLE",
    "Ensemble",
    "EquilibriumResult",
    "FixedPolicy",
    "Landscape",
    "Observation",
    "RolloutResult",
    "SafetyReport",
    "ThresholdPolicy",
    "World",
    "WorldConfig",
    "attractor_stability",
    "best_response",
    "build_landscape",
    "conditional_entropy",
    "conditional_entropy_rate",
    "entropy",
    "evaluate",
    "gradient_influence",
    "identity_objective",
    "identity_retention",
    "literal_memory_objective",
    "memory_preservation",
    "mutual_information",
    "normalised_mutual_information",
    "payoff_objective",
    "policy_grid",
    "rollout",
    "run_ensemble",
    "signature_schedule",
    "solve_equilibrium",
    "stability_drift",
    "__version__",
]
