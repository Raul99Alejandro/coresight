"""Points 1 and 2 of the third analysis: a browser sees only its boxes; samples are read-only.

Two TestClients on one app are two browsers: each keeps its own cookie jar.
"""

from fastapi.testclient import TestClient
from test_api import fake_analyzer, fake_handoffs, fake_sample_photo, upload
from test_showcase import box, done

from coresight import api
from coresight.api import VISITOR_COOKIE, create_app, pin_legacy_samples, read_visitor, sign_visitor
from coresight.review import ReviewStore


def two_browsers(store, analyzer=fake_analyzer):
    app = create_app(store=store, analyzer=analyzer, handoff_runner=fake_handoffs,
                     transcriber=lambda wav: ("", 0), background=False)  # fmt: skip
    return TestClient(app), TestClient(app)


BEFORE = -7 * 24 * 60  # minutes: a week before the boxes made in the test


def legacy_samples(store) -> None:
    """What production had before owners: sample boxes nobody owns, one approved with agents."""
    store.save(box(1, n=3, minutes=BEFORE + 4))  # Nevada box 3 under review, newest (home, tour)
    store.save(box(2, n=1, status="approved", minutes=BEFORE + 2))  # box 1 of the hole
    store.save(box(3, n=3, status="approved", handoffs=done(True), minutes=BEFORE + 3))  # agents


def test_an_upload_is_seen_only_by_the_browser_that_sent_it(tmp_path):
    a, b = two_browsers(ReviewStore(tmp_path))
    mine = upload(a).json()
    assert [x["id"] for x in a.get("/api/boxes").json()] == [mine["id"]]
    assert b.get("/api/boxes").json() == []
    files = ["/tray.jpg", "/masks/0.png", "/runs/0/crop.jpg", "/log.csv", "/corrections.csv"]
    for path in ["", *files]:
        assert a.get(f"/api/boxes/{mine['id']}{path}").status_code == 200, path
        r = b.get(f"/api/boxes/{mine['id']}{path}")
        assert r.status_code == 404, path  # not 403: nothing says the box exists
        assert r.json()["detail"] == b.get("/api/boxes/000000000000").json()["detail"]


def test_a_stranger_cannot_change_or_approve_an_upload(tmp_path):
    a, b = two_browsers(ReviewStore(tmp_path))
    box_id = upload(a).json()["id"]
    attempts = [
        b.post(f"/api/boxes/{box_id}/runs/0/breaks/0", json={"kind": "mechanical"}),
        b.delete(f"/api/boxes/{box_id}/runs/0/pieces/0"),
        b.post(f"/api/boxes/{box_id}/runs/0/pieces/0/split", json={"at_cm": 5}),
        b.put(f"/api/boxes/{box_id}/runs/0/description", json={"field": "lithology", "value": "x"}),
        b.post(f"/api/boxes/{box_id}/runs/0/sam-point", json={"points": [{"x": 1, "y": 1}]}),
        b.post(f"/api/boxes/{box_id}/approve"),
        b.post(f"/api/boxes/{box_id}/handoffs"),
        b.post(f"/api/boxes/{box_id}/drafts/safety/approve"),
    ]
    assert [r.status_code for r in attempts] == [404] * len(attempts)
    assert a.get(f"/api/boxes/{box_id}").json()["status"] == "ready"
    assert a.post(f"/api/boxes/{box_id}/approve").json()["status"] == "approved"


def test_an_approved_upload_and_its_hole_stay_private(tmp_path):
    a, b = two_browsers(ReviewStore(tmp_path))
    box_id = upload(a).json()["id"]
    a.post(f"/api/boxes/{box_id}/approve")
    assert [h["hole_id"] for h in a.get("/api/holes").json()] == ["DDH-1"]
    assert b.get("/api/holes").json() == []
    assert b.get("/api/holes/DDH-1").status_code == 404
    assert b.get("/api/showcase").json() == {"box": None, "agents_box": None, "hole_id": None}


def test_a_stranger_does_not_learn_from_my_corrections(tmp_path):
    jobs = []

    def analyzer(photo, job, report):
        jobs.append(job)
        return fake_analyzer(photo, job, report)

    a, b = two_browsers(ReviewStore(tmp_path), analyzer)
    box_id = upload(a).json()["id"]
    a.put(f"/api/boxes/{box_id}/runs/0/description",
          json={"field": "lithology", "value": "chloritic gneiss"})  # fmt: skip
    a.post(f"/api/boxes/{box_id}/approve")
    upload(b)
    upload(a)
    assert "examples" not in str(jobs[1].context)  # b: nothing of a's
    assert "chloritic gneiss" in str(jobs[2].context)  # a: their own correction


def test_the_cookie_is_signed_httponly_and_secure_behind_https(tmp_path):
    a, _ = two_browsers(ReviewStore(tmp_path))
    r = a.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{VISITOR_COOKIE}=") and "HttpOnly" in cookie
    assert "SameSite=lax" in cookie and "Secure" in cookie
    plain = TestClient(a.app)  # http: the browser keeps it without Secure
    assert "Secure" not in plain.get("/api/health").headers["set-cookie"]
    assert "set-cookie" not in plain.get("/api/health").headers  # signed already: kept as is


