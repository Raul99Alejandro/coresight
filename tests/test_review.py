from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from test_calibration import photo

from coresight import review
from coresight.review import ReviewError, ReviewStore
from coresight.schemas import (
    BoxReview,
    GeologyDescription,
    Interval,
    IntervalResult,
    ReviewPiece,
    RunReview,
    TrayCheck,
    TrayView,
)


def make_run(pieces, from_m=10.0, to_m=11.0, described=True) -> RunReview:
    """A run under review: pieces as (row, start_cm, end_cm, break_after)."""
    placeholder = IntervalResult(
        from_m=from_m, to_m=to_m, rqd_pct=0, tcr_pct=0, natural_fractures=0,
        fracture_frequency_per_m=0, uncertain_breaks=0, mechanical_breaks=0,
        rock_quality="very poor", complete=True,
    )  # fmt: skip
    run = RunReview(
        from_m=from_m,
        to_m=to_m,
        pieces=[ReviewPiece(row=r, start_cm=a, end_cm=b, break_after=k) for r, a, b, k in pieces],
        machine_log=placeholder,
        log=placeholder,
    )
    run.machine_log = run.log = review.recompute(run)
    if described:
        d = GeologyDescription(
            lithology="granite gneiss", alteration="none visible",
            mineralization="none visible", confidence=0.7,
        )  # fmt: skip
        run.machine_description = run.description = d
        run.description_backend = "muse-spark-1.3"
    return run


def make_box(*runs: RunReview, status="ready") -> BoxReview:
    return BoxReview(
        id="abc123",
        hole_id="DDH-1",
        box_number=3,
        source="test",
        status=status,
        created_at=datetime.now(UTC),
        tray=TrayView(width=1000, height=500, px_per_cm=10, rows=[(0, 100)], markers=[]),
        runs=list(runs),
    )


# Run 10-11 m: 40 cm, 8 cm, 45 cm pieces (93 cm recovered).
PIECES = [(0, 0, 40, "natural"), (0, 40, 48, "natural"), (0, 50, 95, "natural")]


def test_recompute_uses_geometry():
    run = make_run(PIECES)
    assert run.log.tcr_pct == pytest.approx(93.0)
    assert run.log.rqd_pct == pytest.approx(85.0)  # the 8 cm piece does not count
    assert run.log.natural_fractures == 2
    assert run.log.rock_quality == "good"


def test_mechanical_break_rejoins_pieces_and_keeps_the_original():
    box = make_box(make_run(PIECES))
    run = review.set_break(box, 0, 1, "mechanical")  # 8 cm piece joins the 45 cm one
    assert run.log.rqd_pct == pytest.approx(93.0)
    assert run.log.natural_fractures == 1
    assert run.log.mechanical_breaks == 1
    assert run.machine_log.rqd_pct == pytest.approx(85.0)
    (c,) = run.corrections
    assert (c.target, c.original, c.corrected) == ("break 2", "natural", "mechanical")
    assert c.source == "typed"


def test_the_run_end_break_cannot_be_changed():
    box = make_box(make_run(PIECES))
    with pytest.raises(ReviewError):
        review.set_break(box, 0, 2, "mechanical")


def test_remove_piece_recomputes_and_rule_anomalies_follow():
    box = make_box(make_run(PIECES))
    run = review.remove_piece(box, 0, 2)  # 48 cm left: TCR 48 -> low recovery
    assert run.log.tcr_pct == pytest.approx(48.0)
    assert [a.type for a in run.description.anomalies] == ["low_recovery"]
    assert run.machine_description.anomalies == []
    assert run.corrections[0].corrected == "removed"


def test_split_piece_adds_the_missed_break_and_recomputes():
    box = make_box(make_run(PIECES))
    run = review.split_piece(box, 0, 0, 5.0)  # 40 cm piece -> 5 + 35: only 35 counts
    assert [(p.start_cm, p.end_cm) for p in run.pieces[:2]] == [(0, 5.0), (5.0, 40)]
    assert run.pieces[0].break_after == "natural"
    assert run.pieces[1].break_after == "natural"  # keeps the original break after it
    assert run.log.rqd_pct == pytest.approx(80.0)
    assert run.log.natural_fractures == 3
    assert run.machine_log.rqd_pct == pytest.approx(85.0)
    (c,) = run.corrections
    assert (c.target, c.original) == ("piece 1", "row 1, 0.0-40.0 cm")
    assert c.corrected == "split at 5.0 cm (natural break)"


def test_split_keeps_the_run_end_on_the_last_part():
    box = make_box(make_run(PIECES))
    run = review.split_piece(box, 0, 2, 70.0, kind="mechanical")
    assert [p.break_after for p in run.pieces[2:]] == ["mechanical", "natural"]
    assert run.log.rqd_pct == pytest.approx(85.0)  # rejoined: still one 45 cm piece


@pytest.mark.parametrize("at", [0.2, 39.8, 45.0])
def test_split_must_fall_inside_the_piece(at):
    box = make_box(make_run(PIECES))
    with pytest.raises(ReviewError):
        review.split_piece(box, 0, 0, at)


