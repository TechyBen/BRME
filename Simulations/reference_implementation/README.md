# BRME Reference Implementation

A runnable model of the BRME framework, built so its claims can be **measured and
refuted** rather than only described.

The rest of this repository states empirical claims — that instrumental
convergence is a conditional phase rather than a law, that memory-preserving
equilibria are more noise-tolerant than payoff-maximising ones, that the safety
criteria are computable — but contains no code. This directory closes that gap
for the claims that can be tested in a small world, and reports honestly where
the measurements disagree with the framework.

**Standard library only. No installation, no dependencies.**

```bash
cd Simulations/reference_implementation

python3 run_all.py              # every experiment (~90s)
python3 run_all.py --quick      # fast smoke check (~25s, noisier estimates)

python3 experiments/exp1_objective_degeneracy.py
python3 experiments/exp2_brme_vs_payoff.py
python3 experiments/exp3_gradient_isolation.py

python3 -m unittest discover -s tests -t .    # 82 tests, ~3s
```

Each experiment prints the question it asks, the prediction it tests, the
measurements, and a `[SUPPORTED]` / `[NOT SUPPORTED]` verdict. Two predictions
currently come back NOT SUPPORTED; see [`FINDINGS.md`](FINDINGS.md).

---

## The world model

The smallest world in which the framework's three attractor classes actually
compete instead of being asserted. The memory field is a bit vector:

```
[ agent 0 private ][ agent 1 private ][ shared block ]
```

Agent `i`'s memory region `m_i` is its private block plus the shared block, so
every region overlaps — that overlap is the interaction region `I_{P,Q}` of the
formalisation, and it is the only channel between systems.

Each agent has a fixed **signature**: the private-block pattern that constitutes
its identity. Channel noise flips cells every step, so an idle system decays
(the framework's Information Decay Theorem). Three actions, one per attractor
class:

| Action | Serves | Effect |
|---|---|---|
| `HOLD` | **M** | Error-corrects the private block toward the signature, and repairs one cell of the shared block. Costs energy. |
| `HARVEST` | **E** | Takes a unit from the shared pool. The only source of energy. Corrupts cells of the shared block. |
| `PROBE` | **C** | Raises model quality, which raises how many cells one `HOLD` can repair. Decays, so it must be maintained. |

**The shared block is load-bearing.** It is the reference channel every agent
reads to locate errors in its own memory: correction capacity is reduced, cell
for cell, by how far it has drifted from its reference value. So one system's
harvesting degrades another's ability to hold its own identity — without touching
its private memory, and without any hostile intent. That is the framework's
asymmetric-cognition claim reduced to a mechanism.

Because `HOLD` repairs the shared block and `HARVEST` damages it, the block is a
commons. Nothing in the rules says defecting on it is bad; the solvers are simply
asked what they converge to.

Two modelling choices worth stating plainly:

- **Harvesting is free.** If acquisition cost energy, an agent that fell below
  that cost could never afford to acquire again — depletion would be absorbing
  and every policy would eventually collapse, so the model could only ever
  exhibit collapse. Scarcity is imposed through the pool, which is recoverable.
- **Agents start holding their identity.** A run measures how well a policy
  *retains* memory, not how fast it acquires one.

## Modules

| File | Contents |
|---|---|
| `brme/information.py` | Entropy and mutual information with Miller–Madow bias correction; `memory_preservation` (the framework's stated measure) and `identity_retention` (the non-degenerate one). |
| `brme/field.py` | The memory field, the three actions, noise, energy, the shared reference channel, rollouts. |
| `brme/policies.py` | The enumerable strategy space, so best responses are exact rather than the output of a search that may have stalled. |
| `brme/equilibrium.py` | Ensembles, the three objectives, and iterated exact best response with cycle detection. |
| `brme/safety.py` | The memory-preservation landscape; gradient influence, curvature, entropy compatibility, attractor stability, and a `SafetyReport` with pass/fail. |

## Method notes

These are the choices the results depend on most.

**Identity retention needs an ensemble.** Within a single run the identity is a
constant, and mutual information with a constant is zero by construction. Every
evaluation therefore runs a scheduled ensemble of signature assignments, built so
each agent's marginal is uniform over the whole signature space. `tests/` pins
this.

**Bias correction is applied and tested.** Plug-in mutual information is biased
on finite samples, and every claim here is an MI *difference*, so an uncorrected
estimator would let sampling noise pass for an effect. `test_information.py`
checks that the correction reduces error rather than merely changing the number.

**Best responses need a margin.** A challenger must beat the incumbent by more
than a tolerance to displace it. Without that, best-response dynamics chase
differences smaller than the estimator's own noise and cycle indefinitely between
statistically indistinguishable policies.

**Safety bounds are calibrated against a null.** Experiment 3 first compares the
world against itself with only the seeds changed, which measures how much
apparent influence the estimator invents when nothing has changed. Bounds are set
to twice that floor. This matters: the null influence is a large fraction of the
real signal at this sample budget, so an uncalibrated threshold either fires on
everything or on nothing.

**Cycles are reported, not hidden.** Iterated best response need not converge.
When it doesn't, the solver says `cycle` — the framework asserts that a BRME
exists without proving it, and a cycle is a concrete counterexample.

## Limits

- One world model. The results characterise BRME's behaviour *here*; they do not
  establish how it behaves in general.
- Two agents, 3 private bits, 2 shared bits. Small enough that mutual information
  is estimable without a variational estimator, and small enough that multi-agent
  effects beyond pairwise interaction are out of reach.
- The strategy space is two thresholds. Rich enough to trade the three attractor
  classes against each other; far poorer than a learned policy.
- The safety thresholds are calibrated to this world. The framework supplies no
  values, and choosing them in general is unsolved.
- Measuring gradient influence needs a counterfactual — the host's landscape
  under a version of the other system that acted differently. Here that is a
  config knob. For a real system it is the hard part.

## Extending

Adding an experiment: write a script in `experiments/` that imports from
`_common` for output helpers and `--quick` handling, state the question and
prediction in `banner(...)`, and end with `verdict(...)` calls that can come back
negative. The point of the format is that a prediction can fail visibly.

Changing the world: `WorldConfig` is a frozen dataclass, so pass a modified copy
rather than mutating it. Anything that changes the balance between the attractor
classes should be checked against `tests/test_field.py`, which pins the
mechanisms the experiments rely on.
