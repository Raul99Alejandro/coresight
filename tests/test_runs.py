import pytest

from coresight.pipeline import build_logs
from coresight.runs import Position, RunMismatchError, assign_runs, dedupe_markers
from coresight.schemas import Interval
from coresight.segmentation import RowPieces, default_breaks

PPC = 10.0  # px per cm


def row(*pieces_cm, cuts_cm=(), breaks=None):
    intervals = [(a * PPC, b * PPC) for a, b in pieces_cm]
    cuts = [c * PPC for c in cuts_cm]
    return RowPieces("sam", PPC, intervals, cuts, breaks or default_breaks(intervals, cuts))


def runs(*bounds):
    return [Interval(from_m=a, to_m=b) for a, b in zip(bounds, bounds[1:], strict=False)]


def test_marker_splits_the_rows_into_runs():
    # row 0: 40 + 50 cm, marker at 95 cm; row 1: 30 + 5 + 60 cm
    rows = [row((0, 40), (42, 92)), row((0, 30), (31, 36), (38, 98))]
    logs = assign_runs(rows, [Position(0, 95)], runs(10.0, 11.0, 12.0), True)
    (r1, first, c1), (r2, second, c2) = logs
    assert first.recovered_cm == pytest.approx(90)
    assert first.rqd_pct == pytest.approx(90)
    assert second.recovered_cm == pytest.approx(95)
    assert second.rqd_pct == pytest.approx(90)  # the 5 cm piece does not count
    assert c1 and not c2  # the last run has no marker at its end in this box


def test_first_run_is_incomplete_when_it_started_in_the_previous_box():
    rows = [row((0, 40), (42, 92)), row((0, 90))]
    logs = assign_runs(rows, [Position(0, 95)], runs(10.0, 11.0, 12.0), False)
    assert [complete for _, _, complete in logs] == [False, False]


def test_a_marker_at_the_end_of_the_last_run_completes_it():
    rows = [row((0, 90)), row((0, 90))]
    markers = [Position(0, 95), Position(1, 95)]
    logs = assign_runs(rows, markers, runs(0.0, 1.0, 2.0), True)
    assert [complete for _, _, complete in logs] == [True, True]


def test_row_ends_and_profile_cuts_are_uncertain_breaks():
    rows = [row((0, 30), (30, 60), cuts_cm=(30,)), row((0, 40))]
    [(_, log, _)] = assign_runs(rows, [Position(1, 45)], runs(0.0, 1.0), True)
    assert log.natural_fractures == 2
    assert log.uncertain_breaks == 2


def test_piece_across_a_marker_is_split_there():
    rows = [row((0, 80))]
    logs = assign_runs(rows, [Position(0, 50)], runs(0.0, 0.5, 1.0), True)
    assert logs[0][1].recovered_cm == pytest.approx(50)
    assert logs[1][1].recovered_cm == pytest.approx(30)


def test_marker_count_must_fit_the_run_list():
    with pytest.raises(RunMismatchError):
        assign_runs([row((0, 90))], [], runs(0.0, 1.0, 2.0, 3.0), True)


def test_same_block_seen_in_two_rows_counts_once():
    markers = [Position(0, 100.5), Position(1, 102.0), Position(1, 40.0)]
    assert dedupe_markers(markers) == [Position(0, 100.5), Position(1, 40.0)]


def test_build_logs_returns_validated_results():
    rows = [row((0, 40), (42, 92)), row((0, 90))]
    [first, second] = build_logs(rows, [Position(0, 95)], runs(10.0, 11.0, 12.0), True)
    assert first.rqd_pct == 90.0 and first.rock_quality == "excellent"
    assert first.complete and not second.complete
    assert first.fracture_frequency_per_m == pytest.approx(1.0)


def test_mechanical_breaks_are_rejoined_and_possible_ones_are_not():
    breaks = ["mechanical", "possible_mechanical", "uncertain"]
    rows = [row((0, 8), (8, 16), (16, 22), breaks=breaks)]
    [(_, log, _)] = assign_runs(rows, [Position(0, 25)], runs(0.0, 0.3), True)
    assert log.mechanical_breaks == 1
    assert log.intact_piece_lengths_cm == pytest.approx((16, 6))
    assert log.uncertain_breaks == 1  # the possible mechanical one; the last is the run end
