"""Verification at the milestones (point E): the spec the new parts of verify.py are built to.

Agents 102: verify at milestones, not only at the end. Before any area agent writes,
two milestones are checked by code:

1. The hole agent's finding (check_finding). The hole agent reads the trends that code
   found between boxes (hole.hole_trends) and proposes one action. Its finding passes
   three checks, always these three, in this order:
   - "trends": every trend kind it cites is one hole_trends returned.
   - "action": "oriented_core" and "warn_geotech" need a cited "rqd_drop" or
     "weak_zone"; "sample_contact" needs a cited "lithology_change", "sulfides_appear"
     or "sulfides_gone"; "none" is always allowed. With no trends at all, only "none".
   - "numbers": every number in the title and body comes from a tool: the runs of this
     box and of earlier boxes (as verify's numbers check), run numbers from 1, box numbers
     (this box, earlier boxes and the trends' boxes), and every number of the trends
     (from_m, to_m, rqd_before_pct, rqd_after_pct, rqd_pct, min_rqd_pct). The detail
     lists the numbers no tool gave, as verify's numbers check does.
   Failed details are sentences without field names: trend kinds read as
   "an RQD drop", "a weak zone", "a change of rock", "sulfides appearing", "sulfides ending".

2. The orchestrator's routing (check_routing), against what code knows about the box
   (RoutingSignals, from hole.routing_signals). One check per area, named by the area,
   in the order lab, safety, plant, finance. The orchestrator decides everything the
   rules leave open; the rules only refuse what contradicts the record:
   - safety must apply if the worst run is very poor (min_rqd_pct < 25) or a trend of
     kind "rqd_drop" or "weak_zone" reaches the box. It cannot apply if the worst run has
     RQD >= 75 and recovery >= 75 and no such trend.
   - lab must apply if the box shows sulfides. It cannot apply without lab evidence.
   - plant must apply if sulfides appear or end ("sulfides_appear", "sulfides_gone").
     It cannot apply with no "lithology_change", no sulfide trend and no sulfides.
   - finance applies exactly when lab applies (it only prices the lab request).
   - an area without a route fails: "<Area> has no route".
   Details: "<Area> must apply: <why>" or "<Area> cannot apply: <why>", the area
   capitalised (Lab, Safety, Plant, Finance), reasons joined with "; ".

verify() also takes the trends, so a draft that quotes them is traceable.
Box DDH-1, box 3: run 1 is 10-11 m (RQD 85.0, TCR 93.0), run 2 is 11-12.5 m (RQD 56.7,
TCR 62.0).
"""

import pytest
from test_review import PIECES, make_box, make_run

from coresight.agents import load_prices
from coresight.schemas import (
    AreaRoute,
    Draft,
    HoleFinding,
    HoleTrend,
    Routing,
    RoutingSignals,
)
from coresight.verify import check_finding, check_routing, verify

DROP = HoleTrend(
    kind="rqd_drop", from_m=6.0, to_m=12.5, boxes=[2, 3],
    summary="RQD falls from 92.4 % in box 2 (6.00 to 10.00 m) to 69.3 % in box 3 "
            "(10.00 to 12.50 m)",
    rqd_before_pct=92.4, rqd_after_pct=69.3,
)  # fmt: skip
ZONE = HoleTrend(
    kind="weak_zone", from_m=11.0, to_m=13.0, boxes=[3, 4],
    summary="Poor rock from 11.00 to 13.00 m (boxes 3 and 4): RQD 41.2 % together, "
            "33.8 % in the worst interval",
    rqd_pct=41.2, min_rqd_pct=33.8,
)  # fmt: skip
ROCK = HoleTrend(
    kind="lithology_change", from_m=9.0, to_m=11.0, boxes=[2, 3],
    summary="Rock changes from granite at the bottom of box 2 (6.00 to 10.00 m) to "
            "andesite at the top of box 3 (10.00 to 12.50 m)",
    before="granite", after="andesite",
)  # fmt: skip
PYRITE = HoleTrend(
    kind="sulfides_appear", from_m=6.0, to_m=12.5, boxes=[2, 3],
    summary="Sulfides appear in box 3 (10.00 to 12.50 m); box 2 (6.00 to 10.00 m) showed none",
    before="none", after="sulfides",
)  # fmt: skip
AREAS = ["lab", "safety", "plant", "finance"]


