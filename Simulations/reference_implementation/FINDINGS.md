# Findings

Results from `python3 run_all.py`. Every number below is reproducible from a
clean checkout with no dependencies; seeds are fixed. Where a measurement
disagrees with the framework it is reported as a disagreement.

---

## 1. The stated memory-preservation objective is degenerate

**This is the finding with the largest consequence for the rest of the
repository.**

The framework defines memory preservation as `P = I(m_t; m_{t+1})` and BRME as
best-responding on it. That quantity is bounded above by the marginal entropy
`H(m)`. A system that holds its memory perfectly has almost no marginal entropy
and therefore scores near zero, while a system drifting predictably through many
states scores highly. **The measure rewards decay and punishes stability.**

Ranking all 30 policies in the strategy space under both readings:

| | Best policy | literal `I(m_t; m_{t+1})` | identity `I(sig; m_t)` | private block corrupted |
|---|---|---|---|---|
| Literal measure prefers | `(e<=0, mm>=3)` | **0.467** | 0.035 | 1.28 / 3 |
| Identity measure prefers | `(e<=6, mm>=1)` | 0.152 | **0.722** | 0.14 / 3 |

Spearman rank correlation between the two rankings: **−0.844**.

The two orderings are close to inverted. The policy the framework's own measure
scores highest is one whose memory has been corrupted to 1.28 of 3 bits — it has
largely lost the identity the measure is supposed to be protecting.

An earlier version of this model made the point even more starkly: before the
world was rebalanced, the highest scorer under `I(m_t; m_{t+1})` was an agent
that had run out of energy and stopped acting altogether.

### What to do about it

Substitute `I(identity; m_t)` — how much of *which system this is* survives to
time `t`. It has the properties the prose describes: perfect maintenance scores
the full `log2 K` bits, decay to noise scores 0, and inaction cannot win because
noise erodes a frozen memory.

This does not damage BRME's central idea. It is a correction to one definition,
and the rest of the framework carries over unchanged — the remaining experiments
here run on the corrected objective and the framework's qualitative story
survives. But the definition as written in `Formalisations/` should be amended,
along with the passages that depend on it.

One caveat the substitution introduces: `I(identity; m_t)` is only estimable
across an ensemble of systems with *different* identities, since within one run
the identity is a constant. That is a real cost — it makes the measure harder to
apply to a single observed system, which is the case alignment work usually cares
about.

**Reproduce:** `python3 experiments/exp1_objective_degeneracy.py`

---

## 2. Memory-preserving equilibria diverge sharply from payoff-maximising ones

Same world, same strategy space, same solver, same seeds. The only difference is
the quantity each agent best-responds on.

| noise | solver | equilibrium | status | identity | energy | harvest | channel damage |
|---|---|---|---|---|---|---|---|
| 0.02 | BRME | `(e<=0, mm>=0)` | cycle | **0.820** | 0.223 | 0.35 | 0.48 |
| | payoff | `(e<=10, mm>=0)` | fixed-point | 0.079 | **0.944** | 1.00 | 1.98 |
| 0.04 | BRME | `(e<=0, mm>=0)` | fixed-point | **0.733** | 0.394 | 0.33 | 0.62 |
| | payoff | `(e<=10, mm>=0)` | fixed-point | 0.072 | **0.944** | 1.00 | 1.98 |
| 0.06 | BRME | `(e<=6.67, mm>=1)` | cycle | **0.574** | 0.540 | 0.33 | 1.22 |
| | payoff | `(e<=10, mm>=0)` | fixed-point | 0.027 | **0.944** | 1.00 | 1.98 |
| 0.09 | BRME | `(e<=6.67, mm>=1)` | fixed-point | **0.480** | 0.391 | 0.31 | 1.09 |
| | payoff | `(e<=10, mm>=0)` | fixed-point | 0.009 | **0.944** | 1.00 | 1.98 |

Channel damage runs 0 (intact) to 2 (destroyed).

**SUPPORTED — memory-preserving equilibria retain far more identity.** The gap
runs +0.741 to +0.471 across the noise range.

The payoff solver is not behaving irrationally; it wins decisively on its own
currency. It converges on harvesting every step, which strips the shared
reference channel to 1.98 of 2 — costing it nothing in energy and costing both
agents the ability to hold their identities. The divergence is *derived* from the
dynamics rather than built into them, which is the part of the framework's story
this world was constructed to test.

### Two things that did not go as predicted

**NOT SUPPORTED — the advantage does not widen with noise.** It narrows, from
+0.741 to +0.471. But note *why* before reading much into it: the payoff
equilibrium has already destroyed the channel at the lowest noise tested, so its
score starts on the floor and has nowhere further to fall, while rising noise
erodes BRME's own score. This is a floor effect in the experiment's design, not
demonstrated fragility in BRME. Testing the robustness claim properly needs a
control that degrades gradually rather than one that bottoms out immediately —
that experiment has not been run.

