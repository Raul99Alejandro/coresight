"""Orchestrator and area agents with a simulated Model API (no network)."""

import json

import pytest
from test_review import PIECES, make_box, make_run

from coresight import agents
from coresight.agents import (
    QuoteArg,
    QuoteLine,
    RunArg,
    Toolbox,
    approve_draft,
    draft_handoffs,
    load_prices,
)
from coresight.meta_client import MUSE_SPARK_MODEL_ID, MUSE_WONDER_MODEL_ID
from coresight.schemas import Check

ROUTES = {
    "routes": [
        {"area": "lab", "applies": True, "reason": "Run 2 shows sulfides.", "runs": [1]},
        {"area": "safety", "applies": True, "reason": "Run 2 is fair, RQD 56.7.", "runs": [1]},
        {"area": "plant", "applies": False, "reason": "No earlier box to compare."},
        {"area": "finance", "applies": True, "reason": "Lab applies."},
    ]
}
LAB = {
    "title": "Assay request",
    "body": "Sample 11-12.5 m, 2 samples, PREP and AU-FA.",
    "priority": "high",
    "intervals": [{"from_m": 11.0, "to_m": 12.5}],
}
SAFETY = {
    "title": "Ground alert",
    "body": "Fair rock, RQD 56.7%.",
    "intervals": [{"from_m": 11.0, "to_m": 12.5}],
    "figures": [{"run": 2, "metric": "rqd_pct", "value": 56.7}],
}
FINANCE = {
    "title": "Assay cost",
    "body": "Example prices. $54.00.",
    "lines": [
        {"code": "PREP", "samples": 2, "unit_usd": 9.0, "total_usd": 18.0},
        {"code": "AU-FA", "samples": 2, "unit_usd": 18.0, "total_usd": 36.0},
    ],
    "total_usd": 54.0,
}


def call(name, args, n=[0]):  # noqa: B006 - a counter for unique call ids
    n[0] += 1
    return {"type": "function_call", "name": name, "arguments": json.dumps(args),
            "call_id": f"call_{n[0]}"}  # fmt: skip


class FakeClient:
    """Answers each request with the next scripted turn and records what was asked."""

    def __init__(self, turns, fail_models=()):
        self.turns, self.fail_models, self.bodies = list(turns), set(fail_models), []

    def respond(self, body):
        self.bodies.append(body)
        if body["model"] in self.fail_models:
            raise RuntimeError(f"{body['model']} 500: upstream error")
        return {"output": self.turns.pop(0)}


def all_ok(area, draft, box, prices, history=()):
    return [Check(name="figures", ok=True)]


@pytest.fixture
def box():
    return make_box(make_run(PIECES, 10, 11), make_run(PIECES, 11, 12.5), status="approved")


def happy_turns():
    return [
        [call("box_summary", {})],
        [call("route_box", ROUTES)],
        [call("count_samples", {"from_m": 11.0, "to_m": 12.5})],
        [call("submit_draft", LAB)],
        [call("run_metrics", {"run": 2})],
        [call("submit_draft", SAFETY)],
        [call("lab_request", {}), call("quote", {"lines": [
            {"code": "PREP", "samples": 2}, {"code": "AU-FA", "samples": 2}]})],  # fmt: skip
        [call("submit_draft", FINANCE)],
    ]


def test_wonder_routes_and_each_area_drafts_with_tools(box):
    client = FakeClient(happy_turns())
    saves = []
    h = draft_handoffs(box, [], client, all_ok, save=lambda h: saves.append(h.status))

    assert h.status == "done" and h.orchestrator_model == MUSE_WONDER_MODEL_ID
    assert [d.area for d in h.drafts] == ["lab", "safety", "finance"]  # plant does not apply
    assert all(d.status == "ready" and d.verified for d in h.drafts)
    assert h.drafts[2].draft.total_usd == 54.0
    assert client.bodies[0]["model"] == MUSE_WONDER_MODEL_ID
    assert {b["model"] for b in client.bodies[2:]} == {MUSE_SPARK_MODEL_ID}
    texts = [e.text for e in h.log]
    assert "Read the box from geometry.py: 2 runs; the worst is run 2, RQD 56.7 %" in texts
    assert ("Read run 2 (11.00 to 12.50 m): RQD 56.7 %, recovery 62.0 %, "
            "1.3 fractures per metre, fair rock") in texts  # fmt: skip
    assert not any("_pct" in t or "{" in t for t in texts)  # sentences, not field names
    assert any("Plant does not apply" in t for t in texts)
    assert len(saves) > 5  # the page sees progress while the agents work


def test_tool_results_go_back_to_the_model(box):
    client = FakeClient(happy_turns())
    draft_handoffs(box, [], client, all_ok)
    lab_turn = client.bodies[3]["input"]
    out = [i for i in lab_turn if i.get("type") == "function_call_output"]
    assert json.loads(out[0]["output"])["samples"] == 2
    names = [t["name"] for t in client.bodies[2]["tools"]]
    assert names == ["box_summary", "run_metrics", "count_samples", "price_list", "submit_draft"]
    finance_turn = client.bodies[7]["input"]
    lab_request = json.loads(
        [i for i in finance_turn if i.get("type") == "function_call_output"][0]["output"]
    )
    assert lab_request["title"] == "Assay request"  # finance sees the verified lab draft