def test_a_forged_cookie_owns_nothing(tmp_path):
    a, b = two_browsers(ReviewStore(tmp_path))
    box_id = upload(a).json()["id"]
    visitor = read_visitor(b"x", sign_visitor(b"x", "abc"))
    assert visitor == "abc" and read_visitor(b"y", sign_visitor(b"x", "abc")) is None
    owner = a.get(f"/api/boxes/{box_id}").json()["owner"]
    b.cookies.set(VISITOR_COOKIE, f"{owner}.{'0' * 32}")  # a's id, without the server's key
    assert b.get(f"/api/boxes/{box_id}").status_code == 404
    assert read_visitor(b"x", None) is None and read_visitor(b"x", "../..") is None


def test_boxes_from_before_owners_are_hidden_unless_pinned(tmp_path):
    store = ReviewStore(tmp_path)
    store.save(box(9, hole_id="JUDGE-commons_nts_1981", n=1, source="upload"))
    legacy_samples(store)
    a, _ = two_browsers(store)
    assert a.get("/api/boxes/b9").status_code == 404  # a judge's upload: nobody sees it now
    assert a.get("/api/boxes").json() == []
    assert {b.id for b in store.all() if b.pinned} == {"b1", "b2", "b3"}
    assert pin_legacy_samples(store) == []  # once


def test_the_samples_everybody_sees_are_read_only(tmp_path):
    store = ReviewStore(tmp_path)
    legacy_samples(store)
    a, b = two_browsers(store)
    for c in (a, b):
        assert c.get("/api/boxes/b1").status_code == 200
        assert c.get("/api/boxes/b1/tray.jpg").status_code == 404  # no image in this test
    attempts = [
        a.post("/api/boxes/b1/runs/0/breaks/0", json={"kind": "mechanical"}),
        a.delete("/api/boxes/b1/runs/0/pieces/0"),
        a.put("/api/boxes/b1/runs/0/description", json={"field": "lithology", "value": "x"}),
        a.post("/api/boxes/b1/runs/0/sam-point", json={"points": [{"x": 1, "y": 1}]}),
        a.post("/api/boxes/b1/approve"),
        a.post("/api/boxes/b3/handoffs"),
        a.post("/api/boxes/b3/drafts/safety/approve"),
    ]
    assert [r.status_code for r in attempts] == [403] * len(attempts)
    assert "Try a sample box" in attempts[0].json()["detail"]
    assert store.get("b1") == box(1, n=3, minutes=BEFORE + 4).model_copy(update={"pinned": True})


def test_approving_my_sample_copy_changes_nothing_for_the_others(tmp_path, monkeypatch):
    fake_sample_photo(tmp_path, monkeypatch, "nevada-u12g-box3")
    store = ReviewStore(tmp_path / "boxes")
    legacy_samples(store)
    a, b = two_browsers(store)
    before = b.get("/api/showcase").json(), b.get("/api/holes/U12G-GF-GT2").json()
    assert before[0] == {"box": "b1", "agents_box": "b3", "hole_id": "U12G-GF-GT2"}

    copy = a.post("/api/samples/nevada-u12g-box3").json()  # "Try a sample box"
    assert copy["owner"] and not copy["pinned"] and copy["id"] not in {"b1", "b2", "b3"}
    assert b.get(f"/api/boxes/{copy['id']}").status_code == 404
    a.post(f"/api/boxes/{copy['id']}/runs/0/breaks/0", json={"kind": "mechanical"})
    assert a.post(f"/api/boxes/{copy['id']}/approve").json()["handoffs"]["status"] == "done"

    assert (b.get("/api/showcase").json(), b.get("/api/holes/U12G-GF-GT2").json()) == before
    assert a.get("/api/showcase").json() == before[0]  # the tour is the same for a too
    mine = a.get("/api/holes/U12G-GF-GT2").json()  # a's own hole: their approval of box 3
    assert copy["id"] in {x["id"] for x in mine["boxes"] if x["in_log"]}
    assert "b3" not in {x["id"] for x in mine["boxes"] if x["in_log"]}


def test_the_tour_screenshot_belongs_to_the_visitor(tmp_path):
    a, b = two_browsers(ReviewStore(tmp_path), analyzer=lambda *x: (_ for _ in ()).throw(
        api.ReviewError("no scale")))  # fmt: skip
    refused = a.post("/api/tour/not-a-box").json()
    assert a.get(f"/api/boxes/{refused['id']}").status_code == 200
    assert b.get(f"/api/boxes/{refused['id']}").status_code == 404


def test_we_pin_a_sample_with_the_ops_token(tmp_path, monkeypatch):
    fake_sample_photo(tmp_path, monkeypatch, "nevada-u12g-box3")
    a, b = two_browsers(ReviewStore(tmp_path / "boxes"))
    copy = a.post("/api/samples/nevada-u12g-box3").json()["id"]
    assert b.post(f"/api/ops/pin/{copy}").status_code == 404  # no token set: no route
    monkeypatch.setenv("CORESIGHT_OPS_TOKEN", "t0k")
    assert b.post(f"/api/ops/pin/{copy}", headers={"X-Ops-Token": "no"}).status_code == 403
    assert b.post(f"/api/ops/pin/{copy}", headers={"X-Ops-Token": "t0k"}).json()["pinned"]
    assert b.get(f"/api/boxes/{copy}").json()["owner"] is None
    assert b.get("/api/showcase").json()["box"] == copy
    assert a.post(f"/api/boxes/{copy}/approve").status_code == 403
    up = upload(a).json()["id"]
    assert b.post(f"/api/ops/pin/{up}", headers={"X-Ops-Token": "t0k"}).status_code == 400
