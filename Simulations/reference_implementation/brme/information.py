"""Information-theoretic estimators.

Everything the framework measures reduces to entropy and mutual information over
finite alphabets of memory states, so these estimators are the foundation of the
whole implementation.

Plug-in (maximum-likelihood) mutual information is biased *upward* on finite
samples: spurious structure in a sparse contingency table looks like shared
information. Since the framework's headline quantity is a mutual information
difference between conditions, an uncorrected estimator would let sampling noise
masquerade as an effect. We therefore apply the Miller-Madow bias correction and
expose the estimator bias directly so experiments can report it.

All logarithms are base 2; entropies and mutual informations are in bits.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Hashable, Iterable, Sequence, Tuple

__all__ = [
    "entropy",
    "conditional_entropy",
    "mutual_information",
    "normalised_mutual_information",
    "memory_preservation",
    "identity_retention",
]


def _counts(samples: Iterable[Hashable]) -> Counter:
    return Counter(samples)


def _plugin_entropy(counts: Counter, total: int) -> float:
    if total <= 0:
        return 0.0
    h = 0.0
    for n in counts.values():
        if n > 0:
            p = n / total
            h -= p * math.log2(p)
    return h


def entropy(samples: Sequence[Hashable], correct_bias: bool = True) -> float:
    """Shannon entropy H(X) in bits, estimated from ``samples``.

    With ``correct_bias`` the Miller-Madow correction ``(K - 1) / (2 N ln 2)`` is
    added, where ``K`` is the number of observed distinct states. The plug-in
    estimator underestimates entropy, so the correction is positive.
    """
    total = len(samples)
    if total == 0:
        return 0.0
    counts = _counts(samples)
    h = _plugin_entropy(counts, total)
    if correct_bias:
        h += (len(counts) - 1) / (2.0 * total * math.log(2.0))
    return max(0.0, h)


def conditional_entropy(
    xs: Sequence[Hashable], ys: Sequence[Hashable], correct_bias: bool = True
) -> float:
    """H(X | Y) in bits, computed as H(X, Y) - H(Y)."""
    _require_same_length(xs, ys)
    joint = list(zip(xs, ys))
    return max(0.0, entropy(joint, correct_bias) - entropy(ys, correct_bias))


def mutual_information(
    xs: Sequence[Hashable], ys: Sequence[Hashable], correct_bias: bool = True
) -> float:
    """I(X; Y) in bits, computed as H(X) + H(Y) - H(X, Y).

    Independent variables yield an estimate near zero; the residual is the
    estimator bias, which shrinks as ``1 / N``. It is clamped at zero because a
    negative mutual information is never meaningful.
    """
    _require_same_length(xs, ys)
    if not xs:
        return 0.0
    joint = list(zip(xs, ys))
    mi = entropy(xs, correct_bias) + entropy(ys, correct_bias) - entropy(joint, correct_bias)
    return max(0.0, mi)


def normalised_mutual_information(
    xs: Sequence[Hashable], ys: Sequence[Hashable], max_bits: float
) -> float:
    """I(X; Y) expressed as a fraction of ``max_bits``.

    ``max_bits`` is the alphabet's capacity (e.g. 4.0 for a 4-bit memory region),
    which makes the measure comparable across regions of different size.
    """
    if max_bits <= 0:
        return 0.0
    return mutual_information(xs, ys) / max_bits


def memory_preservation(trace: Sequence[Hashable], max_bits: float = 0.0) -> float:
    """The framework's stated quantity ``P = I(m_t; m_{t+1})``.

    ``trace`` is a system's memory state sampled once per step. Consecutive pairs
    are drawn from it, so a trace of length ``n`` yields ``n - 1`` samples. When
    ``max_bits`` is positive the result is normalised into ``[0, 1]``.

    **This quantity is degenerate as an objective, and measurably so.** It is
    bounded above by the marginal entropy ``H(m)``, so it rewards a memory that
    is *variable but predictable* and punishes one that is *stable*. A system
    holding its identity perfectly has ``H(m) ~ 0`` and therefore scores ~0,
    while a system drifting slowly through many states scores highly. In this
    package's world model, the highest scorer under this measure is an agent that
    has run out of energy and stopped acting entirely (see ``FINDINGS.md``).

    It is retained because it is what the formalisation writes down, and because
    experiments quantify the gap. Use :func:`identity_retention` as the objective
    that expresses the intended meaning.
    """
    if len(trace) < 2:
        return 0.0
    present = list(trace[:-1])
    future = list(trace[1:])
    if max_bits > 0:
        return normalised_mutual_information(present, future, max_bits)
    return mutual_information(present, future)


def identity_retention(
    identities: Sequence[Hashable],
    states: Sequence[Hashable],
    max_bits: float = 0.0,
) -> float:
    """``I(identity; m_t)``: how much of a system's identity survives to time ``t``.

    This is the non-degenerate reading of memory preservation. Rather than asking
    how predictable one step is from the last, it asks how much information about
    *which system this is* can still be recovered from its current memory state.
    A system holding its signature perfectly scores the full ``log2 K`` bits; one
    whose memory has decayed to noise scores 0. Inaction no longer wins, because
    a frozen memory is eroded by channel noise.

    It must be estimated over an *ensemble* of systems with differing identities:
    within a single run the identity is constant, and mutual information with a
    constant is zero by construction. ``identities`` and ``states`` are therefore
    paired samples pooled across runs.
    """
    _require_same_length(identities, states)
    if not identities:
        return 0.0
    if max_bits > 0:
        return normalised_mutual_information(identities, states, max_bits)
    return mutual_information(identities, states)


def _require_same_length(xs: Sequence[Hashable], ys: Sequence[Hashable]) -> None:
    if len(xs) != len(ys):
        raise ValueError(f"sample sequences differ in length: {len(xs)} != {len(ys)}")
