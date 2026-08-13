"""Tests for the policy space, the objectives, and the equilibrium solvers."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brme.equilibrium import (  # noqa: E402
    Ensemble,
    best_response,
    evaluate,
    identity_objective,
    literal_memory_objective,
    payoff_objective,
    run_ensemble,
    signature_schedule,
    solve_equilibrium,
)
from brme.field import Action, Observation, WorldConfig  # noqa: E402
from brme.policies import FixedPolicy, ThresholdPolicy, policy_grid  # noqa: E402
from brme.safety import (  # noqa: E402
    Landscape,
    attractor_stability,
    build_landscape,
    gradient_influence,
)

FAST = Ensemble(steps=90, burn_in=30, seeds=(11,))


def obs(energy: float, mismatch: int) -> Observation:
    return Observation(energy=energy, mismatch=mismatch, max_energy=10.0, private_bits=3)


class TestPolicies(unittest.TestCase):
    def test_low_energy_triggers_harvest(self):
        self.assertIs(ThresholdPolicy(5.0, 1).act(obs(3.0, 3)), Action.HARVEST)

    def test_corruption_triggers_hold(self):
        self.assertIs(ThresholdPolicy(2.0, 1).act(obs(8.0, 2)), Action.HOLD)

    def test_clean_and_fed_triggers_probe(self):
        self.assertIs(ThresholdPolicy(2.0, 2).act(obs(8.0, 1)), Action.PROBE)

    def test_threshold_zero_always_holds_when_fed(self):
        self.assertIs(ThresholdPolicy(0.0, 0).act(obs(8.0, 0)), Action.HOLD)

    def test_threshold_above_range_never_holds(self):
        self.assertIs(ThresholdPolicy(0.0, 4).act(obs(8.0, 3)), Action.PROBE)

    def test_fixed_policy_ignores_observation(self):
        policy = FixedPolicy(Action.PROBE)
        self.assertIs(policy.act(obs(0.0, 3)), Action.PROBE)

    def test_grid_covers_the_full_mismatch_range(self):
        config = WorldConfig()
        grid = policy_grid(config)
        thresholds = {p.mismatch_threshold for p in grid}
        self.assertEqual(thresholds, set(range(config.private_bits + 2)))

    def test_grid_size_matches_its_axes(self):
        config = WorldConfig()
        self.assertEqual(len(policy_grid(config, energy_steps=4)), 4 * (config.private_bits + 2))

    def test_grid_rejects_degenerate_axis(self):
        with self.assertRaises(ValueError):
            policy_grid(WorldConfig(), energy_steps=1)


class TestSignatureSchedule(unittest.TestCase):
    def test_covers_every_signature(self):
        config = WorldConfig()
        schedule = signature_schedule(config)
        self.assertEqual(len(schedule), 1 << config.private_bits)

    def test_each_agent_sees_a_uniform_marginal(self):
        """Uniform marginals are what make identity scores comparable."""
        config = WorldConfig()
        schedule = signature_schedule(config)
        for agent in range(config.n_agents):
            seen = {assignment[agent] for assignment in schedule}
            self.assertEqual(len(seen), 1 << config.private_bits)

    def test_agents_are_offset_from_each_other(self):
        config = WorldConfig()
        differing = sum(
            1 for a in signature_schedule(config) if a[0] != a[1]
        )
        self.assertEqual(differing, len(signature_schedule(config)))


class TestObjectives(unittest.TestCase):
    def setUp(self):
        self.config = WorldConfig()

    def score(self, policy, objective):
        results = run_ensemble(self.config, [policy, policy], FAST)
        return objective(results, 0, self.config)

    def test_identity_objective_prefers_a_maintaining_policy(self):
        careful = self.score(ThresholdPolicy(6.0, 1), identity_objective)
        neglectful = self.score(ThresholdPolicy(0.0, 4), identity_objective)
        self.assertGreater(careful, neglectful)

    def test_payoff_objective_prefers_a_harvesting_policy(self):
        greedy = self.score(ThresholdPolicy(10.0, 0), payoff_objective)
        frugal = self.score(ThresholdPolicy(0.0, 0), payoff_objective)
        self.assertGreater(greedy, frugal)

    def test_the_two_objectives_disagree(self):
        """If they agreed, experiment 2 would have nothing to compare."""
        greedy, careful = ThresholdPolicy(10.0, 0), ThresholdPolicy(6.0, 1)
        self.assertGreater(
            self.score(greedy, payoff_objective),
            self.score(careful, payoff_objective),
        )
        self.assertGreater(
            self.score(careful, identity_objective),
            self.score(greedy, identity_objective),
        )

    def test_literal_objective_inverts_the_identity_ranking(self):
        """Pins the finding of experiment 1 so a regression would surface."""
        greedy, careful = ThresholdPolicy(0.0, 3), ThresholdPolicy(6.0, 1)
        self.assertGreater(
            self.score(careful, identity_objective),
            self.score(greedy, identity_objective),
        )
        self.assertGreater(
            self.score(greedy, literal_memory_objective),
            self.score(careful, literal_memory_objective),
        )

    def test_objectives_are_bounded(self):
        for objective in (identity_objective, literal_memory_objective, payoff_objective):
            value = self.score(ThresholdPolicy(6.0, 1), objective)
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.05)

    def test_empty_results_are_handled(self):
        for objective in (identity_objective, literal_memory_objective, payoff_objective):
            self.assertEqual(objective([], 0, self.config), 0.0)


class TestSolvers(unittest.TestCase):
    def setUp(self):
        self.config = WorldConfig()
        self.grid = policy_grid(self.config, energy_steps=2)

    def test_best_response_does_not_lower_the_score(self):
        profile = [ThresholdPolicy(0.0, 4), ThresholdPolicy(0.0, 4)]
        before = evaluate(self.config, profile, identity_objective, 0, FAST)
        _, after = best_response(
            self.config, profile, 0, identity_objective, self.grid, FAST
        )
        self.assertGreaterEqual(after, before)

    def test_incumbent_survives_without_a_clear_margin(self):
        """Ties must not flip, or best-response dynamics chase estimator noise."""
        profile = [ThresholdPolicy(0.0, 1), ThresholdPolicy(0.0, 1)]
        policy, _ = best_response(
            self.config, profile, 0, identity_objective, self.grid, FAST, tolerance=1.0
        )
        self.assertEqual(policy, profile[0])

    def test_solver_terminates_and_reports_status(self):
        result = solve_equilibrium(
            self.config, identity_objective, grid=self.grid, ensemble=FAST, max_rounds=3
        )
        self.assertIn(result.status, {"fixed-point", "cycle", "unconverged"})
        self.assertEqual(len(result.profile), self.config.n_agents)
        self.assertEqual(len(result.scores), self.config.n_agents)
        self.assertGreaterEqual(result.rounds, 1)

    def test_solver_records_its_history(self):
        result = solve_equilibrium(
            self.config, identity_objective, grid=self.grid, ensemble=FAST, max_rounds=3
        )
        self.assertEqual(result.history[0], tuple(result.history[0]))
        self.assertGreaterEqual(len(result.history), 2)

    def test_fixed_point_is_a_genuine_fixed_point(self):
        result = solve_equilibrium(
            self.config, identity_objective, grid=self.grid, ensemble=FAST, max_rounds=4
        )
        if result.converged:
            for agent in range(self.config.n_agents):
                policy, _ = best_response(
                    self.config,
                    list(result.profile),
                    agent,
                    identity_objective,
                    self.grid,
                    FAST,
                )
                self.assertEqual(policy, result.profile[agent])

    def test_wrong_profile_size_raises(self):
        with self.assertRaises(ValueError):
            run_ensemble(self.config, [ThresholdPolicy(0.0, 1)], FAST)


class TestSafetyMetrics(unittest.TestCase):
    def flat(self):
        return Landscape([0.0, 1.0, 2.0], [0, 1, 2], [[0.5] * 3 for _ in range(3)])

    def sloped(self):
        return Landscape(
            [0.0, 1.0, 2.0], [0, 1, 2], [[float(e) for _ in range(3)] for e in range(3)]
        )

    def test_flat_landscape_has_no_gradient_or_curvature(self):
        land = self.flat()
        self.assertEqual(land.gradient_at(1, 1), (0.0, 0.0))
        self.assertAlmostEqual(land.max_curvature, 0.0, places=9)

    def test_linear_slope_has_gradient_but_no_curvature(self):
        land = self.sloped()
        self.assertAlmostEqual(land.gradient_at(1, 1)[0], 1.0, places=9)
        self.assertAlmostEqual(land.max_curvature, 0.0, places=9)

    def test_argmax_finds_the_peak(self):
        land = self.flat()
        land.values[2][0] = 9.0
        self.assertEqual(land.argmax(), (2, 0))

    def test_identical_landscapes_show_no_influence(self):
        influence, _ = gradient_influence(self.sloped(), self.sloped(), delta=1.0)
        self.assertAlmostEqual(influence, 0.0, places=9)

    def test_deformed_landscape_shows_influence(self):
        influence, _ = gradient_influence(self.flat(), self.sloped(), delta=1.0)
        self.assertGreater(influence, 0.0)

    def test_zero_delta_raises(self):
        with self.assertRaises(ValueError):
            gradient_influence(self.flat(), self.flat(), delta=0.0)

    def test_mismatched_grids_raise(self):
        other = Landscape([0.0, 1.0], [0, 1], [[0.0, 0.0], [0.0, 0.0]])
        with self.assertRaises(ValueError):
            gradient_influence(self.flat(), other, delta=1.0)

    def test_stability_is_higher_for_a_maintained_agent(self):
        config = WorldConfig()
        careful = run_ensemble(config, [ThresholdPolicy(6.0, 1)] * 2, FAST)
        neglectful = run_ensemble(config, [ThresholdPolicy(0.0, 4)] * 2, FAST)
        self.assertGreater(
            attractor_stability(careful[0], 0, config),
            attractor_stability(neglectful[0], 0, config),
        )

    def test_landscape_has_the_requested_shape(self):
        config = WorldConfig()
        land = build_landscape(
            config,
            0,
            [ThresholdPolicy(6.0, 1)] * 2,
            energies=[0.0, 5.0],
            mismatches=[0, 1, 2],
            ensemble=FAST,
        )
        self.assertEqual(len(land.values), 2)
        self.assertEqual(len(land.values[0]), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
