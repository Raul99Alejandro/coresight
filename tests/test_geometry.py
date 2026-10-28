import math

import pytest

from coresight.geometry import Piece, log_interval, rock_quality_class


def consecutive(lengths_cm, start=0.0):
    pieces, pos = [], start
    for length in lengths_cm:
        pieces.append(Piece(pos, pos + length))
        pos += length
    return pieces


def test_textbook_run():
    log = log_interval(consecutive([38, 17, 5, 10, 7, 43]), 0.0, 2.0)
    assert log.rqd_cm == pytest.approx(108.0)
    assert log.rqd_pct == pytest.approx(54.0)
    assert log.tcr_pct == pytest.approx(60.0)
    assert log.natural_fractures == 5
    assert log.fracture_frequency_per_m == pytest.approx(2.5)
    assert rock_quality_class(log.rqd_pct) == "fair"


def test_mechanical_break_rejoins_pieces():
    pieces = [Piece(0, 6, mechanical_break_after=True), Piece(6, 12), Piece(12, 100)]
    log = log_interval(pieces, 10.0, 11.0)
    assert log.rqd_cm == pytest.approx(100.0)
    assert log.natural_fractures == 1
    assert log.intact_pieces == 2
    assert log.intact_piece_lengths_cm == pytest.approx((12.0, 88.0))
    assert log.mechanical_breaks == 1


def test_uncertain_break_is_counted_and_treated_as_natural():
    pieces = [Piece(0, 40, uncertain_break_after=True), Piece(40, 100)]
    log = log_interval(pieces, 0.0, 1.0)
    assert log.uncertain_breaks == 1
    assert log.natural_fractures == 1


def test_break_after_last_piece_is_run_boundary():
    log = log_interval([Piece(0, 100, uncertain_break_after=True)], 0.0, 1.0)
    assert log.uncertain_breaks == 0
    assert log.natural_fractures == 0


def test_piece_longer_than_run_is_clipped():
    log = log_interval([Piece(0, 150)], 0.0, 1.0)
    assert log.tcr_pct == pytest.approx(100.0)
    assert log.rqd_pct == pytest.approx(100.0)


def test_unsorted_input_gives_same_result():
    pieces = consecutive([38, 17, 5, 10, 7, 43])
    assert log_interval(reversed(pieces), 0.0, 2.0) == log_interval(pieces, 0.0, 2.0)


def test_empty_run_is_all_zero():
    log = log_interval([], 0.0, 1.5)
    assert log.rqd_pct == 0
    assert log.tcr_pct == 0
    assert log.natural_fractures == 0
    assert log.fracture_frequency_per_m == 0
    assert log.intact_pieces == 0


@pytest.mark.parametrize(
    "start,end", [(5, 5), (10, 2), (math.nan, 3), (0, math.inf)]
)
def test_invalid_piece_raises(start, end):
    with pytest.raises(ValueError):
        Piece(start, end)


def test_piece_cannot_be_mechanical_and_uncertain():
    with pytest.raises(ValueError):
        Piece(0, 10, mechanical_break_after=True, uncertain_break_after=True)


@pytest.mark.parametrize("from_m,to_m", [(1.0, 1.0), (2.0, 1.0), (math.nan, 1.0)])
def test_invalid_interval_raises(from_m, to_m):
    with pytest.raises(ValueError):
        log_interval([], from_m, to_m)


def test_overlapping_pieces_raise():
    with pytest.raises(ValueError):
        log_interval([Piece(0, 20), Piece(15, 30)], 0.0, 1.0)


@pytest.mark.parametrize(
    "rqd,expected",
    [(0, "very poor"), (24.9, "very poor"), (25, "poor"), (50, "fair"),
     (75, "good"), (90, "excellent"), (100, "excellent")],
)
def test_deere_classes(rqd, expected):
    assert rock_quality_class(rqd) == expected


@pytest.mark.parametrize("rqd", [-1, 101, math.nan])
def test_invalid_rqd_raises(rqd):
    with pytest.raises(ValueError):
        rock_quality_class(rqd)


def test_combined_rqd_weights_each_run_by_its_length():
    from coresight.geometry import combined_rqd

    # 1.5 m at 20 % and 0.5 m at 100 %: 0.3 + 0.5 m intact of 2 m
    assert combined_rqd([(0.0, 1.5, 20.0), (1.5, 2.0, 100.0)]) == pytest.approx(40.0)
    assert combined_rqd([(5.0, 6.0, 33.3)]) == pytest.approx(33.3)
    with pytest.raises(ValueError):
        combined_rqd([])
    with pytest.raises(ValueError):
        combined_rqd([(2.0, 1.0, 50.0)])
