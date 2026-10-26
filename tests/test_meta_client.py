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
