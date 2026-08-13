"""Run every experiment in order.

    python3 run_all.py [--quick]

``--quick`` shrinks the measurement ensemble for a fast check that everything
executes. Results from a quick run are indicative only - the mutual information
estimates get noticeably noisier - so read conclusions off a full run.
"""

from __future__ import annotations

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS = [
    "exp1_objective_degeneracy.py",
    "exp2_brme_vs_payoff.py",
    "exp3_gradient_isolation.py",
]


def main() -> None:
    sys.path.insert(0, os.path.join(HERE, "experiments"))
    for name in EXPERIMENTS:
        runpy.run_path(os.path.join(HERE, "experiments", name), run_name="__main__")


if __name__ == "__main__":
    main()
