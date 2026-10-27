from datetime import UTC, datetime

import cv2
import numpy as np
import pytest

from coresight import review
from coresight.review import ReviewError, ReviewStore
from coresight.schemas import (
    BoxReview,
    GeologyDescription,
    Interval,
    IntervalResult,
    ReviewPiece,
    RunReview,
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
