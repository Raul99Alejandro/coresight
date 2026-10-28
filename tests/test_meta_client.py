import json
from pathlib import Path

import httpx
import pytest

from coresight.meta_client import MetaClient, TransientAPIError, parse_sam_text, sam_masks

# One real SAM 3.1 record (prompt "stone", Onkalo 1 at 2048 px wide), Oct 26.
SAM_ONE_RECORD = Path(__file__).parent / "data" / "sam_one_record.txt"


def test_sam_masks_decodes_real_record_at_its_bounds():
    masks = sam_masks(SAM_ONE_RECORD.read_text(encoding="utf-8"))
    assert len(masks) == 1
    left, top, right, bottom = masks[0]["bounds"]
    assert masks[0]["mask"].shape == (bottom - top, right - left)
    assert 0.5 < masks[0]["mask"].mean() < 1.0
    assert masks[0]["id"] == 0


def test_parse_sam_text_reads_box_and_mask_per_record():
    text = (
        "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.91|>"
        "<|mask;x=0;y=0;c=0.91;data=27,60,~abc|>,"
        "3<|box;x1=1;y1=2;x2=30;y2=40;w=320;h=334|><|mask;x=0;y=0;data=39,30,!xyz|>"
    )
    records = parse_sam_text(text)
    assert [r["id"] for r in records] == [0, 3]
    assert records[0]["box"]["x2"] == 270
    assert records[0]["box"]["c"] == 0.91
    assert records[0]["mask"] == "27,60,~abc"
    assert records[1]["mask"] == "39,30,!xyz"


def test_parse_sam_text_payload_with_separator_characters():
    text = (
        "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=10;h=10|><|mask;x=0;y=0;data=2,2,~a|>b,c;d|>,"
        "1<|box;x1=5;y1=6;x2=7;y2=8;w=10;h=10|><|mask;x=0;y=0;data=2,2,!z|>\n"
    )
    records = parse_sam_text(text)
    assert [r["mask"] for r in records] == ["2,2,~a|>b,c;d", "2,2,!z"]


def test_parse_sam_text_no_matches():
    assert parse_sam_text("") == []


SSE_OK = (
    'data: {"type": "response.output_text.delta", "delta": "0<|box;x1=1|>"}\n\n'
    'data: {"type": "response.output_text.delta", "delta": "<|mask;data=2,2,~a|>"}\n\n'
    "data: [DONE]\n\n"
)


def fake_client(tmp_path, statuses, waits=None):
    """MetaClient whose HTTP answers come from ``statuses`` (an int status or an exception)."""
    calls = []

    def handler(request):
        calls.append(request)
        status = statuses[min(len(calls) - 1, len(statuses) - 1)]
        if isinstance(status, Exception):
            raise status
        if status == 200:
            return httpx.Response(200, text=SSE_OK)
        return httpx.Response(status, text="error")

    client = MetaClient(
        api_key="test",
        cache_dir=tmp_path,
        backoff_s=1.0,
        transport=httpx.MockTransport(handler),
        sleep=(waits.append if waits is not None else lambda s: None),
    )
    return client, calls


def test_sam_response_is_cached_by_image_and_prompt(tmp_path):
    client, calls = fake_client(tmp_path, [200])
    first = client.segment_row_raw(b"png-bytes", "stone")
    again = client.segment_row_raw(b"png-bytes", "stone")
    assert first == again == "0<|box;x1=1|><|mask;data=2,2,~a|>"
    assert len(calls) == 1
    client.segment_row_raw(b"png-bytes", "rock")
    client.segment_row_raw(b"other-bytes", "stone")
    assert len(calls) == 3
    assert len(list((tmp_path / "sam").glob("*.txt"))) == 3


def test_transient_errors_are_retried_with_backoff(tmp_path):
    waits = []
    client, calls = fake_client(
        tmp_path, [429, httpx.ConnectTimeout("slow"), 503, 200], waits=waits
    )
    assert client.segment_row_raw(b"png", "stone").startswith("0<|box")
    assert len(calls) == 4
    assert waits == [1.0, 2.0, 4.0]


def test_client_errors_are_not_retried(tmp_path):
    client, calls = fake_client(tmp_path, [400])
    with pytest.raises(RuntimeError, match="SAM 400"):
        client.segment_row_raw(b"png", "stone")
    assert len(calls) == 1
    assert not (tmp_path / "sam").exists()


def test_retries_give_up_after_max_retries(tmp_path):
    client, calls = fake_client(tmp_path, [500])
    with pytest.raises(TransientAPIError):
        client.segment_row_raw(b"png", "stone")
    assert len(calls) == client.max_retries + 1