def test_dictated_description_keeps_transcript_and_original():
    box = make_box(make_run(PIECES))
    run = review.set_description(
        box, 0, "alteration", "weak chloritic", source="voice", transcript="clorítica débil"
    )
    assert run.description.alteration == "weak chloritic"
    assert run.machine_description.alteration == "none visible"
    (c,) = run.corrections
    assert (c.original, c.source, c.transcript) == ("none visible", "voice", "clorítica débil")


def test_unchanged_value_is_not_a_correction():
    box = make_box(make_run(PIECES))
    review.set_description(box, 0, "lithology", "granite gneiss")
    review.set_break(box, 0, 0, "natural")
    assert box.runs[0].corrections == []


def test_geologist_can_write_a_description_the_model_failed_to_give():
    box = make_box(make_run(PIECES, described=False))
    with pytest.raises(ReviewError):
        review.approve(box)
    review.set_description(box, 0, "lithology", "diorite")
    assert box.runs[0].description.lithology == "diorite"
    assert review.approve(box).status == "approved"


def test_an_approved_box_is_locked():
    box = make_box(make_run(PIECES))
    review.approve(box)
    with pytest.raises(ReviewError):
        review.set_description(box, 0, "comment", "late note")
    with pytest.raises(ReviewError):
        review.approve(box)


def test_bad_photo_bytes_are_a_review_error():
    with pytest.raises(ReviewError, match="could not be read"):
        review.decode_photo(b"not an image")


def test_photo_without_a_tray_says_it_has_no_scale():
    ok, png = cv2.imencode(".png", np.full((600, 900, 3), 128, np.uint8))
    with pytest.raises(ReviewError, match="no scale"):
        review.analyze(png.tobytes(), 100.0, [Interval(from_m=1, to_m=2)], True, None, None)


def test_store_round_trip(tmp_path):
    store = ReviewStore(tmp_path)
    box = make_box(make_run(PIECES))
    store.save(box)
    assert store.get("abc123") == box
    assert [b.id for b in store.all()] == ["abc123"]
    with pytest.raises(KeyError):
        store.get("../etc")


def test_mask_overlay_colours_only_the_masked_pixels():
    mask = np.zeros((10, 20), bool)
    mask[2:8, 5:15] = True
    sam = [{"bounds": (0, 0, 20, 10), "mask": mask, "confidence": 0.9}]
    png = review.mask_overlay(sam, (10, 20))
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    assert img.shape == (10, 20, 4)
    assert img[5, 10, 3] > 0 and img[0, 0, 3] == 0


class GateClient:
    """Muse Spark's tray check only; SAM must never be called when the gate refuses."""

    def __init__(self, check):
        self.check, self.sam_calls, self.gates = check, 0, []

    def check_tray(self, png):
        if isinstance(self.check, Exception):
            raise self.check
        return self.check

    def segment_row(self, png, prompt):
        self.sam_calls += 1
        return []


class GateReporter(review.Reporter):
    def __init__(self):
        self.results = []

    def gate(self, result):
        self.results.append(result)


def tray_photo() -> bytes:
    return cv2.imencode(".png", photo())[1].tobytes()


def test_spark_refusal_stops_the_analysis_before_sam():
    client = GateClient(TrayCheck(is_core_tray=False, what_it_shows="a web page", confidence=1.0))
    report = GateReporter()
    with pytest.raises(ReviewError, match="not a core tray: a web page"):
        review.analyze(tray_photo(), 100.0, [Interval(from_m=1, to_m=2)], True, client, None,
                       report=report)  # fmt: skip
    assert client.sam_calls == 0
    assert [r.signal for r in report.results[0].reasons] == ["spark"]


def test_a_real_screenshot_is_refused_by_calibration_without_spark():
    png = (Path(__file__).parent / "data" / "screenshot_glyphs.jpg").read_bytes()
    client = GateClient(RuntimeError("Muse Spark is down"))  # an outage: the others decide
    with pytest.raises(ReviewError, match="no scale to measure in cm"):
        review.analyze(png, 100.0, [Interval(from_m=1, to_m=2)], True, client, None)
    assert client.sam_calls == 0


# SAM with a click (point C)


def cut(start_cm, end_cm, row=0) -> review.PointMask:
    return review.PointMask(row, start_cm, end_cm, 0.95, b"png", 3.4)


def spans(run):
    return [(p.row, p.start_cm, p.end_cm, p.break_after) for p in run.pieces]


def test_a_tap_where_a_break_is_missing_splits_the_piece_at_the_mask():
    box = make_box(make_run(PIECES))
    run, changed = review.sam_piece(box, 0, cut(50, 70.4), 1)
    assert changed
    assert spans(run)[2:] == [(0, 50, 70.4, "natural"), (0, 70.4, 95, "natural")]
    assert run.log.natural_fractures == 3
    c = run.corrections[-1]
    assert c.source == "sam-point" and c.target == "row 1, 50.0-70.4 cm"
    assert c.original == "1 piece: 50.0-95.0 cm"
    assert c.corrected == "one piece 50.0-70.4 cm from the SAM 3.1 mask (1 point)"
    assert [p.end_cm for p in c.pieces_before] == [40, 48, 95]


