"""The abuse test (point G): what a sceptical judge uploads first, through the API.

Every case must end in a message the person can act on, never in a number:
a photo that is not a core box, a huge photo, a strange or damaged file, a box
without scale, and many uploads in a row.
"""

import struct
import zlib
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from test_api import client, fake_analyzer, photo_bytes, upload
from test_review import GateClient, tray_photo

from coresight import review
from coresight.api import create_app
from coresight.review import ReviewStore
from coresight.schemas import TrayCheck

DATA = Path(__file__).parent / "data"


def real_analyzer(spark_check):
    """The real pipeline (review.analyze) with Muse Spark's answer fixed and no SAM."""
    seen = {}

    def analyzer(photo, job, report):
        seen["client"] = GateClient(spark_check)
        return review.analyze(photo, job.box_length_cm, job.runs, job.first_starts_in_box,
                              seen["client"], None, report=report, n_rows=job.n_rows)  # fmt: skip

    analyzer.seen = seen
    return analyzer


def png_header(w: int, h: int) -> bytes:
    """A valid PNG signature and IHDR that declares a w x h image, with no pixels."""
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    crc = struct.pack(">I", zlib.crc32(chunk))
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + chunk + crc


def detail(r) -> str:
    assert isinstance(r.json()["detail"], str)  # a sentence the page shows as it is
    return r.json()["detail"]


# 1. A photo that is not a core box


def test_a_screenshot_is_refused_by_calibration_and_costs_no_sam_call(tmp_path):
    analyzer = real_analyzer(RuntimeError("Muse Spark is down"))
    c = client(tmp_path, analyzer)
    box = upload(c, data=(DATA / "screenshot_glyphs.jpg").read_bytes()).json()
    assert box["status"] == "failed"
    assert "no scale" in box["error"] and "from above" in box["error"]
    assert box["runs"] == [] and analyzer.seen["client"].sam_calls == 0


def test_a_photo_spark_says_is_not_a_tray_is_refused_with_what_it_shows(tmp_path):
    check = TrayCheck(is_core_tray=False, what_it_shows="a person taking a selfie", confidence=1.0)
    analyzer = real_analyzer(check)
    box = upload(client(tmp_path, analyzer), data=tray_photo()).json()
    assert box["status"] == "failed" and "a person taking a selfie" in box["error"]
    assert box["gate"]["ok"] is False and analyzer.seen["client"].sam_calls == 0


# 2. A huge photo


def test_a_photo_over_the_size_limit_is_refused(tmp_path):
    big = b"\xff\xd8\xff" + b"\0" * (21 * 2**20)
    r = upload(client(tmp_path), data=big)
    assert r.status_code == 400 and "larger than 20 MB" in detail(r)


def test_a_small_file_that_declares_a_huge_image_is_refused_before_decoding(tmp_path, monkeypatch):
    def never(*_):
        raise AssertionError("a decompression bomb must not reach cv2.imdecode")

    monkeypatch.setattr(review.cv2, "imdecode", never)
    r = upload(client(tmp_path), data=png_header(60000, 60000))
    assert r.status_code == 400
    assert "60000 x 60000 px" in detail(r) and "8000 px" in detail(r)


def test_a_photo_too_small_to_measure_is_refused(tmp_path):
    ok, jpg = cv2.imencode(".jpg", np.full((200, 300, 3), 120, np.uint8))
    r = upload(client(tmp_path), data=jpg.tobytes())
    assert r.status_code == 400 and "too small" in detail(r)


# 3. A strange or damaged file


@pytest.mark.parametrize(
    "data, says",
    [
        (bytes([0xFF, 0xD8, 0xFF]), "cut short"),  # upload() turns b"" into a photo
        (b"GIF89a" + b"\0" * 64, "a GIF"),
        (b"%PDF-1.7\n" + b"\0" * 64, "a PDF document"),
        (b"\0\0\0\x18ftypheic" + b"\0" * 64, "HEIC"),
        (b"II*\0" + b"\0" * 64, "a TIFF file"),
        (b"<!doctype html><html><body>hello</body></html>", "could not be read"),
    ],
)
def test_a_file_that_is_not_a_photo_says_what_it_is(tmp_path, data, says):
    r = upload(client(tmp_path), data=data)
    assert r.status_code == 400 and says in detail(r)
    assert "JPG" in detail(r)


def test_a_damaged_jpg_is_refused(tmp_path):
    whole = photo_bytes()
    r = upload(client(tmp_path), data=whole[:200])  # header intact, image data cut off
    assert r.status_code == 400 and "damaged" in detail(r)


