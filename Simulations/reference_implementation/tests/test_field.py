"""Tests for the world model.

The experiments' conclusions are only as good as the dynamics underneath them, so
these tests pin the mechanisms the results actually depend on: that acting is
required to preserve memory, that the shared block is genuinely load-bearing, and
that depletion is recoverable rather than absorbing.
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brme.field import Action, World, WorldConfig, rollout  # noqa: E402
from brme.policies import FixedPolicy, ThresholdPolicy  # noqa: E402


class TestWorldConstruction(unittest.TestCase):
    def test_agents_start_holding_their_identity(self):
        world = World(WorldConfig(), random.Random(0))
        for i in range(world.config.n_agents):
            self.assertEqual(world.mismatch(i), 0)

    def test_explicit_signatures_are_used(self):
        sigs = [(1, 0, 1), (0, 1, 0)]
        world = World(WorldConfig(), random.Random(0), signatures=sigs)
        self.assertEqual([tuple(s) for s in world.signatures], sigs)
        self.assertEqual(tuple(world.private[0]), (1, 0, 1))

    def test_wrong_signature_count_raises(self):
        with self.assertRaises(ValueError):
            World(WorldConfig(), random.Random(0), signatures=[(1, 0, 1)])

    def test_wrong_signature_length_raises(self):
        with self.assertRaises(ValueError):
            World(WorldConfig(), random.Random(0), signatures=[(1, 0), (0, 1)])

    def test_shared_block_starts_intact(self):
        world = World(WorldConfig(), random.Random(0))
        self.assertEqual(world.shared_corruption(), 0)

    def test_region_is_private_plus_shared(self):
        config = WorldConfig()
        world = World(config, random.Random(0))
        self.assertEqual(len(world.region(0)), config.region_bits)


class TestDynamics(unittest.TestCase):
    def test_noise_eventually_corrupts_an_idle_memory(self):
        """Information decay: doing nothing loses the identity."""
        world = World(WorldConfig(private_noise=0.2), random.Random(1))
        for _ in range(200):
            world.apply_noise()
        self.assertGreater(world.mismatch(0), 0)

    def test_hold_repairs_the_private_block(self):
        world = World(WorldConfig(), random.Random(2))
        world.private[0] = [1 - b for b in world.signatures[0]]
        before = world.mismatch(0)
        world.apply(0, Action.HOLD)
        self.assertLess(world.mismatch(0), before)

    def test_harvest_damages_the_shared_block(self):
        world = World(WorldConfig(), random.Random(3))
        self.assertEqual(world.shared_corruption(), 0)
        world.apply(0, Action.HARVEST)
        self.assertGreater(world.shared_corruption(), 0)

    def test_hold_repairs_the_shared_block(self):
        world = World(WorldConfig(), random.Random(4))
        world.shared = [1 - r for r in world.shared_reference]
        before = world.shared_corruption()
        world.apply(0, Action.HOLD)
        self.assertLess(world.shared_corruption(), before)

    def test_shared_corruption_reduces_correction_capacity(self):
        """The mechanism that makes one system's actions reach another's memory."""
        world = World(WorldConfig(), random.Random(5))
        intact = world.correction_capacity(0)
        world.shared = [1 - r for r in world.shared_reference]
        self.assertLess(world.correction_capacity(0), intact)

    def test_probe_raises_correction_capacity(self):
        world = World(WorldConfig(), random.Random(6))
        before = world.correction_capacity(0)
        for _ in range(6):
            world.apply(0, Action.PROBE)
        self.assertGreater(world.correction_capacity(0), before)

    def test_model_quality_decays(self):
        world = World(WorldConfig(), random.Random(7))
        world.apply(0, Action.PROBE)
        high = world.model_quality[0]
        world.decay_and_drain()
        self.assertLess(world.model_quality[0], high)

    def test_harvest_gains_energy_from_the_pool(self):
        world = World(WorldConfig(), random.Random(8))
        world.energy[0] = 1.0
        pool_before = world.pool
        world.apply(0, Action.HARVEST)
        self.assertGreater(world.energy[0], 1.0)
        self.assertEqual(world.pool, pool_before - 1)

    def test_empty_pool_yields_nothing(self):
        world = World(WorldConfig(), random.Random(9))
        world.pool = 0
        world.energy[0] = 1.0
        world.apply(0, Action.HARVEST)
        self.assertEqual(world.energy[0], 1.0)

    def test_depletion_is_not_absorbing(self):
        """A depleted agent must still be able to harvest, or collapse is one-way."""
        world = World(WorldConfig(), random.Random(10))
        world.energy[0] = 0.0
        taken = world.apply(0, Action.HARVEST)
        self.assertIs(taken, Action.HARVEST)
        self.assertGreater(world.energy[0], 0.0)

    def test_unaffordable_action_becomes_noop(self):
        world = World(WorldConfig(), random.Random(11))
        world.energy[0] = 0.0
        self.assertIs(world.apply(0, Action.HOLD), Action.NOOP)

    def test_energy_is_capped(self):
        config = WorldConfig()
        world = World(config, random.Random(12))
        world.energy[0] = config.max_energy
        world.apply(0, Action.HARVEST)
        self.assertLessEqual(world.energy[0], config.max_energy)

    def test_per_agent_scramble_bandwidth(self):
        config = WorldConfig(scramble_by_agent=(0, 2))
        world = World(config, random.Random(13))
        world.apply(0, Action.HARVEST)
        self.assertEqual(world.shared_corruption(), 0)
        world.apply(1, Action.HARVEST)
        self.assertEqual(world.shared_corruption(), 2)


class TestRollout(unittest.TestCase):
    def setUp(self):
        self.config = WorldConfig()
        self.policy = ThresholdPolicy(6.0, 1)

    def test_records_requested_number_of_steps(self):
        result = rollout(self.config, [self.policy] * 2, steps=50, seed=1, burn_in=10)
        self.assertEqual(result.agents[0].steps, 50)
        self.assertEqual(len(result.pool_levels), 50)
        self.assertEqual(len(result.shared_corruption), 50)

    def test_is_deterministic_for_a_seed(self):
        a = rollout(self.config, [self.policy] * 2, steps=40, seed=7)
        b = rollout(self.config, [self.policy] * 2, steps=40, seed=7)
        self.assertEqual(a.agents[0].region_states, b.agents[0].region_states)

    def test_different_seeds_diverge(self):
        a = rollout(self.config, [self.policy] * 2, steps=40, seed=7)
        b = rollout(self.config, [self.policy] * 2, steps=40, seed=8)
        self.assertNotEqual(a.agents[0].region_states, b.agents[0].region_states)

    def test_wrong_policy_count_raises(self):
        with self.assertRaises(ValueError):
            rollout(self.config, [self.policy], steps=10, seed=1)

    def test_signature_is_recorded(self):
        sigs = [(1, 0, 1), (0, 1, 0)]
        result = rollout(
            self.config, [self.policy] * 2, steps=10, seed=1, signatures=sigs
        )
        self.assertEqual(result.agents[0].signature, (1, 0, 1))

    def test_action_fractions_sum_to_one(self):
        result = rollout(self.config, [self.policy] * 2, steps=100, seed=2)
        total = sum(
            result.agents[0].action_fraction(a) for a in Action
        )
        self.assertAlmostEqual(total, 1.0, places=9)

    def test_holding_beats_idling_at_preserving_identity(self):
        """The core reason acting is necessary: idle agents decay."""
        holder = rollout(
            self.config, [ThresholdPolicy(2.0, 1)] * 2, steps=400, seed=3, burn_in=50
        )
        idler = rollout(
            self.config,
            [FixedPolicy(Action.NOOP)] * 2,
            steps=400,
            seed=3,
            burn_in=50,
        )
        held = sum(holder.agents[0].mismatches) / holder.agents[0].steps
        idled = sum(idler.agents[0].mismatches) / idler.agents[0].steps
        self.assertLess(held, idled)

    def test_constant_harvesting_destroys_the_shared_channel(self):
        greedy = rollout(
            self.config,
            [FixedPolicy(Action.HARVEST)] * 2,
            steps=300,
            seed=4,
            burn_in=50,
        )
        careful = rollout(
            self.config, [ThresholdPolicy(2.0, 1)] * 2, steps=300, seed=4, burn_in=50
        )
        self.assertGreater(
            greedy.mean_shared_corruption, careful.mean_shared_corruption
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
