"""Hole agent, orchestrator and area agents with a simulated Model API (no network)."""

import copy
import json
import threading

import pytest
from test_hole_view import box as hole_box
from test_hole_view import broken, sound
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
from coresight.schemas import Check, JudgeVerdict

NONE_FINDING = {"title": "Nothing along the hole", "body": "No trend reaches this box.",
                "trends": [], "action": "none", "action_reason": "Nothing to act on."}  # fmt: skip
ROUTES = {
    "routes": [
        {"area": "lab", "applies": True, "reason": "Run 2 shows sulfides.", "runs": [1]},
        {"area": "safety", "applies": True, "reason": "Run 2 is fair, RQD 56.7.", "runs": [1]},
        {"area": "plant", "applies": False, "reason": "No earlier box to compare."},
        {"area": "finance", "applies": True, "reason": "Lab applies."},
    ]
}
ONLY_SAFETY = {"routes": [
    {"area": "lab", "applies": False, "reason": "no sulfides"},
    {"area": "safety", "applies": True, "reason": "fair rock"},
    {"area": "plant", "applies": False, "reason": "-"},
    {"area": "finance", "applies": False, "reason": "-"}]}  # fmt: skip
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
BACKED = JudgeVerdict(claims=[{"claim": "Fair rock", "supported": True, "evidence": "run 2"}])
NOT_BACKED = JudgeVerdict(claims=[
    {"claim": "Fair rock", "supported": True, "evidence": "run 2"},
    {"claim": "Visible sulfides", "supported": False,
     "evidence": "the approved mineralization of every run is none visible"}])  # fmt: skip


def call(name, args, n=[0]):  # noqa: B006 - a counter for unique call ids
    n[0] += 1
    return {"type": "function_call", "name": name, "arguments": json.dumps(args),
            "call_id": f"call_{n[0]}"}  # fmt: skip


class FakeClient:
    """Answers each request with the next scripted turn and records what was asked."""

    def __init__(self, turns, fail_models=()):
        self.turns, self.fail_models, self.bodies = list(turns), set(fail_models), []

    def respond(self, body):
        self.bodies.append(copy.deepcopy(body))  # the agent's conversation keeps growing
        if body["model"] in self.fail_models:
            raise RuntimeError(f"{body['model']} 500: upstream error")
        return {"output": self.turns.pop(0)}


def all_ok(area, draft, box, prices, history=(), trends=()):
    return [Check(name="figures", ok=True)]


def ok_checks(*_):
    return [Check(name="trends", ok=True)]


class FakeJudge:
    """Scripted verdicts; records what it was asked to judge."""

    def __init__(self, *verdicts):
        self.verdicts, self.asked = list(verdicts), []

    def __call__(self, what, text, record, effort):
        self.asked.append((what, text, record))
        effort.turns += 1
        return self.verdicts.pop(0) if self.verdicts else BACKED


def run(box, client, verifier=all_ok, history=(), **kw):
    kw = {"judge": FakeJudge(), "finding_check": ok_checks, "routing_check": ok_checks,
          "workers": 1} | kw  # one at a time: the scripted turns come in order
    return draft_handoffs(box, list(history), client, verifier, **kw)


@pytest.fixture
def box():
    return make_box(make_run(PIECES, 10, 11), make_run(PIECES, 11, 12.5), status="approved")


