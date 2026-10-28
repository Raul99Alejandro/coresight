import struct
from datetime import UTC, datetime

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_review import PIECES, make_run

from coresight.api import create_app, parse_runs
from coresight.review import Analysis, ReviewError, ReviewStore
from coresight.schemas import AgentEvent, AreaDraft, Check, Draft, Handoffs, TrayView


def photo_bytes() -> bytes:
    ok, jpg = cv2.imencode(".jpg", np.full((600, 900, 3), 120, np.uint8))
    return jpg.tobytes()


def fake_analyzer(photo, job, report):
    report.stage("calibration", status="done", progress=1, seconds=0.123)
    report.masks(0, b"png")
    report.crop(0, b"jpg")
    runs = [make_run(PIECES, r.from_m, r.to_m) for r in job.runs]
    tray = TrayView(width=900, height=600, px_per_cm=9, rows=[(0, 120)], markers=[])
    return Analysis(tray=tray, tray_jpg=photo, runs=runs)


def failing_analyzer(photo, job, report):
    raise ReviewError("No core tray with 5 rows was found, so the photo has no scale.")


def broken_analyzer(photo, job, report):
    raise RuntimeError("SAM 503: upstream unavailable")


def fake_handoffs(box, history, save):
    """The agents' result without the Model API: one verified safety draft."""
    h = Handoffs(status="done", orchestrator_model="muse-wonder-1.0")
    h.drafts.append(AreaDraft(area="safety", model="muse-spark-1.3", verified=True,
                              status="ready", draft=Draft(title="Ground alert", body="Fair."),
                              checks=[Check(name="figures", ok=True)]))  # fmt: skip
    h.log.append(AgentEvent(at=datetime.now(UTC), actor="orchestrator", kind="route",
                            text=f"history {len(history)}"))  # fmt: skip
    save(h)


def client(tmp_path, analyzer=fake_analyzer, transcriber=None, handoffs=fake_handoffs):
    app = create_app(
        store=ReviewStore(tmp_path),
        analyzer=analyzer,
        transcriber=transcriber or (lambda wav: ("alteración clorítica débil", 2100)),
        handoff_runner=handoffs,
        background=False,
    )
    return TestClient(app)


def upload(c: TestClient, runs="10-11, 11-12.5", data=None):
    return c.post(
        "/api/boxes",
        files={"photo": ("box.jpg", data or photo_bytes(), "image/jpeg")},
        data={"hole_id": "DDH-1", "box_number": "3", "runs": runs},
    )


def wav() -> bytes:
    pcm = b"\0\0" * 1600
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, 16000, 32000, 2, 16) + b"data"
    return header + struct.pack("<I", len(pcm)) + pcm


def test_upload_review_correct_approve_and_export(tmp_path):
    c = client(tmp_path)
    r = upload(c)
    assert r.status_code == 202
    box = r.json()
    assert box["status"] == "ready" and len(box["runs"]) == 2
    bid = box["id"]
    assert c.get(f"/api/boxes/{bid}/tray.jpg").headers["content-type"] == "image/jpeg"

    r = c.post(f"/api/boxes/{bid}/runs/0/breaks/1", json={"kind": "mechanical"})
    assert r.json()["runs"][0]["log"]["rqd_pct"] == pytest.approx(93.0)
    assert r.json()["runs"][0]["machine_log"]["rqd_pct"] == pytest.approx(85.0)
    r = c.put(
        f"/api/boxes/{bid}/runs/1/description",
        json={"field": "alteration", "value": "weak chloritic", "source": "voice",
              "transcript": "alteración clorítica débil"},
    )  # fmt: skip
    assert r.status_code == 200

    log = c.get(f"/api/boxes/{bid}/log.csv")
    assert log.headers["content-disposition"].endswith('DDH-1_box03.csv"')
    lines = log.text.splitlines()
    assert lines[0].startswith("hole_id,box,from_m,to_m")
    assert len(lines) == 3 and ",93.0," in lines[1]
    corrections = c.get(f"/api/boxes/{bid}/corrections.csv").text.splitlines()
    assert len(corrections) == 3 and "alteración clorítica débil" in corrections[2]

    assert c.post(f"/api/boxes/{bid}/approve").json()["status"] == "approved"
    r = c.post(f"/api/boxes/{bid}/runs/0/breaks/0", json={"kind": "mechanical"})
    assert r.status_code == 400 and "approved" in r.json()["detail"]


