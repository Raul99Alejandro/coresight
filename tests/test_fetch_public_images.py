import importlib.util
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_public_images.py"
spec = importlib.util.spec_from_file_location("fetch_public_images", SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

JPEG = b"\xff\xd8\xff\xe0 photo"
ERROR_PAGE = b"<!DOCTYPE html><title>Wikimedia Error</title>"
URL = "https://upload.wikimedia.org/photo.jpg"


def client_with(*responses):
    queue = list(responses)
    calls = []

    def handler(request):
        calls.append(request)
        return queue.pop(0)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_waits_as_told_and_saves_after_a_429(tmp_path):
    client, calls = client_with(
        httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, content=JPEG)
    )
    waits = []
    target = tmp_path / "a.jpg"
    assert fetch.download(client, URL, target, sleep=waits.append)
    assert waits == [7]
    assert len(calls) == 2
    assert target.read_bytes() == JPEG


def test_a_persistent_429_raises_and_saves_nothing(tmp_path):
    client, _ = client_with(*[httpx.Response(429) for _ in range(fetch.RETRIES)])
    target = tmp_path / "a.jpg"
    with pytest.raises(httpx.HTTPStatusError):
        fetch.download(client, URL, target, sleep=lambda _: None)
    assert not target.exists()


def test_an_error_page_with_status_200_is_not_saved(tmp_path):
    client, _ = client_with(httpx.Response(200, content=ERROR_PAGE))
    target = tmp_path / "a.jpg"
    with pytest.raises(RuntimeError):
        fetch.download(client, URL, target, sleep=lambda _: None)
    assert not target.exists()


def test_a_saved_error_page_is_downloaded_again(tmp_path):
    client, _ = client_with(httpx.Response(200, content=JPEG))
    target = tmp_path / "a.jpg"
    target.write_bytes(ERROR_PAGE)
    assert fetch.download(client, URL, target, sleep=lambda _: None)
    assert target.read_bytes() == JPEG


def test_a_good_photo_is_kept_without_a_request(tmp_path):
    client, calls = client_with()
    target = tmp_path / "a.jpg"
    target.write_bytes(JPEG)
    assert not fetch.download(client, URL, target, sleep=lambda _: None)
    assert calls == []