def test_webp_is_accepted(tmp_path):
    ok, webp = cv2.imencode(".webp", np.full((600, 900, 3), 120, np.uint8))
    assert review.photo_size(webp.tobytes()) == (900, 600)
    assert upload(client(tmp_path), data=webp.tobytes()).status_code == 202


def test_jpg_and_png_sizes_come_from_the_header():
    img = np.zeros((450, 1234, 3), np.uint8)
    for ext in (".jpg", ".png"):
        assert review.photo_size(cv2.imencode(ext, img)[1].tobytes()) == (1234, 450)


def test_a_bad_form_field_names_the_field(tmp_path):
    c = client(tmp_path)
    files = {"photo": ("box.jpg", photo_bytes(), "image/jpeg")}
    form = {"hole_id": "DDH-1", "box_number": "0", "runs": "10-11"}
    r = c.post("/api/boxes", files=files, data=form)
    assert r.status_code == 422 and "box_number" in detail(r)


# 4. A box without scale


def test_a_box_without_scale_says_how_to_retake_the_photo(tmp_path):
    ok, png = cv2.imencode(".png", np.full((600, 900, 3), 128, np.uint8))
    box = upload(client(tmp_path, real_analyzer(RuntimeError("down"))), data=png.tobytes()).json()
    assert box["status"] == "failed" and "no scale" in box["error"]
    assert "slats visible" in box["error"]


# 5. Many uploads in a row


def test_one_visitor_cannot_start_many_analyses_in_a_row(tmp_path, monkeypatch):
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_VISITOR", "2")
    c = client(tmp_path)
    assert [upload(c).status_code for _ in range(2)] == [202, 202]
    r = upload(c)
    assert r.status_code == 429
    assert "2 analyses in 10 minutes" in detail(r) and "sample" in detail(r)


def test_refused_photos_do_not_use_up_the_visitor_allowance(tmp_path, monkeypatch):
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_VISITOR", "1")
    c = client(tmp_path)
    assert upload(c, data=b"%PDF-1.7" + b"\0" * 64).status_code == 400
    assert upload(c).status_code == 202


def test_the_hourly_cap_for_everybody_is_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "1")
    c = client(tmp_path)
    assert upload(c).status_code == 202
    r = upload(c)
    assert r.status_code == 429 and "per hour" in detail(r)


def test_samples_do_not_use_up_the_upload_allowance(tmp_path, monkeypatch):
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_VISITOR", "1")
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "1")
    app = create_app(store=ReviewStore(tmp_path), analyzer=lambda p, j, r: (_ for _ in ()).throw(
        review.ReviewError("stop")), background=False)  # fmt: skip
    c = TestClient(app)
    for _ in range(3):  # cached samples are cheap: their own, larger cap
        assert c.post("/api/samples/onkalo-box5").status_code == 202
    assert upload(c).status_code == 202


# The credit watch: for us, never for the judge


def test_the_credit_watch_is_hidden_without_its_token(tmp_path, monkeypatch):
    monkeypatch.delenv("CORESIGHT_OPS_TOKEN", raising=False)
    c = client(tmp_path)
    assert c.get("/api/ops/usage").status_code == 404
    monkeypatch.setenv("CORESIGHT_OPS_TOKEN", "s3cret")
    assert c.get("/api/ops/usage").status_code == 403
    assert c.get("/api/ops/usage", headers={"X-Ops-Token": "wrong"}).status_code == 403


def test_the_credit_watch_shows_calls_and_what_is_left(tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("CORESIGHT_OPS_TOKEN", "s3cret")
    monkeypatch.setenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "5")
    usage = tmp_path / "usage.jsonl"
    lines = [{"at": 9e9, "model": "sam-3.1", "status": 200, "seconds": 2.0},
             {"at": 9e9, "model": "sam-3.1", "cached": True}]  # fmt: skip
    usage.write_text("".join(json.dumps(e) + "\n" for e in lines))
    app = create_app(store=ReviewStore(tmp_path / "boxes"), analyzer=fake_analyzer,
                     background=False, usage_path=usage)  # fmt: skip
    c = TestClient(app)
    upload(c)
    r = c.get("/api/ops/usage", headers={"X-Ops-Token": "s3cret"}).json()
    assert r["limits"]["analyses"] == {"per_hour": 5, "left": 4}
    assert r["boxes"] == {"ready": 1} and r["uploads"] == 1
    assert r["usage"]["all"]["sam-3.1"]["calls"] == 1
