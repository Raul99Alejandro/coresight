import json
from pathlib import Path

import pytest

from coresight.labeling import PieceSheet, label_from_sheet, log_sheet, px_per_cm

LABELS_DIR = Path(__file__).resolve().parents[1] / "data" / "labels"
SHEET_FILES = sorted((LABELS_DIR / "pieces").glob("*.json"))


def sheet(rows, runs, marks):
    return PieceSheet(
        hole_id="H",
        box_number=1,
        image="x.jpg",
        runs=[{"from_m": a, "to_m": b} for a, b in runs],
        rows=[
            {"y1": 0, "y2": 10, "pieces": [{"x1": a, "x2": b, "after": k} for a, b, k in row]}
            for row in rows
        ],
        meter_marks=[{"row": r, "x": x, "depth_m": d} for r, x, d in marks],
    )


def test_scale_follows_metre_marks_across_rows():
    # 10 px/cm: the 1 m between the marks is 600 px in row 0 and 400 px in row 1
    s = sheet(
        [[(0, 700, "uncertain")], [(0, 500, "run_end")]],
        [(0.0, 1.2)],
        [(0, 100, 1.0), (1, 400, 2.0)],
    )
    assert px_per_cm(s) == pytest.approx(10.0)


def test_runs_split_at_run_end_and_rqd_comes_from_geometry():
    # 10 px/cm; run 1: 50 + 5 + 45 cm with a mechanical break, run 2: 80 of 100 cm
    s = sheet(
        [
            [(0, 500, "natural"), (500, 550, "mechanical"), (550, 1000, "run_end")],
            [(0, 800, "run_end")],
        ],
        [(0.0, 1.0), (1.0, 2.0)],
        [(0, 0, 0.0), (0, 1000, 1.0)],
    )
    first, second = log_sheet(s)
    assert first.rqd_pct == pytest.approx(100.0)
    assert first.natural_fractures == 1
    assert first.mechanical_breaks == 1
    assert second.tcr_pct == pytest.approx(80.0)
    assert second.rqd_pct == pytest.approx(80.0)


def test_box_must_end_with_a_run_end():
    s = sheet([[(0, 1000, "natural")]], [(0.0, 1.0)], [(0, 0, 0.0), (0, 1000, 1.0)])
    with pytest.raises(ValueError, match="last piece"):
        log_sheet(s)


def test_run_count_must_match():
    s = sheet([[(0, 1000, "run_end")]], [(0.0, 0.5), (0.5, 1.0)], [(0, 0, 0.0), (0, 1000, 1.0)])
    with pytest.raises(ValueError, match="runs"):
        log_sheet(s)


@pytest.mark.parametrize("path", SHEET_FILES, ids=lambda p: p.name)
def test_committed_labels_match_their_piece_sheets(path):
    s = PieceSheet.model_validate_json(path.read_text(encoding="utf-8"))
    label = label_from_sheet(s)
    saved = json.loads((LABELS_DIR / f"{path.stem}.json").read_text(encoding="utf-8"))
    assert label.model_dump(mode="json") == saved
