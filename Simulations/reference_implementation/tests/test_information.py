"""Tests for the information-theoretic estimators.

These matter more than usual: every claim in the experiments is a mutual
information comparison, so an estimator that is quietly biased would produce
confident, wrong conclusions.
"""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brme.information import (  # noqa: E402
    conditional_entropy,
    entropy,
    identity_retention,
    memory_preservation,
    mutual_information,
    normalised_mutual_information,
)


class TestEntropy(unittest.TestCase):
    def test_constant_has_zero_entropy(self):
        self.assertAlmostEqual(entropy(["a"] * 100), 0.0, places=6)

    def test_fair_coin_approaches_one_bit(self):
        rng = random.Random(0)
        samples = [rng.randint(0, 1) for _ in range(20000)]
        self.assertAlmostEqual(entropy(samples), 1.0, places=2)

    def test_uniform_over_eight_approaches_three_bits(self):
        rng = random.Random(1)
        samples = [rng.randint(0, 7) for _ in range(40000)]
        self.assertAlmostEqual(entropy(samples), 3.0, places=2)

    def test_empty_is_zero(self):
        self.assertEqual(entropy([]), 0.0)

    def test_bias_correction_raises_the_estimate(self):
        rng = random.Random(2)
        samples = [rng.randint(0, 7) for _ in range(60)]
        self.assertGreater(entropy(samples, True), entropy(samples, False))

    def test_bias_correction_reduces_error_on_small_samples(self):
        """The correction should earn its place, not merely change the number."""
        rng = random.Random(3)
        raw_error = corrected_error = 0.0
        for _ in range(40):
            samples = [rng.randint(0, 7) for _ in range(80)]
            raw_error += abs(entropy(samples, False) - 3.0)
            corrected_error += abs(entropy(samples, True) - 3.0)
        self.assertLess(corrected_error, raw_error)


class TestMutualInformation(unittest.TestCase):
    def test_independent_variables_are_near_zero(self):
        rng = random.Random(4)
        xs = [rng.randint(0, 3) for _ in range(20000)]
        ys = [rng.randint(0, 3) for _ in range(20000)]
        self.assertLess(mutual_information(xs, ys), 0.05)

    def test_identical_variables_equal_their_entropy(self):
        rng = random.Random(5)
        xs = [rng.randint(0, 3) for _ in range(20000)]
        self.assertAlmostEqual(mutual_information(xs, xs), entropy(xs), places=6)

    def test_never_negative(self):
        rng = random.Random(6)
        for _ in range(20):
            xs = [rng.randint(0, 5) for _ in range(30)]
            ys = [rng.randint(0, 5) for _ in range(30)]
            self.assertGreaterEqual(mutual_information(xs, ys), 0.0)

    def test_symmetric(self):
        rng = random.Random(7)
        xs = [rng.randint(0, 3) for _ in range(3000)]
        ys = [x if rng.random() < 0.8 else rng.randint(0, 3) for x in xs]
        self.assertAlmostEqual(
            mutual_information(xs, ys), mutual_information(ys, xs), places=9
        )

    def test_noisier_channel_carries_less_information(self):
        rng = random.Random(8)
        xs = [rng.randint(0, 3) for _ in range(20000)]

        def through(flip: float):
            return [x if rng.random() > flip else rng.randint(0, 3) for x in xs]

        clean = mutual_information(xs, through(0.05))
        dirty = mutual_information(xs, through(0.5))
        self.assertGreater(clean, dirty)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ValueError):
            mutual_information([1, 2, 3], [1, 2])

    def test_normalisation_bounds(self):
        rng = random.Random(9)
        xs = [rng.randint(0, 3) for _ in range(8000)]
        value = normalised_mutual_information(xs, xs, max_bits=2.0)
        self.assertGreater(value, 0.95)
        self.assertLessEqual(value, 1.05)


class TestConditionalEntropy(unittest.TestCase):
    def test_conditioning_on_self_gives_zero(self):
        rng = random.Random(10)
        xs = [rng.randint(0, 3) for _ in range(5000)]
        self.assertAlmostEqual(conditional_entropy(xs, xs), 0.0, places=6)

    def test_conditioning_on_independent_leaves_entropy_intact(self):
        rng = random.Random(11)
        xs = [rng.randint(0, 3) for _ in range(20000)]
        ys = [rng.randint(0, 3) for _ in range(20000)]
        self.assertAlmostEqual(conditional_entropy(xs, ys), entropy(xs), places=1)


class TestMemoryPreservation(unittest.TestCase):
    def test_short_traces_are_zero(self):
        self.assertEqual(memory_preservation([]), 0.0)
        self.assertEqual(memory_preservation([(0, 1)]), 0.0)

    def test_constant_trace_scores_zero(self):
        """The documented degeneracy: a perfectly held memory scores nothing."""
        self.assertAlmostEqual(memory_preservation([(1, 1)] * 500), 0.0, places=6)

    def test_slow_drift_outscores_perfect_stability(self):
        """The degeneracy stated as an inequality, so a regression would fail here."""
        stable = [(1, 1)] * 2000
        drifting = [((i // 7) % 4, (i // 11) % 4) for i in range(2000)]
        self.assertGreater(memory_preservation(drifting), memory_preservation(stable))


class TestIdentityRetention(unittest.TestCase):
    def test_perfectly_held_identity_scores_full(self):
        rng = random.Random(12)
        ids = [rng.randint(0, 7) for _ in range(8000)]
        states = list(ids)
        self.assertGreater(identity_retention(ids, states, max_bits=3.0), 0.95)

    def test_erased_identity_scores_near_zero(self):
        rng = random.Random(13)
        ids = [rng.randint(0, 7) for _ in range(8000)]
        states = [rng.randint(0, 7) for _ in range(8000)]
        self.assertLess(identity_retention(ids, states, max_bits=3.0), 0.05)

    def test_decreases_monotonically_with_corruption(self):
        rng = random.Random(14)
        ids = [rng.randint(0, 7) for _ in range(20000)]
        scores = []
        for corruption in (0.0, 0.25, 0.5, 1.0):
            states = [
                i if rng.random() > corruption else rng.randint(0, 7) for i in ids
            ]
            scores.append(identity_retention(ids, states, max_bits=3.0))
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_constant_identity_yields_nothing(self):
        """Why the ensemble exists: within one run the identity is a constant."""
        rng = random.Random(15)
        ids = [3] * 4000
        states = [3 if rng.random() > 0.1 else rng.randint(0, 7) for _ in range(4000)]
        self.assertAlmostEqual(identity_retention(ids, states, max_bits=3.0), 0.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