def test_approving_a_box_runs_the_agents_and_drafts_are_approved_one_by_one(tmp_path):
    c = client(tmp_path)
    first = upload(c).json()["id"]
    c.post(f"/api/boxes/{first}/approve")
    second = c.post(
        "/api/boxes",
        files={"photo": ("box.jpg", photo_bytes(), "image/jpeg")},
        data={"hole_id": "DDH-1", "box_number": "4", "runs": "12.5-14"},
    ).json()["id"]
    box = c.post(f"/api/boxes/{second}/approve").json()
    assert box["handoffs"]["status"] == "done"
    assert box["handoffs"]["log"][0]["text"] == "history 1"  # box 3 of the same hole
    assert box["handoffs"]["drafts"][0]["status"] == "ready"

    box = c.post(f"/api/boxes/{second}/drafts/safety/approve").json()
    assert box["handoffs"]["drafts"][0]["status"] == "approved"
    r = c.post(f"/api/boxes/{second}/drafts/lab/approve")
    assert r.status_code == 400 and "no lab draft" in r.json()["detail"]


def test_a_draft_that_needs_review_is_approved_only_explicitly(tmp_path):
    def escalated(box, history, save):
        h = Handoffs(status="done", orchestrator_model="muse-wonder-1.0")
        h.drafts.append(AreaDraft(area="safety", model="muse-spark-1.3", status="needs_review",
                                  draft=Draft(title="Ground alert", body="Fair."),
                                  escalation="Needs review: 3 attempts failed. x"))  # fmt: skip
        save(h)

    c = client(tmp_path, handoffs=escalated)
    bid = upload(c).json()["id"]
    c.post(f"/api/boxes/{bid}/approve")
    r = c.post(f"/api/boxes/{bid}/drafts/safety/approve")
    assert r.status_code == 400 and "three times" in r.json()["detail"]
    r = c.post(f"/api/boxes/{bid}/drafts/safety/approve", json={"override": True})
    d = r.json()["handoffs"]["drafts"][0]
    assert d["status"] == "approved" and d["approved_over_checks"]


def test_agents_need_an_approved_box_and_a_crash_is_reported(tmp_path):
    def crash(box, history, save):
        raise RuntimeError("muse-wonder-1.0 500")

    c = client(tmp_path, handoffs=crash)
    bid = upload(c).json()["id"]
    assert c.post(f"/api/boxes/{bid}/handoffs").status_code == 400
    box = c.post(f"/api/boxes/{bid}/approve").json()
    assert box["handoffs"]["status"] == "failed" and "500" in box["handoffs"]["error"]
    assert c.post(f"/api/boxes/{bid}/handoffs").status_code == 202  # retry allowed


def test_bad_photo_is_refused_with_a_message(tmp_path):
    r = upload(client(tmp_path), data=b"not a photo")
    assert r.status_code == 400
    assert "could not be read" in r.json()["detail"]


def test_bad_run_list_is_refused_with_a_message(tmp_path):
    r = upload(client(tmp_path), runs="10 to 11")
    assert r.status_code == 400
    assert "from-to" in r.json()["detail"]


def test_box_without_scale_fails_with_the_reason(tmp_path):
    box = upload(client(tmp_path, failing_analyzer)).json()
    assert box["status"] == "failed" and "no scale" in box["error"]


def test_api_failure_is_shown_and_the_box_kept(tmp_path):
    c = client(tmp_path, broken_analyzer)
    box = upload(c).json()
    assert box["status"] == "failed" and "SAM 503" in box["error"]
    assert c.get(f"/api/boxes/{box['id']}").json()["status"] == "failed"
    assert c.get(f"/api/boxes/{box['id']}/log.csv").status_code == 409


