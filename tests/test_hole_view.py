"""The hole view (coresight.hole), its API and the agents' read-only hole tool."""

from datetime import UTC, datetime, timedelta

import pytest
from test_api import client, upload
from test_review import make_run

from coresight import hole
from coresight.agents import NoArg, Toolbox, load_prices
from coresight.schemas import Anomaly, AnomalyType, BoxReview, TrayView

T0 = datetime(2026, 10, 30, 12, tzinfo=UTC)


def box(n, runs, hole_id="ONK-1", status="approved", at=0, box_id=None):
    return BoxReview(
        id=box_id or f"b{n}x{at}",
        hole_id=hole_id,
        box_number=n,
        source="test",
        status=status,
        created_at=T0 + timedelta(minutes=at),
        approved_at=T0 + timedelta(minutes=at + 1) if status == "approved" else None,
        tray=TrayView(width=1000, height=500, px_per_cm=10, rows=[(0, 100)], markers=[]),
        runs=runs,
    )


def sound(from_m, to_m):
    """One whole piece per run: RQD 100."""
    return make_run([(0, 0, (to_m - from_m) * 100, "natural")], from_m, to_m)


def broken(from_m, to_m):
    """5 cm pieces: RQD 0."""
    n = round((to_m - from_m) * 20)
    return make_run([(0, i * 5, i * 5 + 5, "natural") for i in range(n)], from_m, to_m)


def test_two_contiguous_boxes_make_one_log():
    view = hole.hole_view([box(6, [sound(2, 4)]), box(5, [sound(0, 2)])], "ONK-1")
    assert (view.from_m, view.to_m) == (0, 4)
    assert [b.box_number for b in view.boxes if b.in_log] == [5, 6]
    assert view.issues == []
    assert [(r.from_m, r.to_m, r.boxes) for r in view.runs] == [(0, 2, [5]), (2, 4, [6])]
    assert len(view.intervals) == 4 and all(i.rqd_pct == 100 for i in view.intervals)
    assert view.intervals[0].lithology == "granite gneiss"


def test_box_run_numbers_match_the_box_log():
    run = make_run([(0, 0, 40, "natural"), (0, 40, 48, "natural"), (0, 50, 95, "natural")])
    view = hole.hole_view([box(1, [run])], "ONK-1")
    (r,) = view.runs
    assert (r.rqd_pct, r.tcr_pct, r.natural_fractures) == (
        run.log.rqd_pct,
        run.log.tcr_pct,
        run.log.natural_fractures,
    )


def test_only_approved_boxes_enter_and_the_latest_approval_wins():
    old = box(1, [broken(0, 1)], at=0)
    new = box(1, [sound(0, 1)], at=10)
    pending = box(2, [sound(1, 2)], status="ready", at=20)
    other = box(1, [sound(0, 1)], hole_id="OTHER")
    view = hole.hole_view([old, new, pending, other], "ONK-1")
    assert [(b.id, b.in_log) for b in view.boxes] == [(new.id, True), (pending.id, False)]
    assert [r.rqd_pct for r in view.runs] == [100]


def test_gap_and_weak_zone_are_reported():
    boxes = [box(1, [sound(0, 1), broken(1, 2), broken(2, 3)]), box(3, [sound(5, 6)])]
    view = hole.hole_view(boxes, "ONK-1")
    assert [(i.kind, i.from_m, i.to_m, i.box_before, i.box_after) for i in view.issues] == [
        ("gap", 3, 5, 1, 3)
    ]
    (z,) = view.zones
    assert (z.from_m, z.to_m, z.rqd_pct, z.rock_quality) == (1, 3, 0, "very poor")
    assert [(i.from_m, i.to_m) for i in view.intervals] == [(0, 1), (1, 2), (2, 3), (5, 6)]


def test_run_split_between_boxes_is_joined():
    a, b = sound(0.5, 1.0), sound(1.0, 1.5)
    a.log = a.log.model_copy(update={"complete": False})
    b.log = b.log.model_copy(update={"complete": False})
    view = hole.hole_view([box(1, [sound(0, 0.5), a]), box(2, [b])], "ONK-1")
    assert [(r.from_m, r.to_m, r.boxes) for r in view.runs] == [(0, 0.5, [1]), (0.5, 1.5, [1, 2])]


def test_anomalies_of_the_runs_touched_are_carried():
    run = broken(0, 1)
    run.description.anomalies.append(
        Anomaly(type=AnomalyType.INTENSE_FRACTURING, explanation="20 fractures per metre")
    )
    view = hole.hole_view([box(1, [run])], "ONK-1")
    assert view.intervals[0].anomalies == [AnomalyType.INTENSE_FRACTURING]


def test_trace_is_an_example_and_says_so():
    view = hole.hole_view([box(1, [sound(0, 1)])], "ONK-1")
    assert view.trace.surveyed is False
    assert "Example trace" in view.trace.note and "no downhole survey" in view.trace.note


def test_hole_without_approved_boxes_has_no_log():
    view = hole.hole_view([box(1, [sound(0, 1)], status="ready")], "ONK-1")
    assert view.runs == [] and view.from_m is None and len(view.boxes) == 1


def test_summaries_list_holes_with_an_approved_box():
    boxes = [box(1, [sound(0, 1)]), box(2, [sound(1, 2)], status="ready"),
             box(1, [sound(0, 1)], hole_id="DRAFT", status="ready")]  # fmt: skip
    assert hole.hole_summaries(boxes) == [
        {"hole_id": "ONK-1", "boxes_in_log": [1], "boxes_pending": [2], "from_m": 0, "to_m": 1}
    ]


def test_agent_tool_reads_the_hole_by_depth():
    earlier = box(1, [sound(0, 1), broken(1, 2)])
    current = box(2, [broken(2, 3), sound(3, 4)])
    t = Toolbox(current, [earlier], load_prices())
    assert "hole_log" in t.tools()
    out = t.tools()["hole_log"].run(NoArg())
    assert out["boxes_in_log"] == [1, 2]
    assert out["weak_zones"][0]["from_m"] == 1 and out["weak_zones"][0]["to_m"] == 3
    assert [r["rqd_pct"] for r in out["intervals_1_m"]] == [100, 0, 0, 100]
    assert out["gaps_and_overlaps"] == []
    assert "geometry" in out["source"]


def test_api_lists_and_reads_holes(tmp_path):
    c = client(tmp_path)
    bid = upload(c, runs="10-11, 11-12.5").json()["id"]
    assert c.get("/api/holes").json() == []
    assert c.get("/api/holes/DDH-1").json()["runs"] == []
    c.post(f"/api/boxes/{bid}/approve")
    (summary,) = c.get("/api/holes").json()
    assert summary["hole_id"] == "DDH-1" and summary["boxes_in_log"] == [3]
    view = c.get("/api/holes/DDH-1").json()
    assert [(r["from_m"], r["to_m"]) for r in view["runs"]] == [(10, 11), (11, 12.5)]
    assert view["trace"]["surveyed"] is False
    assert c.get("/api/holes/NOPE").status_code == 404


@pytest.mark.parametrize("name", ["nevada-u12g-box3"])
def test_second_nevada_box_is_a_sample_that_starts_mid_run(name):
    from coresight.api import SAMPLES

    s = SAMPLES[name]
    assert s.first_starts_in_box is False and "public domain" in s.credit
