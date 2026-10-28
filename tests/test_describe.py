import json

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

from coresight.anomalies import rule_anomalies, with_rule_anomalies
from coresight.baseten_client import BasetenClient, cost_usd
from coresight.calibration import Row, Tray
from coresight.crops import ROW_GAP_PX, run_crop, run_spans
from coresight.glimmer_client import GlimmerClient
from coresight.meta_client import MetaClient
from coresight.pipeline import describe_runs
from coresight.runs import Position
from coresight.schemas import (
    AnomalySource,
    AnomalyType,
    GeologyDescription,
    IntervalResult,
    ModelDescription,
)

MODEL_JSON = {
    "lithology": "Grey medium-grained granodiorite, massive",
    "alteration": "weak chloritic",
    "mineralization": "2% disseminated pyrite and chalcopyrite",
    "anomalies": [{"type": "visible_sulfides", "explanation": "Pyrite blebs in the middle."}],
    "confidence": 0.7,
}


def result(tcr=100.0, ff=2.0, complete=True, from_m=10.0, to_m=13.0) -> IntervalResult:
    return IntervalResult(
        from_m=from_m,
        to_m=to_m,
        rqd_pct=80.0,
        tcr_pct=tcr,
        natural_fractures=int(ff * (to_m - from_m)),
        fracture_frequency_per_m=ff,
        uncertain_breaks=0,
        mechanical_breaks=0,
        rock_quality="good",
        complete=complete,
    )


def described(**update) -> GeologyDescription:
    return GeologyDescription.model_validate({**MODEL_JSON, **update})


# --- anomalies: the three types fire --------------------------------------------------


def test_low_recovery_comes_from_tcr():
    (a,) = rule_anomalies(result(tcr=70.0))
    assert a.type == AnomalyType.LOW_RECOVERY
    assert a.source == AnomalySource.RULE
    assert "70%" in a.explanation


def test_intense_fracturing_comes_from_fracture_frequency():
    (a,) = rule_anomalies(result(ff=14.5))
    assert a.type == AnomalyType.INTENSE_FRACTURING
    assert "14.5" in a.explanation


def test_visible_sulfides_come_from_the_model_and_are_kept():
    out = with_rule_anomalies(described(), result(tcr=60.0, ff=20.0))
    assert [a.type for a in out.anomalies] == [
        AnomalyType.LOW_RECOVERY,
        AnomalyType.INTENSE_FRACTURING,
        AnomalyType.VISIBLE_SULFIDES,
    ]
    assert out.anomalies[2].source == AnomalySource.MODEL


def test_good_rock_has_no_rule_anomalies():
    assert rule_anomalies(result(tcr=85.0, ff=10.0)) == []


def test_incomplete_run_is_not_judged():
    assert rule_anomalies(result(tcr=30.0, ff=25.0, complete=False)) == []


def test_model_cannot_claim_rule_anomalies():
    fake = described(anomalies=[{"type": "low_recovery", "explanation": "looks short"}])
    out = with_rule_anomalies(fake, result(tcr=100.0))
    assert out.anomalies == []
    once = with_rule_anomalies(out, result(tcr=50.0))
    assert with_rule_anomalies(once, result(tcr=50.0)) == once


def test_model_schema_rejects_rule_types():
    bad = {**MODEL_JSON, "anomalies": [{"type": "intense_fracturing", "explanation": "x"}]}
    with pytest.raises(ValidationError):
        ModelDescription.model_validate(bad)
    enum = ModelDescription.model_json_schema()["$defs"]["ModelAnomaly"]["properties"]["type"]
    assert enum["enum"] == ["visible_sulfides", "other"]


# --- crops ------------------------------------------------------------------------------


def test_run_spans_follow_the_markers():
    markers = [Position(1, 40.0), Position(3, 10.0)]
    spans = run_spans(markers, 3)
    assert spans[0] == (Position(0, 0.0), Position(1, 40.0))
    assert spans[1] == (Position(1, 40.0), Position(3, 10.0))
    assert spans[2][0] == Position(3, 10.0)
    # as many markers as runs: the core after the last marker belongs to the next box
    assert len(run_spans([Position(0, 50.0), Position(1, 50.0)], 2)) == 2


