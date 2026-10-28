"""Drill hole aggregation by depth (geometry.log_hole): the spec Muse Code builds against.

A hole is the approved boxes of one drill hole laid end to end by depth.

- ``pieces_at_depth`` turns run pieces (cm from the run start) into depths in metres
  (``from_m + cm / 100``), keeps the break flags, cuts the piece that crosses ``to_m``
  and drops pieces that start at or after it.
- ``log_hole`` takes every ``BoxRun`` of the hole, in any order:
  - ``boxes``: one ``(box, from_m, to_m)`` per box number, from its runs as given,
    sorted by ``from_m``.
  - ``issues``: between boxes next to each other by depth, a ``gap`` when the next box
    starts more than ``DEPTH_TOL_M`` after the previous one ends, and an ``overlap`` when
    it starts more than ``DEPTH_TOL_M`` before. An overlap runs from the next box's start
    to the earlier of both ends.
  - In an overlap the earlier box wins: the next box's runs and pieces are cut to start
    where the previous box ends, and a run left empty is dropped. It never raises.
  - ``runs``: one ``IntervalLog`` per run, by depth. Parts of one run split between two
    boxes (``complete=False`` on both, different boxes, contiguous within
    ``DEPTH_TOL_M``) are joined into one run from the first part's ``from_m`` to the
    last part's ``to_m``. Break flags are kept as given.
  - ``intervals``: fixed intervals on a grid at multiples of ``step_m``, cut to the depth
    the boxes cover (contiguous boxes are one stretch; a gap has no interval). An interval
    shorter than ``DEPTH_TOL_M`` is skipped. A piece that crosses an interval boundary is
    cut there; the cut is not a fracture.
  - ``zones``: runs of at least ``zone_min_intervals`` consecutive, contiguous intervals
    with ``rqd_pct < zone_max_rqd``. Zone RQD is weighted by length
    (sum of ``rqd_cm`` / sum of ``run_length_cm`` x 100).
  - ``ValueError`` for no runs, a step that is not a positive finite number, or
    ``zone_min_intervals < 1``.
"""

import pytest

from coresight.geometry import (
    DEPTH_TOL_M,
    BoxRun,
    DepthIssue,
    DepthPiece,
    Piece,
    log_hole,
    log_interval,
    pieces_at_depth,
)


def run(box, from_m, to_m, lengths_cm, complete=True):
    """A run with consecutive pieces from its top; what they do not fill is lost core."""
    pos, pieces = from_m, []
    for length in lengths_cm:
        pieces.append(DepthPiece(round(pos, 6), round(pos + length / 100, 6)))
        pos += length / 100
    return BoxRun(box, from_m, to_m, tuple(pieces), complete)


def near(rows):
    """Compare a list of tuples number by number (pytest.approx is flat)."""
    return [pytest.approx(r) for r in rows]


def spans(logs):
    return [(x.from_m, x.to_m) for x in logs]


def two_onkalo_boxes():
    """Shaped like ONK-DTPH5.1 boxes 5 and 6: contiguous at 22.60 m."""
    return [
        run(5, 17.94, 20.71, [120, 80, 77]),
        run(5, 20.71, 22.60, [100, 89]),
        run(6, 22.60, 23.66, [50, 56]),
        run(6, 23.66, 26.70, [150, 154]),
    ]


# --- pieces_at_depth ---------------------------------------------------------


def test_pieces_at_depth_converts_cm_to_metres_and_keeps_flags():
    pieces = [Piece(0, 30), Piece(30, 80, mechanical_break_after=True), Piece(80, 95)]
    out = pieces_at_depth(pieces, 10.0, 11.0)
    assert spans(out) == near([(10.0, 10.3), (10.3, 10.8), (10.8, 10.95)])
    assert out[1].mechanical_break_after and not out[0].mechanical_break_after


def test_pieces_at_depth_cuts_at_run_end():
    pieces = [Piece(0, 90, uncertain_break_after=True), Piece(90, 130), Piece(130, 150)]
    out = pieces_at_depth(pieces, 2.0, 3.0)
    assert spans(out) == near([(2.0, 2.9), (2.9, 3.0)])
    assert out[0].uncertain_break_after


# --- boxes and issues --------------------------------------------------------


def test_boxes_sorted_by_depth_whatever_the_input_order():
    hole = log_hole(list(reversed(two_onkalo_boxes())))
    assert list(hole.boxes) == near([(5, 17.94, 22.60), (6, 22.60, 26.70)])
    assert hole.issues == ()


