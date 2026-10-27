import pytest

from coresight.evaluation import (
    bias,
    bland_altman,
    class_agreement,
    cluster_bootstrap,
    mae,
)


def test_mae_and_bias():
    assert mae([-2, 2, 4]) == pytest.approx(8 / 3)
    assert bias([-2, 2, 4]) == pytest.approx(4 / 3)


def test_bootstrap_contains_the_estimate_and_is_reproducible():
    errors = [1, -3, 5, 2, -8, 0, 4, -1]
    boxes = ["a", "a", "b", "b", "c", "c", "d", "d"]
    ci = cluster_bootstrap(errors, boxes, n_resamples=2000, seed=1)
    assert ci.value == pytest.approx(mae(errors))
    assert ci.low <= ci.value <= ci.high
    assert ci == cluster_bootstrap(errors, boxes, n_resamples=2000, seed=1)


def test_bootstrap_resamples_whole_boxes():
    # Every box has the same mean absolute error, so every resample has it too.
    errors = [2, -2, 6, -6, 4, -4]
    boxes = ["a", "a", "b", "b", "c", "c"]
    same = [3, -3, 3, -3, 3, -3]
    ci = cluster_bootstrap(same, boxes, n_resamples=500)
    assert ci.low == ci.high == pytest.approx(3)
    wide = cluster_bootstrap(errors, boxes, n_resamples=500)
    assert 2 <= wide.low <= wide.high <= 6  # box MAEs are 2, 6 and 4


def test_bootstrap_rejects_bad_input():
    with pytest.raises(ValueError):
        cluster_bootstrap([1, 2], ["a"])
    with pytest.raises(ValueError):
        cluster_bootstrap([], [])


def test_bland_altman():
    ba = bland_altman([12, 20, 33, 41], [10, 20, 30, 40])
    assert ba.n == 4
    assert ba.bias == pytest.approx(1.5)
    assert ba.diffs == (2, 0, 3, 1)
    assert ba.means == (11, 20, 31.5, 40.5)
    sd = (sum((d - 1.5) ** 2 for d in (2, 0, 3, 1)) / 3) ** 0.5
    assert ba.sd == pytest.approx(sd)
    assert ba.low == pytest.approx(1.5 - 1.96 * sd)
    assert ba.high == pytest.approx(1.5 + 1.96 * sd)


def test_bland_altman_needs_pairs():
    with pytest.raises(ValueError):
        bland_altman([1], [1])
    with pytest.raises(ValueError):
        bland_altman([1, 2], [1, 2, 3])


def test_class_agreement_uses_deere_classes():
    found = [95, 80, 30, 10]
    reference = [92, 91, 60, 20]  # excellent, excellent, fair, very poor
    agree = class_agreement(found, reference)
    assert agree.n == 4
    assert agree.exact == 2  # 95 vs 92 and 10 vs 20
    assert agree.within_one == 4  # good vs excellent, poor vs fair are neighbours
    assert agree.accuracy == pytest.approx(0.5)
    assert agree.confusion[("excellent", "good")] == 1
    assert agree.confusion[("fair", "poor")] == 1


def test_class_agreement_far_miss():
    agree = class_agreement([10], [95])
    assert agree.exact == 0 and agree.within_one == 0