def test_upload_passes_the_number_of_rows(tmp_path):
    seen = []

    def analyzer(photo, job, report):
        seen.append(job.n_rows)
        return fake_analyzer(photo, job, report)

    c = client(tmp_path, analyzer)
    form = {"hole_id": "DDH-1", "box_number": "3", "runs": "10-11", "n_rows": "4"}
    files = {"photo": ("box.jpg", photo_bytes(), "image/jpeg")}
    assert c.post("/api/boxes", files=files, data=form).status_code == 202
    assert upload(c).status_code == 202
    assert seen == [4, 5]
    form["n_rows"] = "1"
    assert c.post("/api/boxes", files=files, data=form).status_code == 422


def test_unknown_box_is_404(tmp_path):
    assert client(tmp_path).get("/api/boxes/nothere").status_code == 404


def test_transcribe_returns_text(tmp_path):
    r = client(tmp_path).post("/api/transcribe", files={"audio": ("a.wav", wav(), "audio/wav")})
    assert r.json() == {"transcript": "alteración clorítica débil", "duration_ms": 2100}


def test_transcribe_refuses_non_wav_and_survives_a_failure(tmp_path):
    c = client(tmp_path)
    r = c.post("/api/transcribe", files={"audio": ("a.webm", b"\x1aE\xdf\xa3", "audio/webm")})
    assert r.status_code == 400

    def down(wav):
        raise RuntimeError("Muse Voice Transcribe 500")

    r = client(tmp_path, transcriber=down).post(
        "/api/transcribe", files={"audio": ("a.wav", wav(), "audio/wav")}
    )
    assert r.status_code == 502 and "Type the correction" in r.json()["detail"]


def test_demo_caps_analyses_per_hour(tmp_path, monkeypatch):
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "1")
    c = client(tmp_path)
    assert upload(c).status_code == 202
    assert upload(c).status_code == 429


def test_parse_runs_checks_continuity():
    assert [r.to_m for r in parse_runs("1-2\n2-3.5")] == [2, 3.5]
    with pytest.raises(ReviewError, match="does not start"):
        parse_runs("1-2, 2.5-3")


def test_analysis_steps_and_images_are_saved_for_the_live_page(tmp_path):
    c = client(tmp_path)
    box = upload(c).json()
    cal = next(s for s in box["stages"] if s["key"] == "calibration")
    assert (cal["status"], cal["seconds"], cal["actor"]) == ("done", 0.12, "code")
    assert box["mask_rows"] == [0]
    assert c.get(f"/api/boxes/{box['id']}/masks/0.png").content == b"png"
    assert c.get(f"/api/boxes/{box['id']}/runs/0/crop.jpg").content == b"jpg"
    assert c.get(f"/api/boxes/{box['id']}/masks/3.png").status_code == 404


def test_rqd_working_follows_the_corrections(tmp_path):
    c = client(tmp_path)
    bid = upload(c).json()["id"]
    run = c.post(f"/api/boxes/{bid}/runs/0/breaks/1", json={"kind": "mechanical"}).json()["runs"][0]
    assert run["measure"]["intact_lengths_cm"] == [40.0, 53.0]  # 8 + 45 cm rejoined
    assert run["measure"]["rqd_cm"] == pytest.approx(93.0)


def test_split_a_piece_sam_merged(tmp_path):
    c = client(tmp_path)
    bid = upload(c).json()["id"]
    r = c.post(f"/api/boxes/{bid}/runs/0/pieces/0/split", json={"at_cm": 5.0})
    run = r.json()["runs"][0]
    assert run["log"]["rqd_pct"] == pytest.approx(80.0)  # 40 cm -> 5 + 35
    assert run["corrections"][-1]["corrected"] == "split at 5.0 cm (natural break)"
    r = c.post(f"/api/boxes/{bid}/runs/0/pieces/0/split", json={"at_cm": 30.0})
    assert r.status_code == 400 and "between" in r.json()["detail"]


