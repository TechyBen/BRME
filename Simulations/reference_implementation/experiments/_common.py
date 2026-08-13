"""Shared plumbing for the experiment scripts: imports, output, and run size."""

from __future__ import annotations

import os
import sys
import time
from typing import Iterable, List, Sequence

# Let the experiments run as plain scripts from anywhere, without installation.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brme.equilibrium import Ensemble  # noqa: E402

__all__ = ["banner", "section", "table", "ensemble_for", "quick", "Timer", "verdict"]


def quick() -> bool:
    """True when ``--quick`` was passed: fewer samples, for a fast sanity run."""
    return "--quick" in sys.argv


def ensemble_for() -> Ensemble:
    """The measurement ensemble, shrunk under ``--quick``.

    Quick runs are for checking the code path, not for reading results off: the
    smaller sample makes the mutual information estimates noticeably noisier.
    """
    if quick():
        return Ensemble(steps=120, burn_in=40, seeds=(11,))
    return Ensemble(steps=250, burn_in=80, seeds=(11, 23))


def banner(title: str, question: str, prediction: str) -> None:
    """Print the experiment header: what is asked, and what would count as an answer."""
    line = "=" * 78
    print(f"\n{line}\n{title}\n{line}")
    print(f"\nQuestion:   {question}")
    print(f"Prediction: {prediction}")
    if quick():
        print("\n[--quick: reduced sample size, results are indicative only]")
    print()


def section(text: str) -> None:
    print(f"\n--- {text} " + "-" * max(0, 74 - len(text)))


def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """Print a fixed-width table, right-aligning everything but the first column."""
    rows = [[str(c) for c in row] for row in rows]
    widths: List[int] = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        out = [cells[0].ljust(widths[0])]
        out += [cells[i].rjust(widths[i]) for i in range(1, len(cells))]
        return "  ".join(out)

    print(fmt(list(headers)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def verdict(claim: str, supported: bool, detail: str) -> None:
    """State plainly whether the measurement supported the claim under test."""
    mark = "SUPPORTED" if supported else "NOT SUPPORTED"
    print(f"\n  [{mark}] {claim}\n              {detail}")


class Timer:
    def __enter__(self) -> "Timer":
        self.t0 = time.time()
        return self

    def __exit__(self, *exc: object) -> None:
        print(f"\n(completed in {time.time() - self.t0:.1f}s)")
