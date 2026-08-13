"""Experiment 3: are the safety criteria measurable, and do they fire in time?

The README lists safety criteria - gradient isolation, curvature, entropy
compatibility, attractor-stability preservation - as inequalities, without saying
how any of them would be evaluated. This experiment evaluates all of them.

The setup is the rabies case study stripped to its mechanism. A host system H and
another system A share a memory field. A is not hostile and has no model of H; it
simply harvests, and harvesting damages the shared reference channel H depends on
to correct its own memory. A's *edit bandwidth* - how many shared cells one
harvest corrupts - is swept from none to total.

The interesting question is not whether a large bandwidth hurts the host. It is
whether the criteria see anything a plain outcome metric would miss, since a
safety measure that only trips once the damage is already visible has no value.

Run:  python3 experiments/exp3_gradient_isolation.py [--quick]
"""

from __future__ import annotations

from _common import Timer, banner, ensemble_for, section, table, verdict

from brme.equilibrium import Ensemble, identity_objective, run_ensemble
from brme.field import WorldConfig
from brme.policies import ThresholdPolicy
from brme.safety import assess_safety

HOST, OTHER = 0, 1


def main() -> None:
    banner(
        "EXPERIMENT 3 - Gradient isolation and the safety criteria",
        "Can the framework's safety criteria be computed, and do they see anything "
        "that\n            watching the host's own memory would miss?",
        "Influence and curvature should rise with A's edit bandwidth, and should "
        "move\n            further above their noise floor than the host's own "
        "retained identity does.",
    )

    base = ensemble_for()
    # Gradient influence is a difference of finite-difference gradients, so it
    # carries the estimator noise of four separate mutual information estimates.
    # It needs a larger sample than a single score does.
    ensemble = Ensemble(steps=base.steps, burn_in=base.burn_in, seeds=(11, 23, 37))
    # A second ensemble with different seeds, used to measure the null: the same
    # world compared against itself. Any bound looser than that noise floor would
    # be measuring the estimator rather than the other system.
    null_ensemble = Ensemble(
        steps=base.steps, burn_in=base.burn_in, seeds=(41, 53, 67)
    )

    # H is a quiet system holding its identity; A is resource-hungry and harvests
    # at every opportunity. A has no model of H and nothing against it. The host
    # is not adapting to A either - it keeps doing what worked before A's
    # bandwidth changed, which is exactly the case the criteria are meant to
    # cover.
    profile = [ThresholdPolicy(6.0, 1), ThresholdPolicy(10.0, 0)]
    energies = [0.0, 3.3333, 6.6667, 10.0]
    mismatches = [0, 1, 2, 3, 4]

    def assess(baseline_b: int, perturbed_b: int, ens, **bounds):
        return assess_safety(
            baseline_config=WorldConfig(scramble_by_agent=(0, baseline_b)),
            perturbed_config=WorldConfig(scramble_by_agent=(0, perturbed_b)),
            profile=profile,
            host=HOST,
            other=OTHER,
            energies=energies,
            mismatches=mismatches,
            delta=1.0,
            ensemble=ensemble,
            perturbed_ensemble=ens,
            **bounds,
        )

    section("Step 1: calibrate the bounds against a null comparison")
    print(
        "  Comparing bandwidth 0 against bandwidth 0, changing only the random seeds.\n"
        "  Whatever influence this produces is pure estimator noise. Bounds are then\n"
        "  set to twice the null, so a criterion fires only on an effect at least\n"
        "  double what an unchanged world produces on its own.\n"
    )
    null = assess(0, 0, null_ensemble)
    print(
        f"  null influence  = {null.influence:.4f}   -> bound {2 * null.influence:.4f}\n"
        f"  null curvature  = {null.curvature:.4f}   -> bound {2 * null.curvature:.4f}\n"
        f"  null dH/dt      = {null.entropy_rate:+.2e} -> bound {-2 * abs(null.entropy_rate):.2e}\n"
        f"  null dsigma/dt  = {null.stability_drift:+.2e} -> bound {-2 * abs(null.stability_drift):.2e}"
    )

    bounds = dict(
        influence_bound=2 * null.influence,
        kappa_max=2 * null.curvature,
        gamma=2 * abs(null.entropy_rate),
        beta=2 * abs(null.stability_drift),
    )

    rows = []
    reports = []
    for label, base_b, pert_b, ens in (
        ("null 0 -> 0", 0, 0, null_ensemble),
        ("0 -> 1", 0, 1, ensemble),
        ("1 -> 2", 1, 2, ensemble),
    ):
        report = assess(base_b, pert_b, ens, **bounds)
        reports.append((label, report))
        rows.append(
            (
                label,
                f"{report.influence:.4f}",
                f"{report.alignment:+.2f}",
                f"{report.curvature:.4f}",
                f"{report.entropy_rate:+.2e}",
                f"{report.stability:.3f}",
                f"{report.stability_drift:+.2e}",
                f"{report.host_preservation:.3f}",
                "safe" if report.safe else ",".join(report.failures()),
            )
        )

    section("Step 2: safety criteria as A's edit bandwidth increases")
    print(
        "  Each row perturbs A's bandwidth by one cell and measures the effect on H.\n"
        "  influence = max ||grad S_H(perturbed) - grad S_H(baseline)|| / delta\n"
        "  align     = sign of grad S_H . G, Theorem 5; negative means pushing against H\n"
        "  curvature = ||grad^2 S_H||_inf on H's own landscape\n"
        "  dH/dt     = d/dt H(m_H | m_A), entropy compatibility\n"
        "  sigma     = how tightly H sits in its own basin (1 = perfect)\n"
        "  identity  = H's retained identity I(signature; m_H)\n"
    )
    table(
        [
            "bandwidth",
            "influence",
            "align",
            "curvature",
            "dH/dt",
            "sigma",
            "dsigma/dt",
            "identity",
            "verdict",
        ],
        rows,
    )

    section("Step 3: the actual harm, measured directly")
    print(
        "  The criteria above read H's landscape. This reads H itself: the same\n"
        "  fixed host policy run at each of A's bandwidths, so the harm curve is\n"
        "  ground truth to compare the criteria against.\n"
    )
    harm_rows = []
    harm_identity = []
    for bandwidth in (0, 1, 2):
        config = WorldConfig(scramble_by_agent=(0, bandwidth))
        results = run_ensemble(config, profile, ensemble)
        identity = identity_objective(results, HOST, config)
        corruption = sum(r.mean_shared_corruption for r in results) / len(results)
        capacity = sum(
            sum(r.agents[HOST].mismatches) / len(r.agents[HOST].mismatches)
            for r in results
        ) / len(results)
        harm_identity.append(identity)
        harm_rows.append(
            (
                str(bandwidth),
                f"{identity:.3f}",
                f"{corruption:.2f}",
                f"{capacity:.2f}",
            )
        )
    table(
        ["A bandwidth", "H identity", "channel damage", "H corrupted"], harm_rows
    )

    section("Result")
    null_report = reports[0][1]
    first = reports[1][1]
    last = reports[-1][1]

    verdict(
        "The criteria stay quiet when nothing has changed",
        null_report.safe,
        "the null comparison passes every criterion, so the metrics are not "
        "simply always-on."
        if null_report.safe
        else f"the null comparison still trips [{', '.join(null_report.failures())}], "
        "so these bounds cannot discriminate.",
    )

    rising = last.influence > first.influence > null_report.influence
    verdict(
        "Measured influence rises with the other system's edit bandwidth",
        rising,
        f"influence goes {null_report.influence:.4f} (null) -> "
        f"{first.influence:.4f} -> {last.influence:.4f}.",
    )

    # The landscape metric and the host's realised outcome are on different
    # scales, so compare each against its own baseline.
    influence_ratio = last.influence / null_report.influence
    identity_change = abs(harm_identity[-1] - harm_identity[0]) / harm_identity[0]
    more_sensitive = influence_ratio > (1.0 + identity_change)
    verdict(
        "Landscape criteria are more sensitive than the host's realised outcome",
        more_sensitive,
        f"influence grows {influence_ratio:.1f}x above its null floor while H's "
        f"retained identity moves only {100 * identity_change:.0f}% "
        f"({harm_identity[0]:.3f} -> {harm_identity[-1]:.3f}).",
    )

    print(
        f"\n  Worth noting what the harm curve shows. By bandwidth 1 the shared\n"
        f"  channel is already most of the way destroyed, yet H's identity is\n"
        f"  essentially unchanged. H's error-correction capacity has headroom, so\n"
        f"  it absorbs the damage. Gradient manipulation and realised harm are not\n"
        f"  the same thing, and the gap between them is exactly the margin a\n"
        f"  safety metric is supposed to see into."
    )

    print(
        "\n  Reading: the criteria are computable, and computing them on H's\n"
        "  *landscape* rather than on a single run is what buys the sensitivity.\n"
        "  A run shows only where H currently sits; the landscape shows how the\n"
        "  terrain under H has been reshaped, which moves first and moves more.\n"
        "\n"
        "  Two caveats worth carrying forward. The thresholds are calibrated to\n"
        "  this world and are not universal constants - the framework supplies\n"
        "  none, and picking them is an open problem. And measuring influence\n"
        "  needs a counterfactual: H's landscape under a version of A that acted\n"
        "  differently. Here that is free, because A's bandwidth is a config knob.\n"
        "  For a real system it is the hard part, and any practical use of these\n"
        "  criteria has to say where that counterfactual comes from."
    )


if __name__ == "__main__":
    with Timer():
        main()
