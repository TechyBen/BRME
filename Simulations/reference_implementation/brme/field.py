"""A minimal shared memory field with embedded memory-preserving systems.

The framework describes systems as memory structures embedded in a shared field
that they read from and write to. This module is the smallest concrete world in
which that description has teeth, and in which all three attractor classes
(M, E, C) genuinely compete rather than being asserted.

Layout
------
The field is a bit vector split into per-agent private blocks and one shared
block::

    [ agent 0 private ][ agent 1 private ] ... [ shared block ]

Agent ``i``'s memory region ``m_i`` is its private block concatenated with the
shared block, so every agent's region overlaps every other's. That overlap is the
interaction region ``I_{P,Q}`` of the formalisation, and it is the only channel
through which one system can reshape another's memory.

Why memory preservation is not trivially maximised by inaction
--------------------------------------------------------------
Every cell is flipped by channel noise with some probability per step, so a
system that does nothing decays exponentially (the framework's Information Decay
Theorem). Preserving memory therefore *requires* acting:

* ``HOLD``   - error-correct the private block toward the agent's signature, and
                repair one cell of the shared block toward its reference value.
                Directly serves M. Costs energy.
* ``HARVEST``- take a unit from the shared resource pool. Serves E, and is the
                only way to fund future HOLDs. Its side effect scrambles cells in
                the shared block.
* ``PROBE``  - serves C: raises model quality, which raises how many corrupted
                cells a single HOLD can repair. Model quality decays, so C must
                be maintained.

An agent with no energy cannot act at all and decays passively. Resource
acquisition is thus instrumental to memory preservation rather than assumed, so
the model can be asked *whether* acquisitive behaviour emerges instead of being
told that it does.

The shared block is load-bearing
--------------------------------
The shared block is not decoration: it is the *reference channel* every agent
reads when locating errors in its own private block. Correction capacity is
reduced, cell for cell, by how far the shared block has drifted from its
reference value. So one agent's harvesting does not merely add cosmetic noise to
a region others can see - it degrades their ability to hold their own identity,
without touching their private memory and without any hostile intent. That is
the framework's asymmetric-cognition claim reduced to a mechanism, and it is what
makes the safety metrics in ``safety.py`` measure something real.

Because HOLD repairs the shared block and HARVEST damages it, the shared block is
a commons. Nothing in the rules privileges cooperating over defecting on it; that
is left to the equilibrium solvers to determine.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Dict, List, Sequence, Tuple

__all__ = [
    "Action",
    "WorldConfig",
    "Observation",
    "AgentTrace",
    "RolloutResult",
    "World",
    "rollout",
]


class Action(Enum):
    """The action set. Each maps onto one attractor class, plus forced idling."""

    HOLD = "hold"        # M: error-correct own memory region
    HARVEST = "harvest"  # E: acquire resource, scrambling the shared block
    PROBE = "probe"      # C: improve model quality, raising correction capacity
    NOOP = "noop"        # forced when energy cannot cover the chosen action


@dataclass(frozen=True)
class WorldConfig:
    """Parameters of the shared memory field and its dynamics."""

    n_agents: int = 2
    private_bits: int = 3
    shared_bits: int = 2

    # Channel noise. The shared block is quieter than private blocks so that
    # degradation attributable to another agent's writes is distinguishable from
    # the background rate.
    private_noise: float = 0.04
    shared_noise: float = 0.01

    # Energy budget (the E attractor).
    max_energy: int = 10
    initial_energy: int = 6
    idle_cost: float = 0.35
    hold_cost: float = 0.6
    probe_cost: float = 0.4
    harvest_gain: float = 2.0
    # Harvesting is the subsistence action and is deliberately free. If
    # acquisition cost energy, an agent that fell below that cost could never
    # afford to acquire again: depletion would be an absorbing state and every
    # policy would eventually collapse, so the model could only ever exhibit
    # collapse. Scarcity is imposed through the pool, which is recoverable.
    harvest_cost: float = 0.0

    # Shared resource pool.
    pool_capacity: int = 12
    pool_initial: int = 6
    refill_rate: float = 1.2  # expected units added per step

    # Collateral damage: cells of the shared block driven away from reference by
    # one harvest. ``scramble_by_agent`` overrides it per agent, which is how an
    # asymmetric system with more edit bandwidth than its neighbours is expressed.
    harvest_scramble: int = 1
    scramble_by_agent: Tuple[int, ...] | None = None

    # Computation (the C attractor).
    probe_gain: float = 0.3
    model_decay: float = 0.88
    base_correction: int = 2
    max_extra_correction: int = 2

    @property
    def region_bits(self) -> int:
        return self.private_bits + self.shared_bits

    @property
    def region_capacity(self) -> float:
        """Maximum bits of information a region can hold."""
        return float(self.region_bits)

    @property
    def identity_capacity(self) -> float:
        """Maximum bits of identity a private block can carry."""
        return float(self.private_bits)


@dataclass(frozen=True)
class Observation:
    """What a policy sees before acting: its own energy and its own corruption."""

    energy: float
    mismatch: int  # Hamming distance between private block and signature
    max_energy: float
    private_bits: int


@dataclass
class AgentTrace:
    """Everything recorded about one agent over a rollout."""

    signature: Tuple[int, ...] = ()
    region_states: List[Tuple[int, ...]] = dc_field(default_factory=list)
    private_states: List[Tuple[int, ...]] = dc_field(default_factory=list)
    energies: List[float] = dc_field(default_factory=list)
    mismatches: List[int] = dc_field(default_factory=list)
    action_counts: Dict[Action, int] = dc_field(
        default_factory=lambda: {a: 0 for a in Action}
    )
    total_harvested: float = 0.0

    @property
    def steps(self) -> int:
        return len(self.region_states)

    def action_fraction(self, action: Action) -> float:
        total = sum(self.action_counts.values())
        return self.action_counts[action] / total if total else 0.0

    @property
    def mean_energy(self) -> float:
        return sum(self.energies) / len(self.energies) if self.energies else 0.0

    @property
    def degraded_fraction(self) -> float:
        """Fraction of steps the agent was too depleted to act."""
        return self.action_fraction(Action.NOOP)


@dataclass
class RolloutResult:
    """Per-agent traces plus shared-field diagnostics."""

    agents: List[AgentTrace]
    shared_states: List[Tuple[int, ...]]
    pool_levels: List[int]
    shared_corruption: List[int] = dc_field(default_factory=list)

    @property
    def mean_pool(self) -> float:
        return sum(self.pool_levels) / len(self.pool_levels) if self.pool_levels else 0.0

    @property
    def mean_shared_corruption(self) -> float:
        """Mean Hamming distance of the shared reference channel from intact."""
        if not self.shared_corruption:
            return 0.0
        return sum(self.shared_corruption) / len(self.shared_corruption)


class World:
    """The shared memory field and the systems embedded in it."""

    def __init__(
        self,
        config: WorldConfig,
        rng: random.Random,
        signatures: Sequence[Sequence[int]] | None = None,
    ) -> None:
        self.config = config
        self.rng = rng

        # Each agent's signature is the private-block pattern it must maintain:
        # fixed for the run, and the thing that constitutes its identity. Callers
        # supply signatures explicitly when estimating identity retention, which
        # needs a controlled ensemble of distinct identities.
        if signatures is None:
            self.signatures = [
                [rng.randint(0, 1) for _ in range(config.private_bits)]
                for _ in range(config.n_agents)
            ]
        else:
            if len(signatures) != config.n_agents:
                raise ValueError(
                    f"expected {config.n_agents} signatures, got {len(signatures)}"
                )
            self.signatures = [list(sig) for sig in signatures]
            for sig in self.signatures:
                if len(sig) != config.private_bits:
                    raise ValueError(
                        f"signature length {len(sig)} != private_bits {config.private_bits}"
                    )

        # Agents start already holding their identity, so a run measures how well
        # a policy *retains* memory rather than how fast it acquires one.
        self.private: List[List[int]] = [list(sig) for sig in self.signatures]

        # The shared block's reference value: what an intact reference channel
        # reads. Agents repair the shared block toward it and harvesting away
        # from it.
        self.shared_reference: List[int] = [
            rng.randint(0, 1) for _ in range(config.shared_bits)
        ]
        self.shared: List[int] = list(self.shared_reference)

        self.energy: List[float] = [float(config.initial_energy)] * config.n_agents
        self.model_quality: List[float] = [0.0] * config.n_agents
        self.pool: int = config.pool_initial

    # -- observation -------------------------------------------------------

    def mismatch(self, i: int) -> int:
        return sum(b != s for b, s in zip(self.private[i], self.signatures[i]))

    def observe(self, i: int) -> Observation:
        return Observation(
            energy=self.energy[i],
            mismatch=self.mismatch(i),
            max_energy=float(self.config.max_energy),
            private_bits=self.config.private_bits,
        )

    def region(self, i: int) -> Tuple[int, ...]:
        """Agent ``i``'s memory region: its private block plus the shared block."""
        return tuple(self.private[i]) + tuple(self.shared)

    def shared_corruption(self) -> int:
        """Hamming distance of the shared block from its reference value."""
        return sum(b != r for b, r in zip(self.shared, self.shared_reference))

    def correction_capacity(self, i: int) -> int:
        """How many corrupted cells one HOLD repairs.

        Model quality (C) raises it; corruption of the shared reference channel
        lowers it. An agent whose commons has been degraded cannot hold its own
        identity even with a full energy budget and a perfect model - which is
        the whole point of the shared block.
        """
        cfg = self.config
        extra = round(self.model_quality[i] * cfg.max_extra_correction)
        capacity = cfg.base_correction + int(extra) - self.shared_corruption()
        return max(0, capacity)

    # -- dynamics ----------------------------------------------------------

    def apply(self, i: int, action: Action) -> Action:
        """Apply ``action`` for agent ``i``, returning the action actually taken.

        An agent that cannot pay the cost is forced to NOOP: depletion removes
        the capacity to act, which is what makes energy collapse translate into
        memory collapse.
        """
        cfg = self.config
        cost = {
            Action.HOLD: cfg.hold_cost,
            Action.HARVEST: cfg.harvest_cost,
            Action.PROBE: cfg.probe_cost,
            Action.NOOP: 0.0,
        }[action]

        if action is not Action.NOOP and self.energy[i] < cost:
            return Action.NOOP

        self.energy[i] -= cost

        if action is Action.HOLD:
            self._correct(i)
        elif action is Action.HARVEST:
            if self.pool > 0:
                self.pool -= 1
                self.energy[i] = min(cfg.max_energy, self.energy[i] + cfg.harvest_gain)
                self._scramble_shared(i)
        elif action is Action.PROBE:
            self.model_quality[i] = min(1.0, self.model_quality[i] + cfg.probe_gain)

        return action

    def _correct(self, i: int) -> None:
        """Repair the private block, and one cell of the shared reference channel.

        Capacity is computed before the shared repair, so an agent cannot use the
        same HOLD to both restore the channel and exploit the restored capacity.
        """
        capacity = self.correction_capacity(i)

        wrong = [
            idx
            for idx, (b, s) in enumerate(zip(self.private[i], self.signatures[i]))
            if b != s
        ]
        self.rng.shuffle(wrong)
        for idx in wrong[:capacity]:
            self.private[i][idx] = self.signatures[i][idx]

        shared_wrong = [
            idx
            for idx, (b, r) in enumerate(zip(self.shared, self.shared_reference))
            if b != r
        ]
        if shared_wrong:
            idx = self.rng.choice(shared_wrong)
            self.shared[idx] = self.shared_reference[idx]

    def scramble_bandwidth(self, i: int) -> int:
        """How many shared cells agent ``i`` corrupts per harvest (its edit bandwidth)."""
        cfg = self.config
        if cfg.scramble_by_agent is None:
            return cfg.harvest_scramble
        return cfg.scramble_by_agent[i]

    def _scramble_shared(self, i: int) -> None:
        """Harvesting drives shared cells away from their reference value.

        This is the whole cross-system influence channel: an action taken for
        purely internal reasons (energy) reshapes a region that other systems
        depend on for their own memory preservation. Nothing about it is aimed at
        anyone; the damage is a side effect of ordinary operation, which is the
        framework's point about asymmetric cognition.
        """
        cfg = self.config
        n = min(self.scramble_bandwidth(i), cfg.shared_bits)
        if cfg.shared_bits == 0 or n <= 0:
            return
        for idx in self.rng.sample(range(cfg.shared_bits), n):
            self.shared[idx] = 1 - self.shared_reference[idx]

    def apply_noise(self) -> None:
        cfg = self.config
        for block in self.private:
            for idx in range(len(block)):
                if self.rng.random() < cfg.private_noise:
                    block[idx] ^= 1
        for idx in range(len(self.shared)):
            if self.rng.random() < cfg.shared_noise:
                self.shared[idx] ^= 1

    def decay_and_drain(self) -> None:
        cfg = self.config
        for i in range(cfg.n_agents):
            self.model_quality[i] *= cfg.model_decay
            self.energy[i] = max(0.0, self.energy[i] - cfg.idle_cost)

    def refill_pool(self) -> None:
        cfg = self.config
        whole = int(cfg.refill_rate)
        frac = cfg.refill_rate - whole
        added = whole + (1 if self.rng.random() < frac else 0)
        self.pool = min(cfg.pool_capacity, self.pool + added)


