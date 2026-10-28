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

import math
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


_TOL = 1e-9


def _validate_errors(errors: Sequence[RunError]) -> None:
    seen: set[tuple[RunKey, Candidate]] = set()
    for e in errors:
        if not math.isfinite(e.error):
            raise ValueError(f"non-finite error for {e.candidate} on {(e.box, e.run)}")
        key = ((e.box, e.run), e.candidate)
        if key in seen:
            raise ValueError(f"duplicate error for {e.candidate} on {(e.box, e.run)}")
        seen.add(key)


def _dist(a: Candidate, b: Candidate) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _runs_by_box(errors: Sequence[RunError]) -> dict[str, list[RunKey]]:
    grouped: dict[str, set[RunKey]] = {}
    for e in errors:
        grouped.setdefault(e.box, set()).add((e.box, e.run))
    return {box: sorted(runs) for box, runs in grouped.items()}


def _abs_error(
    lookup: dict[tuple[RunKey, Candidate], float], run: RunKey, cand: Candidate
) -> float:
    try:
        err = lookup[(run, cand)]
    except KeyError:
        raise ValueError(f"missing error for {cand} on {run}") from None
    if not math.isfinite(err):
        raise ValueError(f"non-finite error for {cand} on {run}")
    return abs(err)


def mae_of(errors: Sequence[RunError], candidate: Candidate, runs: Iterable[RunKey]) -> float:
    """Mean |error| of ``candidate`` over ``runs``; ValueError if a run is missing or none."""
    _validate_errors(errors)
    wanted = sorted(set(runs))
    if not wanted:
        raise ValueError("no runs")
    found: dict[RunKey, float] = {}
    for e in errors:
        if e.candidate == candidate:
            found[(e.box, e.run)] = e.error
    total = 0.0
    for r in wanted:
        if r not in found:
            raise ValueError(f"missing error for {candidate} on {r}")
        err = found[r]
        if not math.isfinite(err):
            raise ValueError(f"non-finite error for {candidate} on {r}")
        total += abs(err)
    return total / len(wanted)


def fit(errors: Sequence[RunError], runs: Iterable[RunKey] | None, default: Candidate) -> Candidate:
    """The candidate with the lowest MAE over ``runs`` (every run when None)."""
    _validate_errors(errors)
    train = sorted({(e.box, e.run) for e in errors}) if runs is None else sorted(set(runs))
    if not train:
        return default
    by_cand: dict[Candidate, dict[RunKey, float]] = {}
    for e in errors:
        by_cand.setdefault(e.candidate, {})[(e.box, e.run)] = e.error
    need = set(train)
    eligible = [c for c, per_run in by_cand.items() if need <= per_run.keys()]
    if not eligible:
        raise ValueError("no eligible candidate for the training runs")
    maes: dict[Candidate, float] = {}
    for c in eligible:
        per_run = by_cand[c]
        total = 0.0
        for r in train:
            err = per_run[r]
            if not math.isfinite(err):
                raise ValueError(f"non-finite error for {c} on {r}")
            total += abs(err)
        maes[c] = total / len(train)
    best = min(maes.values())
    tied = [c for c, m in maes.items() if abs(m - best) <= _TOL]
    if len(tied) == 1:
        return tied[0]
    dists = {c: _dist(c, default) for c in tied}
    nearest = min(dists.values())
    closest = [c for c in tied if abs(dists[c] - nearest) <= _TOL]
    if len(closest) == 1:
        return closest[0]
    return min(closest)


def leave_one_box_out(errors: Sequence[RunError], default: Candidate) -> list[Fold]:
    """One fold per box, in sorted order: fit on the other boxes, score the held-out one."""
    _validate_errors(errors)
    grouped = _runs_by_box(errors)
    boxes = sorted(grouped)
    if len(boxes) < 2:
        return []
    folds: list[Fold] = []
    for held in boxes:
        train = [r for b in boxes if b != held for r in grouped[b]]
        test = grouped[held]
        fitted = fit(errors, train, default)
        folds.append(
            Fold(
                held_out=held,
                fitted=fitted,
                train_runs=len(train),
                test_runs=len(test),
                mae_default=mae_of(errors, default, test),
                mae_fitted=mae_of(errors, fitted, test),
            )
        )
    return folds


def learning_curve(
    errors: Sequence[RunError], default: Candidate
) -> list[tuple[int, float, float]]:
    """(n corrected runs, pooled held-out MAE with the default, pooled MAE after n)."""
    _validate_errors(errors)
    grouped = _runs_by_box(errors)
    boxes = sorted(grouped)
    if len(boxes) < 2:
        return []
    trains = {b: sorted(r for other in boxes if other != b for r in grouped[other]) for b in boxes}
    max_n = max(len(trains[b]) for b in boxes)
    lookup = {((e.box, e.run), e.candidate): e.error for e in errors}
    total_runs = sum(len(grouped[b]) for b in boxes)
    pooled_default = (
        sum(_abs_error(lookup, r, default) for b in boxes for r in grouped[b]) / total_runs
    )
    curve: list[tuple[int, float, float]] = []
    for n in range(max_n + 1):
        pooled = 0.0
        for b in boxes:
            fitted = fit(errors, trains[b][:n], default)
            for r in grouped[b]:
                pooled += _abs_error(lookup, r, fitted)
        curve.append((n, pooled_default, pooled / total_runs))
    return curve
