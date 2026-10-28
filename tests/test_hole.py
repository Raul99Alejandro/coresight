"""Drill hole aggregation by depth (geometry.log_hole): the spec Muse Code builds against.

A hole is the approved boxes of one drill hole laid end to end by depth.

- ``pieces_at_depth`` turns run pieces (cm from the run start) into depths in metres
  (``from_m + cm / 100``), keeps the break flags, cuts the piece that crosses ``to_m``
  and drops pieces that start at or after it.
- ``log_hole`` takes every ``BoxRun`` of the hole, in any order:
  - ``boxes``: one ``(box, from_m, to_m)`` per box number, from its runs as given,
    sorted by ``from_m``.
  - One tolerance rule everywhere: two depths are contiguous when the second is at most
    ``DEPTH_TOL_M`` past the first; more than that is a gap.
  - ``issues``: walking the boxes by depth, each box is compared with the deepest end
    reached so far (and the box that reached it). A ``gap`` when the box starts more than
    ``DEPTH_TOL_M`` after that end, an ``overlap`` when it starts more than ``DEPTH_TOL_M``
    before it. An overlap runs from the box's start to the earlier of both ends. A box
    inside another is an overlap, never a gap.
  - In an overlap the earlier box wins: the later box's runs and pieces are cut to start
    where the earlier coverage ends, and a run left empty is dropped. It never raises.
  - Runs of the same box must not overlap by more than ``DEPTH_TOL_M``: ``ValueError``
    that names the box. The same run given twice is such an overlap. An overlap of up to
    ``DEPTH_TOL_M`` (rounding) is cut like one between boxes: the earlier run wins.
  - A gap between runs of the same box is a ``gap`` issue too (``box_before`` and
    ``box_after`` are that box). The depth the boxes cover is the union of their runs,
    so a gap inside a box has no interval either.
  - ``runs``: one ``IntervalLog`` per run, by depth. Parts of one run split between two
    boxes (``complete=False`` on both, different boxes, contiguous within
    ``DEPTH_TOL_M``) are joined into one run from the first part's ``from_m`` to the
    last part's ``to_m``. Break flags are kept as given.
  - ``intervals``: fixed intervals on a grid at multiples of ``step_m``, cut to the depth
    the boxes cover (contiguous boxes are one stretch; a gap has no interval). At each end
    of a stretch, an interval shorter than half a step is merged into its neighbour, so
    edge intervals run up to 1.5 steps and no core is dropped; a stretch shorter than that
    is one interval.
  - Intervals agree with the runs:
    - RQD: the intact pieces of each run (after mechanical breaks are rejoined, never
      across a run end) are cut at the interval bounds; parts of 10 cm or more count. A
      piece that crosses an interval boundary is cut there; the cut is not a fracture.
      The part of an intact piece in an interval is the core of its pieces in it: lost
      core between two rejoined pieces is never core, as in ``log_interval``.
    - TCR: recovered core inside the interval / interval length.
    - Fractures: every natural or uncertain break that its run log counts is counted in
      exactly one interval, the one that contains its depth; a break on an interval
      boundary (within floating point error, as with ``3 * 0.3``) goes to the interval
      above. A run end is never a fracture. So
      over intervals that cover the runs, fractures and uncertain breaks add up to the
      runs' totals. Fracture frequency = fractures / interval length.
    - RQD and TCR come from ``log_interval`` on the cut intact pieces; the fracture counts
      follow the rule above.
  - ``zones``: runs of at least ``zone_min_intervals`` consecutive, contiguous intervals
    with ``rqd_pct < zone_max_rqd``. Zone RQD is weighted by length
    (sum of ``rqd_cm`` / sum of ``run_length_cm`` x 100).
  - ``ValueError`` for no runs, a step that is not a finite number of at least 0.1 m,
    or ``zone_min_intervals < 1``.
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


def test_depth_piece_cannot_be_mechanical_and_uncertain():
    with pytest.raises(ValueError):
        DepthPiece(0.0, 1.0, mechanical_break_after=True, uncertain_break_after=True)


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


def test_box_inside_another_is_an_overlap_not_a_gap():
    runs = [run(1, 0.0, 10.0, [1000]), run(2, 2.0, 3.0, [100]), run(3, 4.0, 5.0, [100])]
    hole = log_hole(runs)
    assert [(i.kind, i.from_m, i.to_m, i.box_before, i.box_after) for i in hole.issues] == [
        ("overlap", 2.0, 3.0, 1, 2),
        ("overlap", 4.0, 5.0, 1, 3),
    ]
    assert spans(hole.runs) == near([(0.0, 10.0)])


def test_one_tolerance_rule_for_gaps_joins_and_zones():
    gap = DEPTH_TOL_M * 1.05
    runs = [
        broken(1, 0.0, 1.0),
        run(1, 1.0, 2.0, [5] * 20, complete=False),
        run(2, 2.0 + gap, 3.0, [5] * 19, complete=False),
        broken(2, 3.0, 4.0),
    ]
    hole = log_hole(runs)
    assert [i.kind for i in hole.issues] == ["gap"]
    assert len(hole.runs) == 4  # not joined across the gap
    assert spans(hole.zones) == near([(0.0, 2.0), (2.0 + gap, 4.0)])


def test_runs_of_one_box_that_overlap_by_rounding_are_cut():
    hole = log_hole([run(1, 0.0, 1.0, [100]), run(1, 0.995, 1.995, [100])])
    assert spans(hole.runs) == near([(0.0, 1.0), (1.0, 1.995)])
    assert sum(r.recovered_cm for r in hole.runs) == pytest.approx(199.5)
    assert sum(i.recovered_cm for i in hole.intervals) == pytest.approx(199.5)
    assert hole.issues == ()


def test_gap_between_runs_of_one_box_has_no_interval():
    hole = log_hole([run(1, 0.0, 1.0, [100]), run(1, 2.0, 3.0, [100])])
    assert hole.issues == (DepthIssue("gap", 1.0, 2.0, 1, 1),)
    assert spans(hole.intervals) == near([(0.0, 1.0), (2.0, 3.0)])
    assert hole.zones == ()


def test_runs_of_one_box_that_overlap_raise():
    with pytest.raises(ValueError, match="box 1"):
        log_hole([run(1, 0.0, 2.0, [100]), run(1, 1.0, 3.0, [100])])


def test_the_same_run_twice_raises():
    with pytest.raises(ValueError, match="box 1"):
        log_hole([run(1, 0.0, 1.0, [100]), run(1, 0.0, 1.0, [100])])


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
    assert bounds[0] == pytest.approx((17.94, 19.0))  # 6 cm edge merged
    assert bounds[1] == pytest.approx((19.0, 20.0))
    assert bounds[-1] == pytest.approx((26.0, 26.7))  # 70 cm edge kept
    assert len(bounds) == 9
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


def test_short_edge_is_merged_and_keeps_its_core():
    hole = log_hole([run(1, 0.995, 2.0, [100.5])])
    assert spans(hole.intervals) == near([(0.995, 2.0)])
    assert hole.intervals[0].recovered_cm == pytest.approx(100.5)


def test_both_short_edges_are_merged():
    hole = log_hole([run(1, 0.8, 3.3, [250])])
    assert spans(hole.intervals) == near([(0.8, 2.0), (2.0, 3.3)])


def test_stretch_shorter_than_a_step_is_one_interval():
    assert spans(log_hole([run(1, 0.8, 1.3, [50])]).intervals) == near([(0.8, 1.3)])
    assert spans(log_hole([run(1, 3.2, 3.4, [20])]).intervals) == near([(3.2, 3.4)])


def test_core_and_fractures_add_up_the_same_by_run_and_by_interval():
    runs = two_onkalo_boxes() + [
        run(7, 26.70, 29.0, [8, 9, 7, 6, 40]),
        run(7, 29.0, 29.4, [12, 13], complete=False),
        run(8, 29.4, 30.05, [30, 35], complete=False),
        run(8, 30.05, 31.0, [5, 5, 5, 80]),
    ]
    hole = log_hole(runs)
    for field in ("recovered_cm", "natural_fractures", "uncertain_breaks"):
        by_run = sum(getattr(r, field) for r in hole.runs)
        by_interval = sum(getattr(i, field) for i in hole.intervals)
        assert by_interval == pytest.approx(by_run), field


def test_lost_core_lowers_tcr_of_the_interval_where_it_is_missing():
    hole = log_hole([run(1, 0.0, 2.0, [100, 50])])
    assert [i.tcr_pct for i in hole.intervals] == pytest.approx([100.0, 50.0])


def test_break_on_an_interval_boundary_goes_to_the_interval_above():
    hole = log_hole([run(1, 0.0, 2.0, [100, 100])])
    assert [i.natural_fractures for i in hole.intervals] == [1, 0]
    assert hole.intervals[0].fracture_frequency_per_m == pytest.approx(1.0)
    assert hole.runs[0].natural_fractures == 1


def test_uncertain_break_on_a_boundary_is_counted_for_review():
    pieces = (DepthPiece(0.0, 1.0, uncertain_break_after=True), DepthPiece(1.0, 2.0))
    hole = log_hole([BoxRun(1, 0.0, 2.0, pieces)])
    assert [i.uncertain_breaks for i in hole.intervals] == [1, 0]
    assert [i.natural_fractures for i in hole.intervals] == [1, 0]


def test_mechanical_break_on_a_boundary_is_not_a_fracture():
    pieces = (DepthPiece(0.0, 1.0, mechanical_break_after=True), DepthPiece(1.0, 2.0))
    hole = log_hole([BoxRun(1, 0.0, 2.0, pieces)])
    assert [i.natural_fractures for i in hole.intervals] == [0, 0]
    assert [i.rqd_pct for i in hole.intervals] == pytest.approx([100.0, 100.0])


def test_break_on_a_floating_point_boundary_goes_to_the_interval_above():
    # 3 * 0.3 is 0.8999999999999999 in floating point; the break is at 0.9 m
    hole = log_hole([run(1, 0.0, 1.2, [90, 30])], step_m=0.3)
    assert [i.natural_fractures for i in hole.intervals] == [0, 0, 1, 0]


def test_lost_core_between_rejoined_pieces_is_not_core():
    pieces = (DepthPiece(0.0, 0.5, mechanical_break_after=True), DepthPiece(0.6, 1.0))
    hole = log_hole([BoxRun(1, 0.0, 1.0, pieces)])
    (r,), (i,) = hole.runs, hole.intervals
    assert (r.rqd_pct, r.tcr_pct) == pytest.approx((90.0, 90.0))
    assert (i.rqd_pct, i.tcr_pct, i.recovered_cm) == pytest.approx((90.0, 90.0, 90.0))


def test_run_end_inside_an_interval_is_not_a_fracture():
    hole = log_hole([run(1, 0.0, 0.5, [50]), run(1, 0.5, 1.0, [50])])
    (interval,) = hole.intervals
    assert interval.natural_fractures == 0
    assert interval.rqd_pct == pytest.approx(100.0)


def test_mechanical_break_never_rejoins_across_a_run_end():
    first = BoxRun(1, 0.0, 0.5, (DepthPiece(0.0, 0.45), DepthPiece(0.45, 0.5)))
    second = BoxRun(1, 0.5, 1.0, (DepthPiece(0.5, 0.56), DepthPiece(0.56, 1.0)))
    tail = BoxRun(1, 0.0, 0.5, (DepthPiece(0.0, 0.45), DepthPiece(0.45, 0.5, True)))
    plain = log_hole([first, second]).intervals[0]
    joined = log_hole([tail, second]).intervals[0]
    # the 5 cm and 6 cm pieces on both sides of the run end stay apart either way
    assert joined.rqd_pct == pytest.approx(plain.rqd_pct) == pytest.approx(89.0)


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


@pytest.mark.parametrize("step", [0.0, -1.0, 0.05, float("nan"), float("inf")])
def test_bad_step_raises(step):
    with pytest.raises(ValueError):
        log_hole(two_onkalo_boxes(), step_m=step)


def test_no_runs_raises():
    with pytest.raises(ValueError):
        log_hole([])


def test_zone_minimum_below_one_raises():
    with pytest.raises(ValueError):
        log_hole(two_onkalo_boxes(), zone_min_intervals=0)
