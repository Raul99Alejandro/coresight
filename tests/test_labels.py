from pathlib import Path

import pytest

from coresight.schemas import BoxLabel

LABELS_DIR = Path(__file__).resolve().parents[1] / "data" / "labels"
LABEL_FILES = sorted(LABELS_DIR.glob("*.json"))


def test_there_are_at_least_ten_labels():
    assert len(LABEL_FILES) >= 10


@pytest.mark.parametrize("path", LABEL_FILES, ids=lambda p: p.name)
def test_label_is_valid(path):
    label = BoxLabel.model_validate_json(path.read_text(encoding="utf-8"))
    assert path.stem == f"{label.hole_id}_box{label.box_number:02d}"
    for prev, nxt in zip(label.runs, label.runs[1:], strict=False):
        assert nxt.from_m == pytest.approx(prev.to_m), "runs must be consecutive"
    for run in label.runs:
        # RQD only counts recovered core, so it can never exceed recovery
        assert run.rqd_pct <= run.tcr_pct


def test_natural_fractures_may_be_unlogged():
    run = {"from_m": 0, "to_m": 1, "rqd_pct": 50, "tcr_pct": 90}
    label = BoxLabel(hole_id="H", box_number=1, image="x.jpg", runs=[run])
    assert label.runs[0].natural_fractures is None