def test_contiguous_within_tolerance_is_not_an_issue():
    runs = [run(1, 0.0, 1.0, [100]), run(2, 1.0 + DEPTH_TOL_M / 2, 2.0, [99])]
    assert log_hole(runs).issues == ()


def test_gap_between_boxes_is_reported():
    runs = [run(1, 0.0, 3.414, [100, 100, 100]), run(3, 5.791, 8.016, [100, 100])]
    hole = log_hole(runs)
    assert hole.issues == (DepthIssue("gap", 3.414, 5.791, 1, 3),)


def test_overlap_is_reported_and_the_earlier_box_wins():
    runs = [run(1, 0.0, 2.0, [100, 100]), run(2, 1.8, 3.0, [60, 60])]
    hole = log_hole(runs)
    assert len(hole.issues) == 1
    issue = hole.issues[0]
    assert (issue.kind, issue.box_before, issue.box_after) == ("overlap", 1, 2)
    assert (issue.from_m, issue.to_m) == pytest.approx((1.8, 2.0))
    # box 2 is cut to start at 2.0 m: its run is 2.0-3.0 with 40 + 60 cm of core
    assert spans(hole.runs) == near([(0.0, 2.0), (2.0, 3.0)])
    assert hole.runs[1].recovered_cm == pytest.approx(100.0)


def test_run_inside_an_overlap_is_dropped():
    runs = [run(1, 0.0, 2.0, [200]), run(2, 1.5, 1.9, [40]), run(2, 1.9, 3.0, [110])]
    hole = log_hole(runs)
    assert spans(hole.runs) == near([(0.0, 2.0), (2.0, 3.0)])


# --- runs --------------------------------------------------------------------


def test_complete_runs_match_log_interval():
    runs = two_onkalo_boxes()
    hole = log_hole(runs)
    assert len(hole.runs) == 4
    for got, r in zip(hole.runs, runs, strict=True):
        cm = [Piece((p.from_m - r.from_m) * 100, (p.to_m - r.from_m) * 100) for p in r.pieces]
        want = log_interval(cm, r.from_m, r.to_m)
        assert (got.from_m, got.to_m) == pytest.approx((want.from_m, want.to_m))
        assert got.rqd_pct == pytest.approx(want.rqd_pct)
        assert got.tcr_pct == pytest.approx(want.tcr_pct)
        assert got.natural_fractures == want.natural_fractures


def test_run_split_between_two_boxes_is_joined():
    runs = [
        run(1, 9.0, 10.0, [100]),
        run(1, 10.0, 10.5, [30, 20], complete=False),
        run(2, 10.5, 11.0, [50], complete=False),
        run(2, 11.0, 12.0, [100]),
    ]
    hole = log_hole(runs)
    assert spans(hole.runs) == near([(9.0, 10.0), (10.0, 11.0), (11.0, 12.0)])
    joined = hole.runs[1]
    assert joined.run_length_cm == pytest.approx(100.0)
    assert joined.recovered_cm == pytest.approx(100.0)
    assert joined.intact_piece_lengths_cm == pytest.approx((30.0, 20.0, 50.0))
    assert joined.rqd_pct == pytest.approx(100.0)
    assert joined.natural_fractures == 2


def test_parts_across_a_gap_are_not_joined():
    runs = [run(1, 3.078, 3.414, [33], complete=False), run(3, 5.791, 6.126, [8, 8], False)]
    hole = log_hole(runs)
    assert len(hole.runs) == 2


def test_complete_runs_are_never_joined():
    runs = [run(5, 20.71, 22.60, [189]), run(6, 22.60, 23.66, [106])]
    assert len(log_hole(runs).runs) == 2


# --- fixed intervals ---------------------------------------------------------


def test_intervals_on_a_grid_cut_to_the_covered_depth():
    hole = log_hole(two_onkalo_boxes())
    bounds = [(i.from_m, i.to_m) for i in hole.intervals]
    assert bounds[0] == pytest.approx((17.94, 18.0))
    assert bounds[1] == pytest.approx((18.0, 19.0))
    assert bounds[-1] == pytest.approx((26.0, 26.7))
    assert len(bounds) == 10
    for a, b in zip(bounds, bounds[1:], strict=False):
        assert b[0] == pytest.approx(a[1])


