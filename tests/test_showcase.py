"""The home page and the 60-second tour (point G): real boxes, picked by the server."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from test_api import client
from test_review import PIECES, make_run

from coresight import api, review
from coresight.api import create_app
from coresight.review import ReviewStore
from coresight.schemas import BoxReview, Handoffs, HoleFinding, HoleReport, TrayView

NEVADA3 = api.SAMPLES["nevada-u12g-box3"]


def box(i, hole_id="U12G-GF-GT2", n=3, status="ready", source=None, handoffs=None, minutes=0):
    return BoxReview(
        id=f"b{i}", hole_id=hole_id, box_number=n, status=status,
        source=source or f"{NEVADA3.title}. {NEVADA3.credit}",
        created_at=datetime(2026, 10, 30, tzinfo=UTC) + timedelta(minutes=minutes),
        tray=TrayView(width=1000, height=500, px_per_cm=10, rows=[(0, 100)], markers=[]),
        runs=[make_run(PIECES, 5.79 + n, 6.79 + n)], handoffs=handoffs,
    )  # fmt: skip


def done(finding=True) -> Handoffs:
    report = HoleReport(model="muse-spark-1.3", status="ready")
    if finding:
        report.finding = HoleFinding(action="warn_geotech", title="Warn geotechnics",
                                     body="RQD falls.", action_reason="RQD falls.")  # fmt: skip
    return Handoffs(status="done", hole=report)


def test_showcase_is_empty_on_a_new_server(tmp_path):
    assert client(tmp_path).get("/api/showcase").json() == {
        "box": None, "agents_box": None, "hole_id": None}  # fmt: skip


def test_showcase_picks_the_dramatic_sample_the_agents_and_the_hole(tmp_path):
    store = ReviewStore(tmp_path)
    store.save(box(1, minutes=1))  # Nevada box 3, under review
    store.save(box(2, status="approved", handoffs=done(False), minutes=2))
    store.save(box(3, status="approved", handoffs=done(True), minutes=3))
    store.save(box(4, status="approved", handoffs=Handoffs(status="working"), minutes=4))
    store.save(box(5, hole_id="DDH-9", n=1, status="ready", source="upload", minutes=5))
    onkalo = api.SAMPLES["onkalo-box5"].title
    store.save(box(6, hole_id="ONK", n=5, status="approved", source=onkalo, minutes=6))
    c = TestClient(create_app(store=store, background=False))
    s = c.get("/api/showcase").json()
    assert s["box"] == "b4"  # newest Nevada box 3 with pieces, any status but failed
    assert s["agents_box"] == "b3"  # finished, with a hole finding
    assert s["hole_id"] == "U12G-GF-GT2"  # the hole of the agents box


def test_an_upload_is_never_shown_on_the_home_page(tmp_path):
    store = ReviewStore(tmp_path)
    store.save(box(1, source="upload", status="approved", handoffs=done()))
    s = TestClient(create_app(store=store, background=False)).get("/api/showcase").json()
    assert s == {"box": None, "agents_box": None, "hole_id": None}


def test_the_tour_shows_a_screenshot_being_refused_live(tmp_path, monkeypatch):
    calls = []

    def analyzer(photo, job, report):
        calls.append(job)
        return review.analyze(photo, job.box_length_cm, job.runs, job.first_starts_in_box,
                              None, None, report=report, n_rows=job.n_rows)  # fmt: skip

    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_VISITOR", "0")  # not an upload: no allowance
    b = client(tmp_path, analyzer).post("/api/tour/not-a-box").json()
    assert b["status"] == "failed" and "no scale" in b["error"]
    assert b["gate"]["ok"] is False and "screenshot" in b["source"]
    assert len(calls) == 1