def test_a_tap_where_a_break_is_extra_joins_the_pieces_the_mask_covers():
    box = make_box(make_run(PIECES))
    run, changed = review.sam_piece(box, 0, cut(0.4, 47.6), 2)
    assert changed
    # both mask ends are within 1 cm of the row's breaks, so they snap to them
    assert spans(run) == [(0, 0, 48, "natural"), (0, 50, 95, "natural")]
    assert run.log.rqd_pct > run.machine_log.rqd_pct
    assert run.corrections[-1].original == "2 pieces: 0.0-40.0, 40.0-48.0 cm"


def test_a_piece_sam_finds_in_an_empty_stretch_is_added():
    box = make_box(make_run([(0, 0, 40, "natural"), (0, 60, 95, "natural")]))
    run, _ = review.sam_piece(box, 0, cut(42, 57), 1)
    assert spans(run)[1] == (0, 42, 57, "natural")
    assert run.corrections[-1].original == "0 pieces"


def test_the_run_end_stays_on_the_piece_that_reaches_it():
    box = make_box(make_run([(0, 0, 40, "natural"), (0, 40, 95, "uncertain")]))
    run, _ = review.sam_piece(box, 0, cut(0, 95.3), 1)
    assert spans(run) == [(0, 0, 95, "uncertain")]


def test_a_mask_that_agrees_with_the_pieces_is_not_a_correction():
    box = make_box(make_run(PIECES))
    run, changed = review.sam_piece(box, 0, cut(50.3, 94.6), 1)
    assert not changed and run.corrections == []


def test_a_refining_tap_replaces_the_last_sam_correction():
    box = make_box(make_run(PIECES))
    review.sam_piece(box, 0, cut(0.4, 70), 1)  # spilled over two breaks
    run, changed = review.sam_piece(box, 0, cut(0.4, 39.7), 2, refine=True)
    assert changed  # back as it was, so the spilled correction is gone
    assert spans(run) == [(0, p[1], p[2], p[3]) for p in PIECES]
    assert run.corrections == [] and run.log == run.machine_log


def test_the_mask_is_clipped_to_the_run_it_was_tapped_in():
    first = make_run([(0, 0, 40, "natural")], 10.0, 10.4)
    second = make_run([(0, 42, 95, "natural")], 10.4, 11.0)
    box = make_box(first, second)
    run, _ = review.sam_piece(box, 1, cut(30, 70), 1)
    assert spans(run) == [(0, 40, 70, "natural"), (0, 70, 95, "natural")]
    box.tray.markers = [(0, 41.0)]  # the run block between the two runs
    run, _ = review.sam_piece(box, 1, cut(30, 70), 1, refine=True)
    assert spans(run)[0] == (0, 42, 70, "natural")  # the block, snapped to the piece start
    with pytest.raises(ReviewError, match="not in run 1"):
        review.sam_piece(box, 0, cut(50, 90), 1)


def test_sam_point_mask_measures_the_mask_not_its_box(monkeypatch):
    view = TrayView(width=1000, height=200, px_per_cm=10, rows=[(0, 100), (100, 200)], markers=[])
    image = np.full((200, 1000, 3), 128, np.uint8)
    seen = {}

    def fake_row_masks(client, crop, cache_dir, prompt):
        seen["prompt"], seen["shape"] = prompt, crop.shape
        m = np.zeros((90, 500), dtype=bool)
        m[20:70, 100:400] = True  # the piece: x 200-500 of the row
        m[45:47, 400:500] = True  # a thin spill the box would include
        return [{"id": 1, "bounds": (100, 5, 600, 95), "confidence": 0.95, "mask": m}]

    monkeypatch.setattr(review, "row_masks", fake_row_masks)
    pm = review.sam_point_mask(object(), image, view, [(300, 150, True), (700.6, 160, False)])
    assert seen["prompt"] == (
        "<0f>1<|point;x=300;y=50;w=1000;h=100|>-<|point;x=700;y=60;w=1000;h=100|>"
    )
    assert seen["shape"][:2] == (100, 1000)
    assert pm.row == 1 and (pm.start_cm, pm.end_cm) == (20.0, 50.0)
    assert pm.confidence == 0.95 and pm.overlay.startswith(b"\x89PNG")


def test_sam_point_mask_wants_a_positive_first_point_in_one_row(monkeypatch):
    view = TrayView(width=1000, height=200, px_per_cm=10, rows=[(0, 100), (100, 200)], markers=[])
    image = np.zeros((200, 1000, 3), np.uint8)
    monkeypatch.setattr(review, "row_masks", lambda *a: [])
    with pytest.raises(ReviewError, match="first point"):
        review.sam_point_mask(object(), image, view, [(10, 10, False)])
    with pytest.raises(ReviewError, match="same row"):
        review.sam_point_mask(object(), image, view, [(10, 10, True), (10, 150, False)])
    with pytest.raises(ReviewError, match="no piece"):
        review.sam_point_mask(object(), image, view, [(10, 10, True)])