def test_transcribe_sends_documented_multipart_and_validates_answer(tmp_path):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["accept"] = request.headers["accept"]
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={"sessionId": "s1", "transcript": "pirita diseminada", "audioDurationMs": 1800,
                  "turns": []},
        )  # fmt: skip

    client = MetaClient(api_key="k", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    t = client.transcribe(b"RIFF....WAVE", keywords=["pyrite"])
    assert t.transcript == "pirita diseminada" and t.audioDurationMs == 1800
    assert seen["path"] == "/v1/asr/transcribe"
    assert seen["accept"] == "application/json"
    body = seen["body"]
    assert b'name="request"' in body and b'"model": "muse-voice-transcribe-1.0"' in body
    assert b'"audioEncoding": "WAV"' in body and b'"mode": "PUSH_TO_TALK"' in body
    assert b'name="audio"; filename="dictation.wav"' in body and b"audio/wav" in body


def test_transcribe_retries_a_rate_limit(tmp_path):
    answers = [httpx.Response(429, text="busy"),
               httpx.Response(200, json={"sessionId": "s", "transcript": "ok",
                                         "audioDurationMs": 1, "turns": []})]  # fmt: skip
    client = MetaClient(
        api_key="k", cache_dir=tmp_path, sleep=lambda s: None,
        transport=httpx.MockTransport(lambda r: answers.pop(0)),
    )  # fmt: skip
    assert client.transcribe(b"RIFF").transcript == "ok"


def test_respond_posts_the_body_and_caches_the_answer(tmp_path):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"output": [{"type": "function_call", "name": "x"}]})

    client = MetaClient(api_key="k", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    body = {"model": "muse-wonder-1.0", "input": [], "tools": []}
    assert client.respond(body)["output"][0]["name"] == "x"
    assert client.respond(dict(body))["output"][0]["name"] == "x"
    assert calls == [body]  # the second answer came from data/cache/responses


def test_locate_row_asks_for_grounding_with_a_schema_and_caches_it(tmp_path):
    calls = []
    answer = {"objects": [{"kind": "core", "x_min": 12, "y_min": 80, "x_max": 240, "y_max": 920},
                          {"kind": "run_block", "x_min": 241, "y_min": 60, "x_max": 270,
                           "y_max": 1003}]}  # fmt: skip

    def handler(request):
        calls.append(json.loads(request.content))
        text = json.dumps(answer)
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": text}]}]}
        )

    client = MetaClient(api_key="k", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    first = client.locate_row(b"png")
    again = client.locate_row(b"png")
    assert len(calls) == 1 and first == again
    assert [o.kind for o in first.objects] == ["core", "run_block"]
    body = calls[0]
    assert body["model"] == "muse-spark-1.3"
    assert body["text"]["format"]["name"] == "RowLocation"
    assert "0 to 1000 grid" in body["input"][0]["content"][0]["text"]


# The credit watch (point G): every request that reached the API, and every cache hit


def test_every_request_and_cache_hit_is_logged_without_prompts(tmp_path):
    from coresight.meta_client import usage_summary

    def handler(request):
        usage = {"input_tokens": 120, "output_tokens": 30}
        return httpx.Response(200, json={"output": [], "usage": usage})

    client = MetaClient(api_key="k", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    body = {"model": "muse-wonder-1.0", "input": "secret prompt"}
    client.respond(body)
    client.respond(body)  # same request: from the cache
    entries = client.usage.entries()
    assert [e.get("cached", False) for e in entries] == [False, True]
    assert entries[0]["status"] == 200 and entries[0]["input_tokens"] == 120
    assert "secret" not in (tmp_path / "usage.jsonl").read_text()
    wonder = usage_summary(entries)["hour"]["muse-wonder-1.0"]
    assert (wonder["calls"], wonder["cached"], wonder["output_tokens"]) == (1, 1, 30)


def test_rate_limits_and_old_calls_are_counted_apart():
    from coresight.meta_client import usage_summary

    now = 1_000_000.0
    entries = [
        {"at": now - 10, "model": "sam-3.1", "status": 429, "seconds": 0.2},
        {"at": now - 20, "model": "sam-3.1", "status": 200, "seconds": 3.0},
        {"at": now - 7200, "model": "sam-3.1", "status": 200, "seconds": 2.0},
    ]
    s = usage_summary(entries, now)
    assert s["hour"]["sam-3.1"]["calls"] == 2 and s["hour"]["sam-3.1"]["rate_limited"] == 1
    assert s["day"]["sam-3.1"]["calls"] == 3 and s["all"]["sam-3.1"]["seconds"] == 5.2


def test_without_a_cache_dir_nothing_is_logged():
    client = MetaClient(api_key="k", cache_dir=None, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"usage": {}})))  # fmt: skip
    client.respond({"model": "m"})
    assert client.usage is None