def rows_with_ids(n=3, h=20, w=100):
    """Rows whose pixels hold (row, x, 0), so a crop shows where it was cut."""
    rows = []
    for r in range(n):
        row = np.zeros((h, w, 3), dtype=np.uint8)
        row[..., 0] = r + 1
        row[..., 1] = np.arange(w, dtype=np.uint8)
        rows.append(row)
    return rows


def test_run_crop_stacks_the_slices_of_each_row():
    rows = rows_with_ids()
    crop = run_crop(rows, 1.0, Position(0, 60.0), Position(2, 30.0))
    assert crop.shape == (3 * 20 + 2 * ROW_GAP_PX, 100, 3)
    assert crop[0, 0, 1] == 60 and crop[0, 39, 1] == 99  # row 0 from 60 cm to its end
    assert crop[0, 40, 0] == 0  # padded
    second = crop[20 + ROW_GAP_PX]
    assert second[0, 0] == 2 and second[99, 1] == 99  # the whole of row 1
    third = crop[-1]
    assert third[0, 0] == 3 and third[29, 1] == 29 and third[30, 0] == 0


def test_run_crop_inside_one_row():
    crop = run_crop(rows_with_ids(), 2.0, Position(1, 10.0), Position(1, 20.0))
    assert crop.shape == (20, 20, 3)
    assert crop[0, 0, 1] == 20


def test_run_crop_with_nothing_between_markers_fails():
    with pytest.raises(ValueError, match="no core"):
        run_crop(rows_with_ids(), 1.0, Position(2, 99.5), Position(2, 100.0))


# --- pipeline.describe with a fake backend ---------------------------------------------


class FakeDescriber:
    model = "fake-model"

    def __init__(self):
        self.calls = []

    def describe_interval(self, image_png, context):
        self.calls.append((image_png, context))
        return described()


def flat_tray(n_rows=2, row_h=50, width=200, px_per_cm=2.0) -> Tray:
    return Tray(
        corners=np.zeros((4, 2)),
        homography=np.eye(3),
        width=width,
        height=n_rows * row_h,
        px_per_cm=px_per_cm,
        rows=[Row(i, i * row_h, (i + 1) * row_h) for i in range(n_rows)],
    )


def test_describe_runs_one_validated_description_per_run():
    image = np.full((100, 200, 3), 128, dtype=np.uint8)
    logs = [result(tcr=60.0, from_m=10.0, to_m=11.0), result(ff=15.0, from_m=11.0, to_m=12.0)]
    backend = FakeDescriber()
    out = describe_runs(image, flat_tray(), [Position(0, 60.0)], logs, backend, {"hole_id": "H1"})
    assert [(d.from_m, d.to_m) for d in out] == [(10.0, 11.0), (11.0, 12.0)]
    assert {d.backend for d in out} == {"fake-model"}
    assert [a.type for a in out[0].description.anomalies][0] == AnomalyType.LOW_RECOVERY
    assert [a.type for a in out[1].description.anomalies][0] == AnomalyType.INTENSE_FRACTURING
    assert backend.calls[0][1] == {"hole_id": "H1", "from_m": 10.0, "to_m": 11.0}
    assert backend.calls[0][0].startswith(b"\x89PNG")


# --- the two backends: same contract ---------------------------------------------------


def spark(tmp_path, answer):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        body = {"output": [{"content": [{"type": "output_text", "text": answer}]}]}
        return httpx.Response(200, json=body)

    client = MetaClient(api_key="test", cache_dir=tmp_path, transport=httpx.MockTransport(handler))
    return client, calls


