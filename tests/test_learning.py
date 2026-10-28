"""The learning loop (point F): the spec coresight.learning is built to.

The geologist's corrections give, for every corrected run, its true RQD. The
caller segments each box with every candidate pair of profile thresholds
(min_contrast, min_crossing) and computes RQD with geometry.py; this module
only receives the errors (RQD found - RQD after correction, in points) and
decides: which candidate a site should use, and whether that beats the default
on boxes it never saw (cross-validation by box, since runs of one box share a
photo and a calibration). The caller may set ``box`` to the photo when two boxes
share one photo: the unit of cross-validation is whatever ``box`` names.

Rules:
- fit: the candidate with the lowest MAE over the training runs. A candidate
  that lacks an error for any training run is not eligible. Ties (within
  1e-9) go to the candidate nearest the default (Euclidean distance on the
  pair, also compared within 1e-9), then to the smaller pair. No training
  runs: the default. Training runs but no eligible candidate: ValueError (no
  candidate was scored, so none can be chosen). The training runs are a set:
  a run given twice counts once, and their order does not matter.
- leave_one_box_out: one fold per box, boxes in sorted order; fit on the runs
  of every other box, score the default and the fitted candidate on the
  held-out box. Fewer than two boxes: no folds. A candidate that must be
  scored on a held-out run it has no error for raises ValueError.
- learning_curve: the corrections arrive in order, (box, run) sorted. For
  n = 0 .. the most training runs any fold has, each fold fits on its first n
  training runs (all it has if fewer) and the held-out MAE is pooled over all
  held-out runs of all folds (sum of |error| / number of runs). n = 0 is the
  default.
- Errors are numbers in points; NaN or inf anywhere in the errors is a bug and
  raises ValueError, whether or not that run or candidate is used.
- Two errors for the same (box, run, candidate) are a bug and raise ValueError.
"""

import math

import pytest

from coresight.learning import Fold, RunError, fit, learning_curve, leave_one_box_out, mae_of

D = (0.2, 0.8)  # the default
LOW = (0.1, 0.8)
HIGH = (0.3, 0.8)


def errs(table: dict) -> list[RunError]:
    """{(box, run): {candidate: error}} -> RunError list."""
    return [
        RunError(box=box, run=run, candidate=c, error=e)
        for (box, run), by_c in table.items()
        for c, e in by_c.items()
    ]


# mae_of


def test_mae_of_is_the_mean_absolute_error_of_one_candidate_over_the_runs():
    e = errs({("a", 0): {D: -4.0, LOW: 1.0}, ("a", 1): {D: 2.0, LOW: -3.0}})
    assert mae_of(e, D, {("a", 0), ("a", 1)}) == pytest.approx(3.0)
    assert mae_of(e, LOW, {("a", 1)}) == pytest.approx(3.0)


def test_mae_of_without_runs_or_with_a_missing_run_raises():
    e = errs({("a", 0): {D: 1.0}})
    with pytest.raises(ValueError):
        mae_of(e, D, set())
    with pytest.raises(ValueError):
        mae_of(e, D, {("a", 0), ("a", 9)})


# fit


def test_fit_picks_the_lowest_mae():
    e = errs({("a", 0): {D: 10.0, LOW: 4.0, HIGH: 1.0}, ("a", 1): {D: 10.0, LOW: 4.0, HIGH: 2.0}})
    assert fit(e, {("a", 0), ("a", 1)}, D) == HIGH


def test_fit_uses_only_the_training_runs():
    e = errs({("a", 0): {D: 5.0, LOW: 0.0}, ("b", 0): {D: 0.0, LOW: 50.0}})
    assert fit(e, {("a", 0)}, D) == LOW
    assert fit(e, {("b", 0)}, D) == D


def test_fit_with_all_runs_when_runs_is_none():
    e = errs({("a", 0): {D: 5.0, LOW: 0.0}, ("b", 0): {D: 0.0, LOW: 1.0}})
    assert fit(e, None, D) == LOW  # 2.5 against 0.5


def test_fit_without_training_runs_keeps_the_default():
    e = errs({("a", 0): {D: 5.0, LOW: 0.0}})
    assert fit(e, set(), D) == D


def test_a_tie_goes_to_the_candidate_nearest_the_default():
    far, near = (0.5, 0.8), (0.25, 0.8)
    e = errs({("a", 0): {D: 3.0, far: 1.0, near: 1.0}})
    assert fit(e, {("a", 0)}, D) == near


def test_a_tie_with_the_default_keeps_the_default():
    e = errs({("a", 0): {D: 1.0, LOW: -1.0, HIGH: 1.0}})
    assert fit(e, {("a", 0)}, D) == D


def test_a_tie_at_the_same_distance_goes_to_the_smaller_pair():
    e = errs({("a", 0): {D: 9.0, LOW: 2.0, HIGH: 2.0}})
    assert fit(e, {("a", 0)}, D) == LOW


def test_a_candidate_missing_a_training_run_is_not_eligible():
    e = errs({("a", 0): {D: 5.0, LOW: 0.0}, ("a", 1): {D: 5.0}})
    assert fit(e, {("a", 0), ("a", 1)}, D) == D


def test_the_default_may_be_absent_from_the_errors():
    e = errs({("a", 0): {LOW: 3.0, HIGH: 1.0}})
    assert fit(e, {("a", 0)}, D) == HIGH
    assert fit(e, set(), D) == D


def test_nan_or_inf_errors_are_refused():
    for bad in (math.nan, math.inf):
        with pytest.raises(ValueError):
            fit(errs({("a", 0): {D: bad}}), None, D)


# leave_one_box_out


