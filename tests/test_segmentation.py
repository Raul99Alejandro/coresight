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