def baseten(tmp_path, answer):
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        message = {"role": "assistant", "reasoning_content": "Let me look.", "content": answer}
        usage = {"prompt_tokens": 1000, "completion_tokens": 2000, "total_tokens": 3000}
        return httpx.Response(200, json={"choices": [{"message": message}], "usage": usage})

    client = BasetenClient(
        api_key="test", cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    return client, calls


LOCAL = "http://127.0.0.1:8080/v1"


def glimmer(tmp_path, answer):
    calls = []

    def handler(request):
        calls.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": answer}}]})

    client = GlimmerClient(
        base_url=LOCAL, cache_dir=tmp_path, transport=httpx.MockTransport(handler)
    )
    return client, calls


@pytest.mark.parametrize("make", [spark, glimmer, baseten])
def test_backends_return_the_same_validated_description(tmp_path, make):
    client, calls = make(tmp_path, json.dumps(MODEL_JSON))
    first = client.describe_interval(b"png", {"from_m": 1.0})
    again = client.describe_interval(b"png", {"from_m": 1.0})
    assert first == again == described()
    assert first.anomalies[0].source == AnomalySource.MODEL
    assert len(calls) == 1  # the second answer came from the cache
    assert len(list((tmp_path / "describe" / client.model).glob("*.json"))) == 1


@pytest.mark.parametrize("make", [spark, glimmer, baseten])
def test_backends_reject_invalid_answers_and_do_not_cache_them(tmp_path, make):
    client, _ = make(tmp_path, json.dumps({**MODEL_JSON, "confidence": 3}))
    with pytest.raises(ValidationError):
        client.describe_interval(b"png", {})
    assert not (tmp_path / "describe").exists()


def test_spark_request_uses_responses_and_the_restricted_schema(tmp_path):
    client, calls = spark(tmp_path, json.dumps(MODEL_JSON))
    client.describe_interval(b"png", {"hole_id": "H1"})
    body = calls[0]
    assert body["model"] == "muse-spark-1.3"
    content = body["input"][0]["content"]
    assert content[1]["image_url"].startswith("data:image/png;base64,")
    assert '"hole_id": "H1"' in content[0]["text"]
    schema = body["text"]["format"]["schema"]
    assert "low_recovery" not in json.dumps(schema)


def test_glimmer_request_is_openai_chat_with_image_and_json_schema(tmp_path):
    client, calls = glimmer(tmp_path, json.dumps(MODEL_JSON))
    client.describe_interval(b"png", {"hole_id": "H1"})
    path, body = calls[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "muse-glimmer"
    content = body["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["response_format"]["type"] == "json_schema"
    assert "low_recovery" not in json.dumps(body["response_format"])


def test_glimmer_retries_when_the_server_is_busy(tmp_path):
    ok = {"choices": [{"message": {"content": json.dumps(MODEL_JSON)}}]}
    answers = [httpx.Response(503), httpx.Response(200, json=ok)]
    waits = []
    client = GlimmerClient(
        base_url=LOCAL,
        cache_dir=tmp_path,
        transport=httpx.MockTransport(lambda request: answers.pop(0)),
        sleep=waits.append,
    )
    assert client.describe_interval(b"png", {}) == described()
    assert waits == [5.0]


def test_baseten_request_uses_the_keyed_model_and_skips_the_reasoning(tmp_path):
    client, calls = baseten(tmp_path, json.dumps(MODEL_JSON))
    assert client.describe_interval(b"png", {"hole_id": "H1"}) == described()
    path, body = calls[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "meta-models/muse-spark-open-1026"
    content = body["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert body["response_format"]["json_schema"]["name"] == "GeologyDescription"
    assert "low_recovery" not in json.dumps(body["response_format"])


def test_baseten_usage_is_recorded_and_priced(tmp_path):
    client, _ = baseten(tmp_path, json.dumps(MODEL_JSON))
    client.describe_interval(b"png", {})
    client.describe_interval(b"png", {})  # cached: not paid again
    assert len(client.usage) == 1
    assert cost_usd(client.usage[0]) == pytest.approx((1000 * 1.25 + 2000 * 4.25) / 1e6)


# Few-shot from the geologist's corrections (point F)


def test_the_prompt_is_unchanged_without_corrections():
    from coresight.describe import EXAMPLES_KEY, describe_prompt

    ctx = {"hole_id": "DDH-1", "from_m": 1.0}
    assert describe_prompt(ctx) == describe_prompt({**ctx, EXAMPLES_KEY: []})
    assert EXAMPLES_KEY not in describe_prompt(ctx)


def test_corrections_become_examples_after_the_context():
    from coresight.describe import EXAMPLES_KEY, MAX_EXAMPLES, describe_prompt

    ex = [{"field": "lithology", "model": f"granite {i}", "geologist": f"gneiss {i}"}
          for i in range(MAX_EXAMPLES + 2)]  # fmt: skip
    p = describe_prompt({"hole_id": "DDH-1", EXAMPLES_KEY: ex})
    assert '"hole_id": "DDH-1"' in p and EXAMPLES_KEY not in p.split("Context:")[1].split("\n")[0]
    assert 'the model wrote "granite 0"' in p and 'corrected it to "gneiss 0"' in p
    assert f"granite {MAX_EXAMPLES}" not in p  # at most MAX_EXAMPLES
    assert p.index("Context:") < p.index("granite 0")