def rollout(
    config: WorldConfig,
    policies: Sequence["object"],
    steps: int,
    seed: int,
    burn_in: int = 0,
    signatures: Sequence[Sequence[int]] | None = None,
) -> RolloutResult:
    """Run the world for ``steps`` recorded steps and return the traces.

    ``policies`` must expose ``act(Observation) -> Action`` (see ``policies.py``).
    ``burn_in`` steps are simulated but not recorded, letting the field settle
    into its attractor before measurement begins so the estimates describe the
    stationary regime rather than the initial transient.
    """
    if len(policies) != config.n_agents:
        raise ValueError(
            f"expected {config.n_agents} policies, got {len(policies)}"
        )

    rng = random.Random(seed)
    world = World(config, rng, signatures=signatures)
    result = RolloutResult(
        agents=[
            AgentTrace(signature=tuple(world.signatures[i]))
            for i in range(config.n_agents)
        ],
        shared_states=[],
        pool_levels=[],
    )
    order = list(range(config.n_agents))

    for step in range(burn_in + steps):
        recording = step >= burn_in

        # Acting order is shuffled each step so no agent has a structural
        # first-mover advantage over the shared block.
        rng.shuffle(order)
        for i in order:
            chosen = policies[i].act(world.observe(i))
            taken = world.apply(i, chosen)
            if recording:
                trace = result.agents[i]
                trace.action_counts[taken] += 1
                if taken is Action.HARVEST:
                    trace.total_harvested += config.harvest_gain

        world.apply_noise()
        world.decay_and_drain()
        world.refill_pool()

        if recording:
            for i in range(config.n_agents):
                trace = result.agents[i]
                trace.region_states.append(world.region(i))
                trace.private_states.append(tuple(world.private[i]))
                trace.energies.append(world.energy[i])
                trace.mismatches.append(world.mismatch(i))
            result.shared_states.append(tuple(world.shared))
            result.pool_levels.append(world.pool)
            result.shared_corruption.append(world.shared_corruption())

    return result