def two_boxes():
    """LOW is better on both boxes; HIGH is great on a only."""
    return errs({
        ("a", 0): {D: 10.0, LOW: 2.0, HIGH: 0.0},
        ("a", 1): {D: -6.0, LOW: 2.0, HIGH: 0.0},
        ("b", 0): {D: 8.0, LOW: 1.0, HIGH: 30.0},
    })  # fmt: skip


def test_each_box_is_held_out_once_and_scored_on_what_it_did_not_train_on():
    folds = leave_one_box_out(two_boxes(), D)
    assert [f.held_out for f in folds] == ["a", "b"]
    a, b = folds
    assert a.fitted == LOW and a.train_runs == 1 and a.test_runs == 2  # trained on b
    assert a.mae_default == pytest.approx(8.0) and a.mae_fitted == pytest.approx(2.0)
    assert b.fitted == HIGH and b.train_runs == 2 and b.test_runs == 1  # trained on a
    assert b.mae_default == pytest.approx(8.0) and b.mae_fitted == pytest.approx(30.0)
    assert isinstance(a, Fold)


def test_one_box_has_no_folds():
    assert leave_one_box_out(errs({("a", 0): {D: 1.0}, ("a", 1): {D: 2.0}}), D) == []


def test_folds_with_the_default_absent_still_score_it_as_nan_free():
    e = errs({("a", 0): {D: 1.0, LOW: 0.0}, ("b", 0): {D: 2.0, LOW: 4.0}})
    folds = leave_one_box_out(e, D)
    assert all(math.isfinite(f.mae_default) and math.isfinite(f.mae_fitted) for f in folds)


# learning_curve


def test_the_curve_starts_at_the_default_and_pools_over_held_out_runs():
    curve = learning_curve(two_boxes(), D)
    assert [n for n, _, _ in curve] == [0, 1, 2]
    n0, default0, fitted0 = curve[0]
    assert default0 == pytest.approx(fitted0) == pytest.approx((10 + 6 + 8) / 3)
    # n = 1: fold a fits on (b, 0) -> LOW: 2, 2 ; fold b fits on (a, 0) -> HIGH: 30
    assert curve[1][2] == pytest.approx((2 + 2 + 30) / 3)
    # n = 2: fold a has only 1 training run -> LOW again; fold b fits on a -> HIGH
    assert curve[2][2] == pytest.approx((2 + 2 + 30) / 3)
    assert all(d == pytest.approx(default0) for _, d, _ in curve)


def test_corrections_arrive_in_box_then_run_order():
    e = errs({
        ("a", 0): {D: 1.0, LOW: 1.0},
        ("b", 1): {D: 9.0, LOW: 0.0},
        ("b", 0): {D: 0.0, LOW: 5.0},
        ("c", 0): {D: 4.0, LOW: 0.0},
    })  # fmt: skip
    curve = dict((n, f) for n, _, f in learning_curve(e, D))
    # held out c: n = 1 trains on (a, 0) -> tie -> D: 4 ; n = 2 adds (b, 0) -> D
    # held out a: n = 1 trains on (b, 0) -> D: 1 ;  held out b: n = 1 trains on (a, 0) -> D: 0, 9
    assert curve[1] == pytest.approx((4 + 1 + 0 + 9) / 4)


def test_one_box_gives_no_curve():
    assert learning_curve(errs({("a", 0): {D: 3.0}}), D) == []


# Round 2: what the read-only reviewer found (docs/muse-code/learning-review-1.json)


def test_training_runs_with_no_eligible_candidate_raise():
    e = errs({("a", 0): {LOW: 0.0}, ("a", 1): {HIGH: 0.0}})
    with pytest.raises(ValueError):
        fit(e, {("a", 0), ("a", 1)}, D)
    with pytest.raises(ValueError):
        fit(errs({("a", 0): {LOW: 0.0}}), {("a", 0), ("a", 9)}, D)


def test_a_run_given_twice_counts_once():
    e = errs({("a", 0): {D: 0.0, LOW: 6.0}, ("a", 1): {D: 10.0, LOW: 6.0}})
    # as a set: D 5.0 against LOW 6.0; counting (a, 1) twice would make D 6.7 and pick LOW
    assert fit(e, [("a", 1), ("a", 1), ("a", 0)], D) == fit(e, {("a", 0), ("a", 1)}, D) == D
    assert mae_of(e, LOW, [("a", 0), ("a", 0), ("a", 1)]) == pytest.approx(6.0)


def test_duplicate_errors_for_one_run_and_candidate_raise():
    e = [RunError("a", 0, D, 1.0), RunError("a", 0, D, 99.0)]
    with pytest.raises(ValueError):
        mae_of(e, D, {("a", 0)})
    with pytest.raises(ValueError):
        fit(e, None, D)
    with pytest.raises(ValueError):
        leave_one_box_out(e + [RunError("b", 0, D, 1.0)], D)


def test_nan_anywhere_raises_even_on_a_run_or_candidate_not_used():
    e = errs({("a", 0): {D: 1.0, LOW: math.nan}, ("a", 1): {D: 2.0}})
    with pytest.raises(ValueError):
        fit(e, {("a", 0), ("a", 1)}, D)  # LOW is not eligible, its NaN is still a bug
    with pytest.raises(ValueError):
        fit(errs({("a", 0): {D: 1.0}, ("b", 0): {D: math.inf}}), {("a", 0)}, D)
    with pytest.raises(ValueError):
        learning_curve(errs({("a", 0): {D: 1.0}, ("b", 0): {D: 1.0, LOW: math.nan}}), D)


def test_a_default_with_no_error_on_a_held_out_run_raises():
    e = errs({("a", 0): {LOW: 0.0}, ("b", 0): {LOW: 4.0}})
    with pytest.raises(ValueError):
        leave_one_box_out(e, D)
