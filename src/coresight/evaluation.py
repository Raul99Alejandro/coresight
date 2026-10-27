"""Statistics for the evaluation: errors against a reference log, never RQD itself.

RQD, TCR and the Deere class come from geometry.py; this module only compares
what CoreSight found with what a person logged.

- Confidence intervals are a cluster bootstrap by box: runs of one box share
  a photo, a calibration and a SAM call per row, so they are not independent.
  Resampling runs alone would make the interval too narrow.
- Bland-Altman (1986): bias and 95% limits of agreement of found - reference.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from coresight.geometry import rock_quality_class

DEERE_CLASSES = ("very poor", "poor", "fair", "good", "excellent")


def mae(errors: Sequence[float]) -> float:
    return float(np.mean(np.abs(errors)))


def bias(errors: Sequence[float]) -> float:
    return float(np.mean(errors))


@dataclass(frozen=True)
class Interval95:
    value: float
    low: float
    high: float


def cluster_bootstrap(
    errors: Sequence[float],
    groups: Sequence[str],
    stat: Callable[[Sequence[float]], float] = mae,
    n_resamples: int = 10_000,
    level: float = 0.95,
    seed: int = 0,
) -> Interval95:
    """Percentile interval of ``stat`` resampling whole groups (boxes) with replacement."""
    if len(errors) != len(groups):
        raise ValueError("errors and groups must have the same length")
    if not errors:
        raise ValueError("no errors to resample")
    e = np.asarray(errors, dtype=float)
    names = sorted(set(groups))
    members = [np.flatnonzero(np.asarray(groups) == g) for g in names]
    rng = np.random.default_rng(seed)
    values = np.empty(n_resamples)
    for i in range(n_resamples):
        picked = rng.integers(len(names), size=len(names))
        values[i] = stat(e[np.concatenate([members[j] for j in picked])])
    tail = (1 - level) / 2 * 100
    low, high = np.percentile(values, [tail, 100 - tail])
    return Interval95(stat(e), float(low), float(high))


@dataclass(frozen=True)
class BlandAltman:
    n: int
    bias: float
    sd: float
    low: float  # bias - 1.96 sd
    high: float  # bias + 1.96 sd
    means: tuple[float, ...]  # (found + reference) / 2, the x axis of the plot
    diffs: tuple[float, ...]  # found - reference, the y axis


def bland_altman(found: Sequence[float], reference: Sequence[float]) -> BlandAltman:
    f, r = np.asarray(found, dtype=float), np.asarray(reference, dtype=float)
    if f.shape != r.shape or f.size < 2:
        raise ValueError("need two or more paired values")
    d = f - r
    b, sd = float(d.mean()), float(d.std(ddof=1))
    return BlandAltman(
        n=int(d.size),
        bias=b,
        sd=sd,
        low=b - 1.96 * sd,
        high=b + 1.96 * sd,
        means=tuple(((f + r) / 2).tolist()),
        diffs=tuple(d.tolist()),
    )


@dataclass(frozen=True)
class ClassAgreement:
    n: int
    exact: int  # same Deere class
    within_one: int  # same or a neighbouring class
    confusion: dict[tuple[str, str], int]  # (reference, found) -> runs

    @property
    def accuracy(self) -> float:
        return self.exact / self.n

    @property
    def within_one_rate(self) -> float:
        return self.within_one / self.n


def class_agreement(found_rqd: Sequence[float], reference_rqd: Sequence[float]) -> ClassAgreement:
    if len(found_rqd) != len(reference_rqd) or not found_rqd:
        raise ValueError("need paired RQD values")
    pairs = [
        (rock_quality_class(r), rock_quality_class(f))
        for f, r in zip(found_rqd, reference_rqd, strict=True)
    ]
    rank = {c: i for i, c in enumerate(DEERE_CLASSES)}
    return ClassAgreement(
        n=len(pairs),
        exact=sum(r == f for r, f in pairs),
        within_one=sum(abs(rank[r] - rank[f]) <= 1 for r, f in pairs),
        confusion=dict(Counter(pairs)),
    )
