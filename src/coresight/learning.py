"""The learning loop (point F): a site's corrections tune its profile thresholds.

The profile layer of segmentation cuts a piece where a thin dark line crosses
the core; each such cut is an uncertain break, counted as natural. Two
thresholds decide when a dip becomes a cut (segmentation.ProfileThresholds):
``min_contrast`` (how dark) and ``min_crossing`` (how much of the core height).

When the geologist corrects the breaks of a box, the corrected runs have a
true RQD (computed by geometry.py). The caller segments each corrected box with
every candidate pair, computes RQD with geometry.py and passes the errors here.
This module only chooses and scores, with cross-validation by box: runs of one
box share a photo and a calibration, so a box is never in training and test at
once. It never segments and never computes RQD.

The rules are the docstring of tests/test_learning.py.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

Candidate = tuple[float, float]  # (min_contrast, min_crossing)
RunKey = tuple[str, int]  # (box, run index in the box)


@dataclass(frozen=True)
class RunError:
    """RQD found with one candidate minus the RQD after the geologist's corrections."""

    box: str
    run: int
    candidate: Candidate
    error: float  # percentage points


@dataclass(frozen=True)
class Fold:
    """One box held out: the candidate fitted on the other boxes, scored on this one."""

    held_out: str
    fitted: Candidate
    train_runs: int
    test_runs: int
    mae_default: float
    mae_fitted: float


def mae_of(errors: Sequence[RunError], candidate: Candidate, runs: Iterable[RunKey]) -> float:
    """Mean |error| of ``candidate`` over ``runs``; ValueError if a run is missing or none."""
    raise NotImplementedError


def fit(errors: Sequence[RunError], runs: Iterable[RunKey] | None, default: Candidate) -> Candidate:
    """The candidate with the lowest MAE over ``runs`` (every run when None)."""
    raise NotImplementedError


def leave_one_box_out(errors: Sequence[RunError], default: Candidate) -> list[Fold]:
    """One fold per box, in sorted order: fit on the other boxes, score the held-out one."""
    raise NotImplementedError


def learning_curve(
    errors: Sequence[RunError], default: Candidate
) -> list[tuple[int, float, float]]:
    """(n corrected runs, pooled held-out MAE with the default, pooled MAE after n)."""
    raise NotImplementedError