@pytest.fixture
def box():
    return make_box(make_run(PIECES, 10, 11), make_run(PIECES, 11, 12.5))


def finding(action="warn_geotech", trends=("rqd_drop",), body=None, title="RQD drop"):
    return HoleFinding(
        title=title,
        body=body or "RQD falls from 92.4 % in box 2 to 69.3 % in box 3, run 2 at 56.7 %.",
        trends=list(trends),
        action=action,
        action_reason="Ground gets worse downhole.",
    )


def named(checks, names):
    assert [c.name for c in checks] == names
    return {c.name: c for c in checks}


# --- 1. The hole agent's finding ---------------------------------------------


def test_a_finding_that_cites_found_trends_passes(box):
    c = named(check_finding(finding(), [DROP], box, []), ["trends", "action", "numbers"])
    assert all(x.ok for x in c.values()), c


def test_citing_a_trend_code_did_not_find_fails(box):
    c = named(check_finding(finding(trends=["rqd_drop", "weak_zone"]), [DROP], box, []),
              ["trends", "action", "numbers"])  # fmt: skip
    assert not c["trends"].ok and "a weak zone" in c["trends"].detail
    assert "weak_zone" not in c["trends"].detail


@pytest.mark.parametrize(
    "action,cited,trends,ok",
    [
        ("oriented_core", ["weak_zone"], [ZONE], True),
        ("warn_geotech", ["rqd_drop"], [DROP], True),
        ("warn_geotech", ["lithology_change"], [ROCK], False),
        ("sample_contact", ["lithology_change"], [ROCK], True),
        ("sample_contact", ["sulfides_appear"], [PYRITE], True),
        ("sample_contact", ["rqd_drop"], [DROP], False),
        ("oriented_core", [], [DROP], False),  # the trend must be cited
        ("none", ["rqd_drop"], [DROP], True),
        ("none", [], [], True),
        ("warn_geotech", [], [], False),  # no trends: only "none"
    ],
)
def test_the_action_needs_a_cited_trend_that_supports_it(box, action, cited, trends, ok):
    f = finding(action=action, trends=cited, body="See the hole log.")
    c = named(check_finding(f, trends, box, []), ["trends", "action", "numbers"])
    assert c["action"].ok is ok
    if not ok:
        assert c["action"].detail and "_" not in c["action"].detail


def test_numbers_in_a_finding_come_from_the_trends_or_the_runs(box):
    body = ("Poor rock from 11.00 to 13.00 m in boxes 3 and 4: RQD 41.2 % together, "
            "33.8 % at worst; run 1 has RQD 85.0 %.")  # fmt: skip
    f = finding(action="oriented_core", trends=["weak_zone"], body=body)
    assert all(x.ok for x in check_finding(f, [ZONE], box, []))
    bad = finding(action="oriented_core", trends=["weak_zone"], body="RQD 12.5 % then 41.2 %")
    c = named(check_finding(bad, [ZONE], box, []), ["trends", "action", "numbers"])
    assert not c["numbers"].ok
    assert "12.5" in c["numbers"].detail and "41.2" not in c["numbers"].detail


def test_numbers_of_earlier_boxes_are_traceable_in_a_finding(box):
    earlier = make_box(make_run(PIECES, 6, 7))
    earlier.box_number = 2
    f = finding(action="none", trends=[], body="Box 2 at 6.0 m had RQD 85.0 %.")
    assert all(x.ok for x in check_finding(f, [], box, [earlier]))


# --- 2. The orchestrator's routing ---------------------------------------------


def signals(**kw):
    base = dict(min_rqd_pct=56.7, min_tcr_pct=62.0, sulfides=False, lab_evidence=True,
                earlier_boxes=1, trends=[])  # fmt: skip
    return RoutingSignals(**(base | kw))