def happy_turns():
    return [
        [call("hole_trends", {})],
        [call("submit_finding", NONE_FINDING)],
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


def test_hole_agent_then_wonder_routes_and_each_area_drafts_with_tools(box):
    client = FakeClient(happy_turns())
    saves = []
    h = run(box, client, save=lambda h: saves.append(h.status))

    assert h.status == "done" and h.orchestrator_model == MUSE_WONDER_MODEL_ID
    assert h.hole.status == "ready" and h.hole.finding.action == "none"
    assert h.routing_verified is True
    assert [d.area for d in h.drafts] == ["lab", "safety", "finance"]  # plant does not apply
    assert all(d.status == "ready" and d.verified for d in h.drafts)
    assert h.drafts[2].draft.total_usd == 54.0
    assert [b["model"] for b in client.bodies[:4]] == [MUSE_SPARK_MODEL_ID] * 2 + [
        MUSE_WONDER_MODEL_ID] * 2  # fmt: skip
    assert {b["model"] for b in client.bodies[4:]} == {MUSE_SPARK_MODEL_ID}
    texts = [e.text for e in h.log]
    assert "Read the box from geometry.py: 2 runs; the worst is run 2, RQD 56.7 %" in texts
    assert ("Read run 2 (11.00 to 12.50 m): RQD 56.7 %, recovery 62.0 %, "
            "1.3 fractures per metre, fair rock") in texts  # fmt: skip
    assert "Read the trends along the hole: none reaches this box" in texts
    assert not any("_pct" in t or "{" in t for t in texts)  # sentences, not field names
    assert any("Plant does not apply" in t for t in texts)
    assert len(saves) > 5  # the page sees progress while the agents work


def test_tool_results_go_back_to_the_model(box):
    client = FakeClient(happy_turns())
    run(box, client)
    lab_turn = client.bodies[5]["input"]
    out = [i for i in lab_turn if i.get("type") == "function_call_output"]
    assert json.loads(out[0]["output"])["samples"] == 2
    names = [t["name"] for t in client.bodies[4]["tools"]]
    assert names == ["box_summary", "run_metrics", "count_samples", "price_list", "submit_draft"]
    finance_turn = client.bodies[9]["input"]
    lab_request = json.loads(
        [i for i in finance_turn if i.get("type") == "function_call_output"][0]["output"]
    )
    assert lab_request["title"] == "Assay request"  # finance sees the verified lab draft


def test_each_agent_has_a_closed_tool_list(box):
    client = FakeClient(happy_turns())
    run(box, client)
    hole_tools = [t["name"] for t in client.bodies[0]["tools"]]
    orch_tools = [t["name"] for t in client.bodies[2]["tools"]]
    assert hole_tools == [*agents.HOLE_TOOLS, "submit_finding"]
    assert orch_tools == [*agents.ORCHESTRATOR_TOOLS, "route_box"]
    turns = [[call("send_email", {"to": "boss"})], [call("submit_finding", NONE_FINDING)],
             [call("route_box", ONLY_SAFETY)], [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    run(box, client)
    out = [i for i in client.bodies[1]["input"] if i.get("type") == "function_call_output"]
    assert json.loads(out[0]["output"]) == {"error": "unknown tool send_email"}


def test_the_orchestrator_prompt_holds_no_routing_rules():
    text = agents.ORCHESTRATOR.lower()
    for rule in ("rqd", "sulfide", "poor", "fractur", "recovery", "alteration", "only if"):
        assert rule not in text


def test_the_orchestrator_reads_the_verified_finding(box):
    finding = NONE_FINDING | {"title": "RQD drop", "action": "warn_geotech"}
    turns = [[call("submit_finding", finding)], [call("hole_finding", {})],
             [call("route_box", ONLY_SAFETY)], [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    h = run(box, client)
    out = [i for i in client.bodies[2]["input"] if i.get("type") == "function_call_output"]
    assert json.loads(out[0]["output"])["action"] == "warn_geotech"
    assert "Read the hole agent's finding: “RQD drop”" in [e.text for e in h.log]


def test_spark_takes_over_when_wonder_fails(box):
    client = FakeClient(happy_turns(), fail_models={MUSE_WONDER_MODEL_ID})
    h = run(box, client)
    assert h.orchestrator_model == MUSE_SPARK_MODEL_ID
    assert any(e.kind == "error" and MUSE_WONDER_MODEL_ID in e.text for e in h.log)
    assert h.status == "done"


def test_a_routing_the_check_refuses_goes_back_with_the_reason(box):
    verdicts = iter([False, True])

    def routing_check(routing, signals):
        ok = next(verdicts)
        return [Check(name="safety", ok=ok, detail="" if ok else "Safety must apply: RQD drop")]

    turns = [[call("submit_finding", NONE_FINDING)],
             [call("route_box", ROUTES | {"routes": [
                 r | {"applies": False} for r in ONLY_SAFETY["routes"]]})],
             [call("route_box", ONLY_SAFETY)], [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    h = run(box, client, routing_check=routing_check)
    second = client.bodies[2]["input"][0]["content"][0]["text"]
    assert "Safety must apply: RQD drop" in second and "refused" in second
    assert client.bodies[2]["model"] == MUSE_WONDER_MODEL_ID
    assert h.routing_verified and h.routing_effort.attempts == 2
    assert [d.area for d in h.drafts] == ["safety"]  # the drafts wait for a verified routing


def test_a_routing_refused_three_times_reaches_the_person_and_nobody_drafts(box):
    def never(routing, signals):
        return [Check(name="lab", ok=False, detail="Lab must apply: the box shows sulfides")]

    turns = [[call("submit_finding", NONE_FINDING)]] + [[call("route_box", ONLY_SAFETY)]] * 3
    h = run(box, FakeClient(turns), routing_check=never)
    assert h.status == "done" and h.routing_verified is False and h.drafts == []
    assert h.escalation.startswith("Routing needs review: 3 attempts failed.")
    assert "Lab must apply" in h.escalation
    assert any(e.kind == "escalate" for e in h.log)


def test_the_judge_runs_after_the_checks_pass_and_its_reasons_go_back(box):
    judge = FakeJudge(BACKED, NOT_BACKED, BACKED)  # the finding, then two drafts
    turns = [[call("submit_finding", NONE_FINDING)], [call("route_box", ONLY_SAFETY)],
             [call("submit_draft", SAFETY)], [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    h = run(box, client, judge=judge)
    (d,) = h.drafts
    assert d.status == "ready" and d.verified and d.judge == BACKED
    assert d.effort.attempts == 2
    retry = client.bodies[3]["input"][-1]["content"][0]["text"]
    assert "“Visible sulfides” is not backed by the record" in retry
    what, text, record = judge.asked[-1]
    assert what == "Safety & geotechnics draft" and "Fair rock" in text
    assert record["box"]["runs"][1]["mineralization"] == "none visible"
    texts = [e.text for e in h.log]
    assert any("1 of 2 claims backed by the approved record" in t for t in texts)


def test_the_judge_never_sees_what_verify_rejected(box):
    judge = FakeJudge()
    verdicts = iter([False, True])

    def flaky(area, draft, box, prices, history=(), trends=()):
        return [Check(name="figures", ok=next(verdicts), detail="Run 2 RQD is 56.7 %")]

    turns = [[call("submit_finding", NONE_FINDING)], [call("route_box", ONLY_SAFETY)],
             [call("submit_draft", SAFETY)], [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    h = run(box, client, verifier=flaky, judge=judge)
    assert [a[0] for a in judge.asked] == ["Hole finding", "Safety & geotechnics draft"]
    assert "Run 2 RQD is 56.7 %" in client.bodies[3]["input"][-1]["content"][0]["text"]
    assert h.drafts[0].verified and h.drafts[0].effort.attempts == 2


def test_a_draft_failing_three_times_reaches_the_person_marked_with_why(box):
    turns = [[call("submit_finding", NONE_FINDING)], [call("route_box", ONLY_SAFETY)]] + [
        [call("submit_draft", SAFETY)]] * 3  # fmt: skip
    judge = FakeJudge(BACKED, NOT_BACKED, NOT_BACKED, NOT_BACKED)  # finding, then 3 drafts
    box.handoffs = run(box, FakeClient(turns), judge=judge)
    (d,) = box.handoffs.drafts
    assert d.status == "needs_review" and not d.verified
    assert d.escalation.startswith("Needs review: 3 attempts failed.")
    assert "Visible sulfides" in d.escalation
    assert d.effort.attempts == 3 and d.effort.turns == 6  # 3 drafts and 3 verdicts
    assert [e.kind for e in box.handoffs.log].count("retry") == 2
    with pytest.raises(ValueError, match="failed verification three times"):
        approve_draft(box, "safety")
    slot = approve_draft(box, "safety", override=True)
    assert slot.status == "approved" and slot.approved_over_checks
    assert "although it failed verification" in box.handoffs.log[-1].text


def test_a_lab_draft_that_needs_review_leaves_finance_nothing_to_price(box):
    routes = {"routes": [
        {"area": "lab", "applies": True, "reason": "sulfides"},
        {"area": "safety", "applies": False, "reason": "-"},
        {"area": "plant", "applies": False, "reason": "-"},
        {"area": "finance", "applies": True, "reason": "lab applies"}]}  # fmt: skip

    def never(area, draft, box, prices, history=(), trends=()):
        return [Check(name="intervals", ok=False, detail="14.0 m is outside the box")]

    turns = [[call("submit_finding", NONE_FINDING)], [call("route_box", routes)]] + [
        [call("submit_draft", LAB)]] * 3  # fmt: skip
    box.handoffs = run(box, FakeClient(turns), verifier=never)
    assert box.handoffs.drafts[0].status == "needs_review"
    assert [d.area for d in box.handoffs.drafts] == ["lab"]
    assert any(e.actor == "finance" and "Skipped" in e.text for e in box.handoffs.log)


def test_the_log_says_turns_attempts_and_seconds_of_verification(box):
    h = run(box, FakeClient(happy_turns()))
    costs = [e.text for e in h.log if e.kind == "cost"]
    assert costs[0].startswith("Hole agent: 1 attempt, 3 model turns, ")  # 2 turns + judge
    assert costs[1].startswith("Routing: 1 attempt, 2 model turns, ")
    assert "s verifying (" in costs[1] and "s judge" not in costs[1]  # code only
    assert any(t.startswith("Lab agent: 1 attempt, 3 model turns") for t in costs)
    assert all("s judge" in t for t in costs if not t.startswith("Routing"))


def test_the_spark_judge_is_a_validated_submission(box):
    verdict = {"claims": [{"claim": "Fair rock", "supported": True, "evidence": "run 2"}]}
    turns = [[call("submit_finding", NONE_FINDING)], [call("submit_verdict", verdict)],
             [call("route_box", ONLY_SAFETY)], [call("submit_draft", SAFETY)],
             [call("submit_verdict", verdict)]]  # fmt: skip
    client = FakeClient(turns)
    h = draft_handoffs(box, [], client, all_ok, finding_check=ok_checks,
                       routing_check=ok_checks, workers=1)  # fmt: skip
    assert h.hole.verified and h.drafts[0].verified
    assert h.drafts[0].judge.claims[0].evidence == "run 2"
    judge_body = client.bodies[4]
    assert judge_body["model"] == MUSE_SPARK_MODEL_ID
    assert [t["name"] for t in judge_body["tools"]] == ["submit_verdict"]
    assert "Approved record" in judge_body["input"][0]["content"][0]["text"]


def test_bad_tool_arguments_are_returned_to_the_model(box):
    turns = [
        [call("submit_finding", NONE_FINDING)],
        [call("run_metrics", {"run": 9})],
        [call("route_box", ONLY_SAFETY)],
        [call("submit_draft", SAFETY)],
    ]
    client = FakeClient(turns)
    h = run(box, client)
    out = [i for i in client.bodies[2]["input"] if i.get("type") == "function_call_output"]
    assert "does not exist" in json.loads(out[0]["output"])["error"]
    assert h.status == "done"


def test_approving_a_draft_sends_nothing(box):
    box.handoffs = run(box, FakeClient(happy_turns()))
    slot = approve_draft(box, "safety")
    assert slot.status == "approved" and slot.approved_at and not slot.approved_over_checks
    assert "Not sent" in box.handoffs.log[-1].text


def test_neither_model_routes(box):
    client = FakeClient([], fail_models={MUSE_WONDER_MODEL_ID, MUSE_SPARK_MODEL_ID})
    h = run(box, client)
    assert h.hole.status == "failed"
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
    used = set(agents.ORCHESTRATOR_TOOLS) | set(agents.HOLE_TOOLS)
    used |= {n for v in agents.AREA_TOOLS.values() for n in v}
    assert used <= set(t)


# --- The demo: a box approved under a box of good rock --------------------------


def test_a_poor_box_below_a_good_one_gives_a_trend_alert_verified_in_two_layers():
    """The real trends and the real milestone checks; only the models are scripted."""
    from coresight.verify import verify

    top = hole_box(1, [sound(0, 1.5), sound(1.5, 3)], hole_id="DDH-9")
    here = hole_box(2, [broken(3, 4), broken(4, 5.5)], hole_id="DDH-9")
    trends = Toolbox(here, [top], load_prices()).trends
    assert [t.kind for t in trends] == ["rqd_drop", "weak_zone"]
    finding = {
        "title": "Ground gets worse below 3.00 m",
        "body": "RQD falls from 100.0 % in box 1 to 0.0 % in box 2; poor rock from 3.00 to "
                "5.50 m. A possible fault zone.",
        "trends": ["rqd_drop", "weak_zone"],
        "action": "warn_geotech",
        "action_reason": "The next run may enter the same zone.",
    }  # fmt: skip
    routes = {"routes": [
        {"area": "lab", "applies": False, "reason": "No mineralization."},
        {"area": "safety", "applies": True, "reason": "RQD drop and weak zone from 3.00 m."},
        {"area": "plant", "applies": False, "reason": "Same rock, no sulfides."},
        {"area": "finance", "applies": False, "reason": "No lab request."}]}  # fmt: skip
    alert = {
        "title": "Weak zone from 3.00 m, warn before the next run",
        "body": "Run 1 and run 2 are very poor rock, RQD 0.0 %. RQD falls from 100.0 % in "
                "box 1. Poor rock from 3.00 to 5.50 m. Check support before drilling on.",
        "priority": "high",
        "intervals": [{"from_m": 3.0, "to_m": 5.5}],
        "figures": [{"run": 1, "metric": "rqd_pct", "value": 0.0}],
    }  # fmt: skip
    turns = [[call("hole_trends", {})], [call("submit_finding", finding)],
             [call("hole_finding", {}), call("hole_trends", {})], [call("route_box", routes)],
             [call("submit_draft", alert)]]  # fmt: skip
    judge = FakeJudge()
    h = draft_handoffs(here, [top], FakeClient(turns), verify, judge=judge)
    assert h.hole.verified and h.hole.finding.action == "warn_geotech"
    assert all(c.ok for c in h.hole.checks)
    assert h.routing_verified and all(c.ok for c in h.routing_checks)
    (d,) = h.drafts
    assert d.area == "safety" and d.verified and d.status == "ready", d.checks
    assert all(c.ok for c in d.checks) and d.judge.ok
    assert [a[0] for a in judge.asked] == ["Hole finding", "Safety & geotechnics draft"]
    assert judge.asked[1][2]["hole_agent_finding"]["action"] == "warn_geotech"


class RoleClient:
    """Scripted turns per agent, told apart by its role prompt: safe when agents run at once."""

    def __init__(self, turns, meet=()):
        self.turns = {who: list(t) for who, t in turns.items()}
        self.bodies: dict[str, list] = {who: [] for who in turns}
        barrier = threading.Barrier(len(meet), timeout=5) if meet else None
        self.meet = {who: barrier for who in meet}

    def respond(self, body):
        first = body["input"][0]["content"][0]["text"]
        roles = {"hole": agents.HOLE_ROLE, "orchestrator": agents.ORCHESTRATOR,
                 **agents.AREA_ROLES}  # fmt: skip
        who = next(w for w, role in roles.items() if role in first)
        if who in self.meet and not self.bodies[who]:
            self.meet[who].wait()  # only passes when the other agent is drafting too
        self.bodies[who].append(copy.deepcopy(body))
        return {"output": self.turns[who].pop(0)}


def test_lab_safety_and_plant_draft_at_the_same_time_and_finance_waits_for_lab(box):
    routes = {"routes": [
        {"area": "lab", "applies": True, "reason": "sulfides"},
        {"area": "safety", "applies": True, "reason": "fair rock"},
        {"area": "plant", "applies": False, "reason": "-"},
        {"area": "finance", "applies": True, "reason": "lab applies"}]}  # fmt: skip
    client = RoleClient({
        "hole": [[call("submit_finding", NONE_FINDING)]],
        "orchestrator": [[call("route_box", routes)]],
        "lab": [[call("submit_draft", LAB)]],
        "safety": [[call("submit_draft", SAFETY)]],
        "finance": [[call("lab_request", {})], [call("submit_draft", FINANCE)]],
    }, meet=("lab", "safety"))  # fmt: skip
    h = run(box, client, workers=4)
    assert h.status == "done"
    assert [(d.area, d.status) for d in h.drafts] == [
        ("lab", "ready"), ("safety", "ready"), ("finance", "ready")]
    lab_read = json.loads(client.bodies["finance"][1]["input"][-1]["output"])
    assert lab_read["title"] == "Assay request"  # finance priced the verified lab request


def test_the_routing_starts_while_the_judge_reads_and_is_dropped_if_the_judge_refuses(box):
    second = NONE_FINDING | {"title": "Nothing along the hole, checked again"}
    judge = FakeJudge(NOT_BACKED, BACKED)  # the first finding is refused, the second passes
    client = RoleClient({
        "hole": [[call("submit_finding", NONE_FINDING)], [call("submit_finding", second)]],
        "orchestrator": [[call("hole_finding", {})], [call("route_box", ONLY_SAFETY)],
                         [call("hole_finding", {})], [call("route_box", ONLY_SAFETY)]],
        "safety": [[call("submit_draft", SAFETY)]],
    })  # fmt: skip
    h = run(box, client, judge=judge, workers=4)
    assert h.hole.verified and h.hole.finding.title == second["title"]
    assert h.routing_verified and h.drafts[0].status == "ready"
    read = [json.loads(b["input"][-1]["output"])["title"] for b in client.bodies["orchestrator"]
            if b["input"][-1].get("type") == "function_call_output"]  # fmt: skip
    assert read == [NONE_FINDING["title"], second["title"]]  # two early routings, one kept
    kinds = [e.kind for e in h.log]
    assert kinds.count("drop") == 1
    assert [e.at for e in h.log] == sorted(e.at for e in h.log)
    assert sum(e.kind == "route" for e in h.log) == 4  # only the kept routing's four areas


def test_a_retry_continues_the_conversation_and_does_not_read_the_tools_again(box):
    turns = [[call("submit_finding", NONE_FINDING)], [call("route_box", ONLY_SAFETY)],
             [call("run_metrics", {"run": 2})], [call("submit_draft", SAFETY)],
             [call("submit_draft", SAFETY)]]  # fmt: skip
    client = FakeClient(turns)
    h = run(box, client, judge=FakeJudge(BACKED, NOT_BACKED, BACKED))
    assert h.drafts[0].verified and h.drafts[0].effort.turns == 5  # 3 writing, 2 verdicts
    retry = client.bodies[4]["input"]
    assert retry[0] == client.bodies[2]["input"][0]  # the same role prompt, sent once
    assert any(i.get("type") == "function_call_output" and "rqd_pct" in i["output"]
               for i in retry)  # the run it read on attempt 1 is still there
    assert retry[-1]["content"][0]["text"].startswith("Your previous attempt failed")


def test_each_agent_gets_its_no_argument_tools_in_the_first_message(box):
    client = FakeClient([[call("submit_finding", NONE_FINDING)], [call("route_box", ONLY_SAFETY)],
                         [call("submit_draft", SAFETY)]])  # fmt: skip
    h = run(box, client)
    first = [b["input"][0]["content"][0]["text"] for b in client.bodies]
    assert "hole_trends: {" in first[0] and "box_summary: {" in first[0]
    assert "hole_finding: {" in first[1]  # the orchestrator reads the verified finding
    assert "run_metrics:" not in first[2]  # a tool with arguments is still called on demand
    assert any(e.actor == "safety" and e.kind == "tool" and "Read the box" in e.text
               for e in h.log)  # the log says what each agent was given
    assert h.drafts[0].effort.turns == 2  # one draft, one verdict: no turn spent reading