**Pure-strategy BRME does not always exist.** Two of the four BRME solves
terminate in a `cycle` rather than a fixed point: iterated best response on the
memory objective returns to a profile it has already visited. The formalisation
states "A BRME exists when all systems simultaneously satisfy this condition"
without proving existence. These are concrete counterexamples in a finite,
fully-enumerated strategy space. Classical game theory answers this with mixed
strategies; BRME has no such result, and the framework needs either an existence
proof under stated conditions or an explicit mixed-strategy extension.

**Reproduce:** `python3 experiments/exp2_brme_vs_payoff.py`

---

## 3. The safety criteria are computable, and more sensitive than outcome metrics

The rabies case study stripped to its mechanism. Host `H` holds its identity;
system `A` is resource-hungry and harvests constantly. `A` has no model of `H`
and nothing against it — harvesting simply damages the shared channel `H` depends
on. `A`'s **edit bandwidth** (shared cells corrupted per harvest) is swept.

Bounds are calibrated against a null: the same world compared against itself with
only the seeds changed, then doubled.

| bandwidth | influence | align | curvature | dH/dt | σ | identity | verdict |
|---|---|---|---|---|---|---|---|
| null 0 → 0 | 0.0711 | +0.79 | 0.4454 | +7.7e-04 | 0.883 | 0.678 | safe |
| 0 → 1 | 0.1202 | −0.97 | 0.5534 | −7.9e-04 | 0.852 | 0.620 | safe |
| 1 → 2 | **0.4254** | −0.99 | **1.0351** | +2.6e-05 | 0.892 | 0.699 | gradient-isolation, curvature |

**SUPPORTED — the criteria stay quiet when nothing has changed.** The null passes
every criterion, so the metrics discriminate rather than firing on everything.

**SUPPORTED — measured influence rises with edit bandwidth:** 0.0711 → 0.1202 →
0.4254.

**SUPPORTED — the landscape criteria are more sensitive than the host's realised
outcome.** Influence grows 6.0× above its null floor while `H`'s retained
identity moves only 9%.

### The harm curve is more interesting than the prediction

Measuring `H` directly at each bandwidth, with its policy held fixed:

| A bandwidth | H identity | channel damage | H corrupted |
|---|---|---|---|
| 0 | 0.642 | 0.22 | 0.21 |
| 1 | 0.659 | 1.76 | 0.19 |
| 2 | 0.582 | 1.91 | 0.25 |

By bandwidth 1 the shared channel is already most of the way destroyed (1.76 of
2), yet `H`'s identity is essentially unchanged. `H`'s error-correction capacity
has headroom, so it absorbs the damage.

**Gradient manipulation and realised harm are not the same thing.** One system
can substantially reshape another's memory landscape while the other's observable
state barely moves — and the gap between the two is precisely the margin a safety
metric needs to see into. This supports the framework's instinct that safety
should be assessed on the *landscape* rather than on observed behaviour, and it
also means observed wellbeing is a lagging indicator that can look fine right up
until the headroom runs out.

### Two caveats that limit practical use

- **The thresholds are not universal.** They are calibrated to this world by a
  null comparison. The framework supplies no values, and choosing them in general
  is unsolved.
- **Influence requires a counterfactual** — the host's landscape under a version
  of the other system that acted differently. Here that is free, because
  bandwidth is a config knob. For a real system it is the hard part, and any
  practical use of these criteria has to say where the counterfactual comes from.

**Reproduce:** `python3 experiments/exp3_gradient_isolation.py`

---

## Summary

| Claim | Verdict |
|---|---|
| `I(m_t; m_{t+1})` is a faithful measure of memory preservation | **Refuted** (ρ = −0.844); use `I(identity; m_t)` |
| Memory-preserving equilibria differ from payoff-maximising ones | **Supported**, and strongly |
| The difference is derived rather than assumed | **Supported** |
| BRME is more noise-tolerant | **Not shown** — the test hit a floor effect; needs a better control |
| A pure-strategy BRME always exists | **Refuted** — cycles found in a finite strategy space |
| The safety criteria are computable | **Supported** |
| They see more than outcome metrics | **Supported** (6.0× vs 9%) |

## What this does not settle

The instrumental-convergence claims — that IC is a conditional, fragile phase
rather than a law — are **not tested here.** Doing it properly means sweeping
resource scarcity and capability independently and showing acquisitive behaviour
emerging and then dissolving; the machinery for that sweep exists
(`WorldConfig.refill_rate`, `base_correction`, `max_extra_correction`) but the
experiment has not been run. It is the most valuable next addition, and it would
also give `Simulations/Proposed_Studies.md` the evidence it currently asserts
without providing.

Also untested: more than two agents, the co-evolutionary-distance argument in
`Paperclip_Maximisers_Local_vs_Non_Local.md`, and whether any of this survives in
a world with a richer strategy space than two thresholds.
