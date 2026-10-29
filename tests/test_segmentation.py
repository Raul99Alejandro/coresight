import numpy as np
import pytest

from coresight.segmentation import (
    RowPieces,
    fracture_cuts,
    masks_to_intervals,
    split_intervals,
)

PX_PER_CM = 10.0
H, W = 60, 1000


def mask(left, right, top=10, bottom=50):
    m = np.ones((bottom - top, right - left), dtype=bool)
    return {"id": 0, "bounds": (left, top, right, bottom), "confidence": 0.9, "mask": m}


def grey_crop(value=150):
    return np.full((H, W, 3), value, np.uint8)


def test_masks_become_sorted_intervals():
    intervals, union = masks_to_intervals([mask(500, 900), mask(0, 400)], grey_crop(), PX_PER_CM)
    assert intervals == [(0, 400), (500, 900)]
    assert union[30, 450] == np.False_ and union[30, 100]


def test_overlapping_neighbours_split_in_the_middle():
    intervals, _ = masks_to_intervals([mask(0, 420), mask(380, 900)], grey_crop(), PX_PER_CM)
    assert intervals == [(0, 400), (400, 900)]


def test_object_inside_a_larger_one_is_dropped():
    chip = mask(300, 400, top=0, bottom=15)
    intervals, _ = masks_to_intervals([mask(0, 900), chip], grey_crop(), PX_PER_CM)
    assert intervals == [(0, 900)]


def test_specks_and_depth_markers_are_dropped():
    crop = grey_crop()
    crop[:, 600:700] = (200, 0, 200)  # magenta foam block (BGR)
    masks = [mask(0, 500), mask(520, 523), mask(600, 700)]
    intervals, _ = masks_to_intervals(masks, crop, PX_PER_CM)
    assert intervals == [(0, 500)]


def test_thin_dark_line_across_the_core_is_a_fracture():
    crop = grey_crop(160)
    crop[10:50, 497:501] = 60  # 4 px (0.4 cm) dark line crossing the core
    _, union = masks_to_intervals([mask(0, 900)], crop, PX_PER_CM)
    cuts = fracture_cuts(crop, union, (0, 900), PX_PER_CM)
    assert len(cuts) == 1 and abs(cuts[0] - 499) <= 2


def test_dark_band_wider_than_a_fracture_or_partial_is_ignored():
    crop = grey_crop(160)
    crop[10:50, 300:340] = 60  # 4 cm dark band: a dark mineral, not a fracture
    crop[10:20, 600:603] = 60  # short line on the top edge only
    _, union = masks_to_intervals([mask(0, 900)], crop, PX_PER_CM)
    assert fracture_cuts(crop, union, (0, 900), PX_PER_CM) == []


def test_split_intervals_and_pieces_in_cm():
    intervals = split_intervals([(0, 400), (400, 900)], [150, 402], PX_PER_CM)
    assert intervals == [(0, 150), (150, 400), (400, 900)]
    pieces = RowPieces("sam+fill+profile", PX_PER_CM, intervals).pieces
    assert [(p.start_cm, p.end_cm) for p in pieces] == [(0, 15), (15, 40), (40, 90)]


def test_unknown_method_is_rejected():
    from coresight.segmentation import segment_row

    with pytest.raises(ValueError):
        segment_row(grey_crop(), [], PX_PER_CM, method="magic")


def test_row_masks_decodes_once_and_reuses_the_cache(tmp_path):
    from pathlib import Path

    from coresight.segmentation import row_masks

    record = (Path(__file__).parent / "data" / "sam_one_record.txt").read_text(encoding="utf-8")

    class FakeClient:
        calls = 0

        def segment_row_raw(self, png, prompt):
            FakeClient.calls += 1
            return record

    crop = grey_crop()
    first = row_masks(FakeClient(), crop, cache_dir=tmp_path)
    again = row_masks(FakeClient(), crop, cache_dir=tmp_path)
    assert FakeClient.calls == 1
    assert len(first) == len(again) == 1
    assert again[0]["bounds"] == tuple(first[0]["bounds"])
    assert (again[0]["mask"] == first[0]["mask"]).all()