def test_dictation_is_counted_in_the_box_ledger(tmp_path):
    c = client(tmp_path)
    bid = upload(c).json()["id"]
    c.post("/api/transcribe", files={"audio": ("a.wav", wav(), "audio/wav")}, data={"box_id": bid})
    voice = c.get(f"/api/boxes/{bid}").json()["voice"]
    assert (voice["dictations"], voice["audio_ms"]) == (1, 2100)


def test_a_refused_photo_keeps_the_gate_verdict(tmp_path):
    from coresight.schemas import GateReason, GateResult

    def refusing(photo, job, report):
        reason = GateReason(signal="calibration", value=0.0, detail="No tray slats were found.")
        report.gate(GateResult(ok=False, reasons=[reason], message="No tray slats were found."))
        raise ReviewError("No tray slats were found.")

    box = upload(client(tmp_path, refusing)).json()
    assert box["status"] == "failed" and box["error"] == "No tray slats were found."
    assert box["gate"]["reasons"][0]["signal"] == "calibration"


def test_a_tap_on_the_photo_lets_sam_cut_the_piece(tmp_path, monkeypatch):
    from coresight import review

    calls = []

    def fake_row_masks(sam, crop, cache_dir, prompt):
        calls.append(prompt)
        m = np.zeros(crop.shape[:2], dtype=bool)
        m[20:100, 450:634] = True  # 50.0 to 70.4 cm at 9 px per cm
        return [{"id": 1, "bounds": (0, 0, crop.shape[1], crop.shape[0]), "confidence": 0.95,
                 "mask": m}]  # fmt: skip

    monkeypatch.setattr(review, "row_masks", fake_row_masks)
    app = create_app(
        store=ReviewStore(tmp_path), analyzer=fake_analyzer, handoff_runner=fake_handoffs,
        background=False, sam_client=lambda: object(),
    )  # fmt: skip
    c = TestClient(app)
    bid = upload(c, runs="10-11").json()["id"]
    r = c.post(f"/api/boxes/{bid}/runs/0/sam-point", json={"points": [{"x": 540, "y": 60}]})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["changed"] and out["row"] == 0
    assert (out["start_cm"], out["end_cm"]) == (50.0, 70.44)
    assert out["mask"].startswith("data:image/png;base64,")
    assert calls == ["<0f>1<|point;x=540;y=60;w=900;h=120|>"]
    run = out["box"]["runs"][0]
    assert run["corrections"][-1]["source"] == "sam-point"
    assert run["log"]["natural_fractures"] == run["machine_log"]["natural_fractures"] + 1
    corrections = c.get(f"/api/boxes/{bid}/corrections.csv").text.splitlines()
    assert corrections[-1].endswith(",sam-point,")

    # a negative point refines the same piece: the first correction is replaced
    pts = [{"x": 540, "y": 60}, {"x": 620, "y": 60, "positive": False}]
    r = c.post(f"/api/boxes/{bid}/runs/0/sam-point", json={"points": pts, "refine": True})
    assert len(r.json()["box"]["runs"][0]["corrections"]) == 1
    assert calls[-1].endswith("-<|point;x=620;y=60;w=900;h=120|>")


def test_a_tap_needs_a_positive_point_first_and_a_box_under_review(tmp_path, monkeypatch):
    from coresight import review

    monkeypatch.setattr(review, "row_masks", lambda *a: pytest.fail("SAM must not be called"))
    app = create_app(
        store=ReviewStore(tmp_path), analyzer=fake_analyzer, handoff_runner=fake_handoffs,
        background=False, sam_client=lambda: object(),
    )  # fmt: skip
    c = TestClient(app)
    bid = upload(c, runs="10-11").json()["id"]
    bad = {"points": [{"x": 540, "y": 60, "positive": False}]}
    r = c.post(f"/api/boxes/{bid}/runs/0/sam-point", json=bad)
    assert r.status_code == 400 and "first point" in r.json()["detail"]
    assert c.post(f"/api/boxes/{bid}/runs/5/sam-point", json=bad).status_code == 400