def routing(*applies, skip=()):
    return Routing(routes=[
        AreaRoute(area=a, applies=a in applies, reason="read the box")
        for a in AREAS if a not in skip
    ])  # fmt: skip


def test_open_choices_are_left_to_the_orchestrator():
    # fair rock, alteration, no trend: every area is the orchestrator's call
    for applies in [(), ("safety",), ("lab", "finance"), ("safety", "lab", "finance")]:
        checks = check_routing(routing(*applies), signals())
        assert [c.name for c in checks] == AREAS
        assert all(c.ok for c in checks), (applies, checks)


def test_safety_must_apply_on_very_poor_rock():
    c = named(check_routing(routing(), signals(min_rqd_pct=12.0)), AREAS)
    assert not c["safety"].ok
    assert c["safety"].detail == "Safety must apply: the worst run is very poor rock (RQD 12.0 %)"


def test_safety_must_apply_when_a_drop_or_weak_zone_reaches_the_box():
    c = named(check_routing(routing(), signals(trends=[DROP, ZONE])), AREAS)
    assert c["safety"].detail == f"Safety must apply: {DROP.summary}; {ZONE.summary}"
    assert check_routing(routing("safety"), signals(trends=[DROP, ZONE]))[1].ok


def test_safety_cannot_apply_on_good_rock_with_no_trend():
    s = signals(min_rqd_pct=92.3, min_tcr_pct=98.1)
    c = named(check_routing(routing("safety"), s), AREAS)
    assert c["safety"].detail == (
        "Safety cannot apply: the worst run has RQD 92.3 % and recovery 98.1 %, and no "
        "drop or weak zone reaches the box"
    )
    assert check_routing(routing("safety"), signals(min_rqd_pct=92.3, min_tcr_pct=60.0))[1].ok


def test_lab_must_apply_on_sulfides_and_cannot_without_evidence():
    c = named(check_routing(routing(), signals(sulfides=True)), AREAS)
    assert c["lab"].detail == "Lab must apply: the approved description shows sulfides"
    c = named(check_routing(routing("lab", "finance"), signals(lab_evidence=False)), AREAS)
    assert c["lab"].detail == (
        "Lab cannot apply: the approved description shows no mineralization, alteration or veins"
    )


def test_plant_follows_changes_along_the_hole():
    c = named(check_routing(routing(), signals(trends=[PYRITE], sulfides=True)), AREAS)
    assert c["plant"].detail == f"Plant must apply: {PYRITE.summary}"
    c = named(check_routing(routing("plant"), signals()), AREAS)
    assert c["plant"].detail == (
        "Plant cannot apply: no change of rock or sulfides along the hole, and no sulfides "
        "in the box"
    )
    assert check_routing(routing("plant"), signals(trends=[ROCK]))[2].ok  # allowed
    assert check_routing(routing(), signals(trends=[ROCK]))[2].ok  # not required


def test_finance_applies_exactly_when_lab_does():
    c = named(check_routing(routing("lab"), signals()), AREAS)
    assert c["finance"].detail == "Finance must apply: lab applies, and finance prices its request"
    c = named(check_routing(routing("finance"), signals()), AREAS)
    assert c["finance"].detail == (
        "Finance cannot apply: lab does not apply, so there is no request to price"
    )


def test_an_area_left_out_fails():
    c = named(check_routing(routing("safety", skip=("plant",)), signals()), AREAS)
    assert not c["plant"].ok and c["plant"].detail == "Plant has no route"


# --- verify() with the trends -------------------------------------------------


def test_a_draft_quoting_the_trends_is_traceable(box):
    d = Draft(title="Ground alert", body="RQD falls from 92.4 % in box 2 to 69.3 % in box 3; "
              "poor rock from 11.00 to 13.00 m, RQD 41.2 %, 33.8 % at worst.")  # fmt: skip
    numbers = {c.name: c for c in verify("safety", d, box, load_prices(), [], [DROP, ZONE])}
    assert numbers["numbers"].ok, numbers["numbers"].detail
    without = {c.name: c for c in verify("safety", d, box, load_prices(), [])}
    assert not without["numbers"].ok