def test_a_cut_at_an_interval_boundary_is_not_a_fracture():
    hole = log_hole([run(1, 0.0, 2.0, [150, 50])])
    first, second = hole.intervals
    assert (first.rqd_pct, first.natural_fractures) == pytest.approx((100.0, 0))
    assert second.intact_piece_lengths_cm == pytest.approx((50.0, 50.0))
    assert second.natural_fractures == 1


def test_intervals_follow_the_step():
    hole = log_hole([run(1, 0.0, 3.0, [100, 100, 100])], step_m=1.5)
    assert spans(hole.intervals) == near([(0.0, 1.5), (1.5, 3.0)])


def test_no_interval_in_a_gap():
    runs = [run(1, 0.0, 1.5, [150]), run(2, 3.2, 4.0, [80])]
    assert spans(log_hole(runs).intervals) == near([(0.0, 1.0), (1.0, 1.5), (3.2, 4.0)])


def test_sliver_shorter_than_tolerance_is_skipped():
    runs = [run(1, 0.995, 2.0, [100.5])]
    assert spans(log_hole(runs).intervals) == near([(1.0, 2.0)])


def test_recovered_core_is_the_same_by_run_and_by_interval():
    runs = two_onkalo_boxes() + [run(7, 26.70, 29.0, [8, 9, 7, 6, 40])]
    hole = log_hole(runs)
    by_run = sum(r.recovered_cm for r in hole.runs)
    by_interval = sum(i.recovered_cm for i in hole.intervals)
    assert by_interval == pytest.approx(by_run)


def test_lost_core_lowers_tcr_of_the_interval_where_it_is_missing():
    hole = log_hole([run(1, 0.0, 2.0, [100, 50])])
    assert [i.tcr_pct for i in hole.intervals] == pytest.approx([100.0, 50.0])


# --- weak zones --------------------------------------------------------------


def broken(box, from_m, to_m):
    """A metre of 5 cm pieces: RQD 0."""
    n = round((to_m - from_m) * 20)
    return run(box, from_m, to_m, [5] * n)


def sound(box, from_m, to_m):
    return run(box, from_m, to_m, [round((to_m - from_m) * 100)])


def test_consecutive_poor_intervals_make_a_zone():
    runs = [sound(1, 0, 1), broken(1, 1, 2), broken(1, 2, 3), sound(2, 3, 4)]
    hole = log_hole(runs)
    assert len(hole.zones) == 1
    zone = hole.zones[0]
    assert (zone.from_m, zone.to_m) == pytest.approx((1.0, 3.0))
    assert (zone.rqd_pct, zone.min_rqd_pct, zone.intervals) == pytest.approx((0.0, 0.0, 2))


def test_a_single_poor_interval_is_not_a_zone():
    runs = [sound(1, 0, 1), broken(1, 1, 2), sound(1, 2, 3)]
    assert log_hole(runs).zones == ()


def test_zone_rqd_is_length_weighted():
    # 0-1 m: a 45 cm piece and 55 cm of 5 cm pieces, RQD 45; 1-2 m: RQD 0; 2-2.5 m: RQD 100
    runs = [run(1, 0, 1, [45] + [5] * 11), broken(1, 1, 2), sound(1, 2, 2.5)]
    hole = log_hole(runs)
    zone = hole.zones[0]
    assert (zone.from_m, zone.to_m) == pytest.approx((0.0, 2.0))
    assert zone.rqd_pct == pytest.approx(22.5)
    assert zone.min_rqd_pct == pytest.approx(0.0)


def test_a_gap_splits_a_zone():
    runs = [broken(1, 0, 1), broken(1, 1, 2), broken(3, 5, 6)]
    hole = log_hole(runs)
    assert spans(hole.zones) == near([(0.0, 2.0)])


def test_zone_threshold_and_minimum_are_parameters():
    runs = [sound(1, 0, 1), broken(1, 1, 2), sound(1, 2, 3)]
    hole = log_hole(runs, zone_max_rqd=101.0, zone_min_intervals=1)
    assert [(z.from_m, z.to_m, z.intervals) for z in hole.zones] == near([(0, 3, 3)])


# --- errors ------------------------------------------------------------------


@pytest.mark.parametrize("step", [0.0, -1.0, float("nan"), float("inf")])
def test_bad_step_raises(step):
    with pytest.raises(ValueError):
        log_hole(two_onkalo_boxes(), step_m=step)


def test_no_runs_raises():
    with pytest.raises(ValueError):
        log_hole([])


def test_zone_minimum_below_one_raises():
    with pytest.raises(ValueError):
        log_hole(two_onkalo_boxes(), zone_min_intervals=0)
