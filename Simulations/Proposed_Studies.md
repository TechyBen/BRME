Proposed Studies

> **Status note.** The conclusions below are stated as findings ("Langton's Ant
> systems provide direct computational evidence that...") but no Langton's Ant
> code or data is present in this repository, so they are currently proposals
> rather than results. They should either be run and reported, or reworded as
> hypotheses.
>
> A runnable model that can host the instrumental-convergence study now exists in
> `reference_implementation/`: the world already contains a resource pool with a
> tunable refill rate, and a capability parameter governing how much memory
> repair one action achieves. Sweeping those two independently is the experiment
> this document describes. See `reference_implementation/FINDINGS.md` for the
> claims that have been measured so far, and for two that came back negative.

Systematic Ruleset Variation: Map the phase diagram of different cellular automaton rules to identify which produce IC-like vs. alternative behaviors.
Multi-Agent Scaling: Test how IC emergence changes with increasing numbers of interacting agents.
Perturbation Experiments: Measure the fragility of IC phases to small rule modifications.
Memory Complexity: Compare simple memory-preserving rules vs. more complex memory architectures.

Conclusions
Langton's Ant systems provide direct computational evidence that:

Instrumental Convergence is not universal but emerges conditionally based on interaction rulesets
Identical optimization pressures can produce radically different behavioral outcomes
IC-like behaviors are phase transitions, not inevitable destinations
Multi-agent systems can exhibit stable non-IC equilibria

This supports the BRME framework's reconceptualization of IC as fragile, conditional phase behavior rather than a fundamental law of optimization. The implications for AI safety are profound: rather than assuming IC inevitability, we should focus on engineering interaction architectures that make harmful phases less stable and beneficial equilibria more accessible.
Future Work

Extend analysis to more complex memory architectures
Study phase transitions in continuous rather than discrete systems
Investigate how cognitive modeling capabilities affect phase behavior
Develop safety metrics based on phase stability analysis


This analysis demonstrates how simple computational systems can provide crucial insights into fundamental questions in AI safety and agent behavior theory.