def test_spark_takes_over_when_wonder_fails(box):
    client = FakeClient(happy_turns(), fail_models={MUSE_WONDER_MODEL_ID})
    h = draft_handoffs(box, [], client, all_ok)
    assert h.orchestrator_model == MUSE_SPARK_MODEL_ID
    assert any(e.kind == "error" and MUSE_WONDER_MODEL_ID in e.text for e in h.log)
    assert h.status == "done"


def test_failed_check_gets_one_retry_with_the_failures(box):
    turns = [
        [call("route_box", {"routes": [
            {"area": "lab", "applies": False, "reason": "no sulfides"},
            {"area": "safety", "applies": True, "reason": "fair rock"},
            {"area": "plant", "applies": False, "reason": "-"},
            {"area": "finance", "applies": False, "reason": "-"}]})],  # fmt: skip
        [call("submit_draft", SAFETY)],
        [call("submit_draft", SAFETY)],
    ]
    verdicts = iter([False, True])

    def flaky(area, draft, box, prices, history=()):
        return [Check(name="figures", ok=next(verdicts), detail="run 1 rqd_pct is 56.7")]

    client = FakeClient(turns)
    h = draft_handoffs(box, [], client, flaky)
    assert h.drafts[0].verified and h.drafts[0].status == "ready"
    assert "run 1 rqd_pct is 56.7" in client.bodies[2]["input"][0]["content"][0]["text"]
    assert any(e.kind == "retry" for e in h.log)


def test_draft_failing_twice_is_rejected_and_cannot_be_approved(box):
    turns = [
        [call("route_box", {"routes": [
            {"area": "lab", "applies": True, "reason": "sulfides"},
            {"area": "safety", "applies": False, "reason": "-"},
            {"area": "plant", "applies": False, "reason": "-"},
            {"area": "finance", "applies": True, "reason": "lab applies"}]})],  # fmt: skip
        [call("submit_draft", LAB)],
        [call("submit_draft", LAB)],
    ]

    def never(area, draft, box, prices, history=()):
        return [Check(name="intervals", ok=False, detail="14.0 m is outside the box")]

    box.handoffs = draft_handoffs(box, [], FakeClient(turns), never)
    assert box.handoffs.drafts[0].status == "rejected"
    assert [d.area for d in box.handoffs.drafts] == ["lab"]  # nothing verified to price
    assert any(e.actor == "finance" and "skipped" in e.text for e in box.handoffs.log)
    with pytest.raises(ValueError, match="passed every check"):
        approve_draft(box, "lab")


def test_bad_tool_arguments_are_returned_to_the_model(box):
    turns = [
        [call("run_metrics", {"run": 9})],
        [call("route_box", ROUTES | {"routes": ROUTES["routes"][:1] + [
            {"area": a, "applies": False, "reason": "-"} for a in ("safety", "plant", "finance")
        ]})],  # fmt: skip
        [call("submit_draft", LAB)],
    ]
    client = FakeClient(turns)
    h = draft_handoffs(box, [], client, all_ok)
    out = [i for i in client.bodies[1]["input"] if i.get("type") == "function_call_output"]
    assert "does not exist" in json.loads(out[0]["output"])["error"]
    assert h.status == "done"


def test_approving_a_draft_sends_nothing(box):
    box.handoffs = draft_handoffs(box, [], FakeClient(happy_turns()), all_ok)
    slot = approve_draft(box, "safety")
    assert slot.status == "approved" and slot.approved_at
    assert "Not sent" in box.handoffs.log[-1].text


def test_neither_model_routes(box):
    client = FakeClient([], fail_models={MUSE_WONDER_MODEL_ID, MUSE_SPARK_MODEL_ID})
    h = draft_handoffs(box, [], client, all_ok)
    assert h.status == "failed" and "Neither" in h.error


def test_toolbox_numbers_come_from_geometry(box):
    t = Toolbox(box, [], load_prices())
    m = t.run_metrics(RunArg(run=2))
    assert (m["rqd_pct"], m["tcr_pct"], m["rock_quality_deere"]) == (56.7, 62.0, "fair")
    q = t.quote(QuoteArg(lines=[QuoteLine(code="PREP", samples=2),
                                QuoteLine(code="GOLD-MAGIC", samples=1)]))  # fmt: skip
    assert q["total_usd"] == 18.0 and q["unknown_codes"] == ["GOLD-MAGIC"]
    assert q["remaining_after_usd"] == 12000 - 18.0


def test_price_table_says_it_is_an_example():
    p = load_prices()
    assert p.example and "EXAMPLE" in p.notice


def test_agents_have_no_tool_that_acts():
    t = Toolbox(make_box(make_run(PIECES)), [], load_prices()).tools()
    assert not {n for n in t if any(w in n for w in ("send", "post", "write", "email"))}
    used = set(agents.ORCHESTRATOR_TOOLS) | {n for v in agents.AREA_TOOLS.values() for n in v}
    assert used <= set(t)