def test_fill_adds_core_sam_missed_but_not_empty_tray():
    from coresight.segmentation import fill_gaps

    crop = np.zeros((H, W, 3), np.uint8)
    crop[:] = (120, 180, 215)  # tray wood everywhere
    crop[15:45, 100:700] = (90, 90, 90)  # grey core SAM did not return
    intervals, filled = fill_gaps(crop, [], PX_PER_CM)
    assert len(intervals) == 1
    a, b = intervals[0]
    assert abs(a - 100) <= 3 and abs(b - 700) <= 3
    assert filled[30, 400] and not filled[30, 800]


def test_fill_leaves_stretches_sam_covered():
    from coresight.segmentation import fill_gaps

    crop = np.zeros((H, W, 3), np.uint8)
    crop[:] = (120, 180, 215)
    crop[15:45, 100:700] = (90, 90, 90)
    intervals, _ = fill_gaps(crop, [(100.0, 700.0)], PX_PER_CM)
    assert intervals == [(100.0, 700.0)]


def core_with_line(value=150):
    """Grey core with a long red orientation line along it (BGR)."""
    crop = grey_crop(value)
    crop[44:47, :] = (40, 40, 200)
    return crop


def draw_x(crop, x, y=25, size=10):
    import cv2

    cv2.line(crop, (x - size // 2, y - size // 2), (x + size // 2, y + size // 2), (30, 30, 220), 2)
    cv2.line(crop, (x - size // 2, y + size // 2), (x + size // 2, y - size // 2), (30, 30, 220), 2)


def test_red_x_beside_a_break_makes_it_mechanical():
    from coresight.segmentation import classify_breaks, mechanical_marks

    crop = core_with_line()
    draw_x(crop, 385)
    draw_x(crop, 415)
    assert len(mechanical_marks(crop, PX_PER_CM)) == 2
    kinds = classify_breaks(crop, [(0, 400), (400, 700), (705, 990)], [], PX_PER_CM)
    assert kinds[0] == "mechanical"
    assert kinds[1] != "mechanical"
    assert kinds[2] == "uncertain"  # the row end


def test_orientation_line_alone_is_not_a_mark():
    from coresight.segmentation import mechanical_marks

    crop = core_with_line()
    crop[44:47, 300:320] = 150  # a dashed stretch of the line
    assert mechanical_marks(crop, PX_PER_CM) == []


def test_red_on_reddish_rock_is_not_a_mark():
    from coresight.segmentation import mechanical_marks

    crop = np.full((H, W, 3), (60, 80, 150), np.uint8)  # brown, saturated rock
    draw_x(crop, 400)
    assert mechanical_marks(crop, PX_PER_CM) == []


def test_tight_break_with_continuous_line_is_possible_mechanical():
    from coresight.segmentation import classify_breaks

    crop = core_with_line()
    kinds = classify_breaks(crop, [(0, 400), (401, 990)], [], PX_PER_CM)
    assert kinds == ["possible_mechanical", "uncertain"]


def test_not_core_spans_are_taken_out_of_the_pieces():
    from coresight.segmentation import exclude_spans

    intervals = [(0, 400), (500, 900)]
    # a run block at 600-650 cuts the second piece; a card over 380-520 trims both
    out = exclude_spans(intervals, [(600, 650), (380, 520)], PX_PER_CM)
    assert out == [(0, 380), (520, 600), (650, 900)]
    # what is left of a piece shorter than a speck is dropped
    assert exclude_spans([(0, 100)], [(3, 100)], PX_PER_CM) == []


def test_spark_methods_measure_like_their_twins_without_the_not_core():
    from coresight.segmentation import SPARK_METHODS, segment_row

    assert SPARK_METHODS[0] == "spark+sam"
    masks = [mask(0, 400), mask(420, 900)]
    plain = segment_row(grey_crop(), masks, PX_PER_CM, "sam")
    spark = segment_row(grey_crop(), masks, PX_PER_CM, "spark+sam", not_core=[(700, 760)])
    assert plain.intervals_px == [(0, 400), (420, 900)]
    assert spark.intervals_px == [(0, 400), (420, 700), (760, 900)]
    assert spark.method == "spark+sam"


def test_spark_sees_a_long_row_in_overlapping_tiles():
    from coresight.segmentation import tiles

    assert tiles(2500, 278) == [(0, 718), (531, 1343), (1156, 1968), (1781, 2500)]
    assert tiles(600, 278) == [(0, 600)]


def test_tile_boxes_cut_by_an_edge_are_joined_and_twins_dropped():
    from coresight.segmentation import merge_tile_boxes

    boxes = [
        ("core", (0, 5, 200, 50), False, False),
        ("core", (500, 5, 718, 50), False, True),  # cut by the right edge of tile 1
        ("core", (531, 8, 760, 52), True, False),  # its other half, cut by tile 2's left edge
        ("card", (900, 0, 1000, 60), False, False),
        ("card", (905, 0, 1002, 60), False, False),  # the same card seen by two tiles
        ("core", (1003, 5, 1100, 50), False, False),
        ("core", (1095, 5, 1300, 50), False, False),  # touching pieces stay two
        ("core", (1156, 5, 1290, 50), True, False),  # a tile's cut copy of the last one
    ]
    assert merge_tile_boxes(boxes) == [
        ("core", (0, 5, 200, 50)),
        ("core", (500, 5, 760, 52)),
        ("card", (900, 0, 1000, 60)),
        ("core", (1003, 5, 1100, 50)),
        ("core", (1095, 5, 1300, 50)),
    ]


def test_located_masks_prompts_sam_with_spark_boxes_sixteen_at_a_time(tmp_path, monkeypatch):
    from coresight import segmentation
    from coresight.schemas import LocatedObject, RowLocation

    def obj(kind, x1, x2):
        return LocatedObject(kind=kind, x_min=x1, y_min=100, x_max=x2, y_max=900)

    pieces = [obj("core", 50 * i, 50 * i + 40) for i in range(18)]
    location = RowLocation(objects=[*pieces, obj("run_block", 950, 990), obj("card", 905, 940)])
    prompts = []

    class FakeClient:
        def locate_row(self, png):
            return location

        def segment_row_raw(self, png, prompt):
            prompts.append(prompt)
            return prompt

    def fake_masks(text):  # one mask per box token, under its object id
        ids = [int(part.split("<")[0]) for part in text.removeprefix("<0f>").split(",")]
        return [mask(10 * i, 10 * i + 5) | {"id": i} for i in ids]

    monkeypatch.setattr(segmentation, "sam_masks", fake_masks)
    crop = np.full((60, 150, 3), 150, np.uint8)  # one tile
    masks, not_core = segmentation.located_masks(FakeClient(), crop, cache_dir=tmp_path)
    assert len(prompts) == 2  # 18 core boxes: 16, then 2
    assert prompts[0].count("<|box;") == 16 and prompts[1].count("<|box;") == 2
    assert "w=150;h=60" in prompts[0]
    assert prompts[1].startswith("<0f>16<|box;x1=120;")  # 800/1000 of 150 px
    assert [m["id"] for m in masks] == list(range(18))
    assert not_core == [(135.0, 142.0), (142.0, 149.0)]


def test_a_box_prompt_mask_is_kept_to_its_box():
    from coresight.segmentation import clip_to_box

    spill = mask(100, 600)  # SAM ran on into the next piece
    kept = clip_to_box(spill, (100, 10, 299, 50))  # box 200 px wide: 10 px of slack
    cols = np.where(kept["mask"].any(axis=0))[0]
    assert (cols[0] + 100, cols[-1] + 100) == (100, 309)
    assert kept["bounds"] == spill["bounds"] and spill["mask"].all()


def test_fallback_turns_to_spark_only_for_a_row_stone_left_empty(monkeypatch):
    from coresight import pipeline

    class FakeTray:
        px_per_cm = PX_PER_CM

        def row_crops(self, image):
            return [grey_crop(), grey_crop()]

    stone = iter([[mask(0, 400)], []])  # row 1 has masks, row 2 has none
    located = []
    monkeypatch.setattr(pipeline, "row_masks", lambda client, crop: next(stone))
    monkeypatch.setattr(
        pipeline, "located_masks", lambda client, crop: located.append(1) or ([mask(0, 900)], [])
    )
    rows, _ = pipeline.segment(grey_crop(), FakeTray(), object(), "fallback+sam")
    assert located == [1]  # only the empty row asked Spark
    assert [r.intervals_px for r in rows] == [[(0, 400)], [(0, 900)]]


def test_an_empty_stretch_spark_boxes_has_no_pieces_and_counts_as_not_recovered(tmp_path,
                                                                                monkeypatch):
    """Point 5: the bare wood of an empty row is "empty", taken out like a run block, so
    geometry.py logs it as core that was not recovered (TCR and RQD drop)."""
    from coresight import segmentation
    from coresight.runs import log_segment, run_segments
    from coresight.schemas import Interval, LocatedObject, RowLocation

    def obj(kind, x1, x2):
        return LocatedObject(kind=kind, x_min=x1, y_min=100, x_max=x2, y_max=900)

    location = RowLocation(objects=[obj("core", 0, 499), obj("empty", 500, 999)])

    class FakeClient:
        def locate_row(self, png):
            return location

        def segment_row_raw(self, png, prompt):
            return prompt

    monkeypatch.setattr(segmentation, "sam_masks", lambda text: [mask(0, 150) | {"id": 0}])
    crop = np.full((60, 150, 3), 150, np.uint8)  # 150 px, 10 px per cm: a 15 cm row
    masks, not_core = segmentation.located_masks(FakeClient(), crop, cache_dir=tmp_path)
    assert not_core == [(75.0, 150.0)]  # the empty half, as wide as Spark boxed it
    row = segmentation.segment_row(crop, masks, 10.0, "spark+sam", not_core)
    assert row.intervals_px == [(0, 75.0)]  # SAM's mask ran on into the wood: cut there
    (laid,) = run_segments([row], [], 1)
    log = log_segment(laid, Interval(from_m=0, to_m=0.15))
    assert log.tcr_pct == pytest.approx(50.0)  # 7.5 of 15 cm recovered
    assert log.rqd_pct == 0.0  # the one piece, 7.5 cm, is shorter than 10 cm


def test_rows_are_read_side_by_side_and_spark_boxes_only_the_rows_sam_left_empty(monkeypatch):
    """Point 5: a new tray took 142 s with its rows one after another. SAM reads every row
    at once; the rows "stone" found nothing in go to Muse Spark at once, and the page
    hears how many before Spark starts."""
    import threading

    from coresight import pipeline

    crops = [np.full((4, 4, 3), v, np.uint8) for v in (0, 1, 2)]
    together = threading.Barrier(2, timeout=5)  # passes only if two rows box at once

    def stone(client, crop):
        return [] if crop[0, 0, 0] > 0 else [mask(0, 4)]

    def spark(client, crop):
        together.wait()
        return [mask(1, 3)], [(3.0, 4.0)]

    monkeypatch.setattr(pipeline, "row_masks", stone)
    monkeypatch.setattr(pipeline, "located_masks", spark)
    heard = []
    out = pipeline.rows_prompts(None, crops, "fallback+sam+fill+profile", heard.append)
    assert heard == [[1, 2]]
    assert [o[2] for o in out] == [False, True, True]
    assert out[1][1] == [(3.0, 4.0)] and out[0][1] == []
