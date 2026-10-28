"""Trends between boxes of a hole (point E): found by code, read by the hole agent."""

import pytest
from test_hole_view import box, broken, sound

from coresight import hole
from coresight.schemas import Anomaly, AnomalyType


def described(run, lithology, mineralization="none visible", alteration="none visible"):
    run.description = run.description.model_copy(
        update={"lithology": lithology, "mineralization": mineralization,
                "alteration": alteration}  # fmt: skip
    )
    return run


def kinds(trends):
    return [t.kind for t in trends]


def test_rqd_drop_from_the_box_above_and_the_weak_zone_it_starts():
    top = box(1, [sound(0, 2), sound(2, 3)])
    here = box(2, [broken(3, 4), broken(4, 6)])
    trends = hole.hole_trends([top], here)
    assert kinds(trends) == ["rqd_drop", "weak_zone"]
    drop, zone = trends
    assert (drop.rqd_before_pct, drop.rqd_after_pct) == (100.0, 0.0)
    assert drop.boxes == [1, 2] and (drop.from_m, drop.to_m) == (0, 6)
    assert drop.summary == (
        "RQD falls from 100.0 % in box 1 (0.00 to 3.00 m) to 0.0 % in box 2 (3.00 to 6.00 m)"
    )
    assert (zone.from_m, zone.to_m, zone.rqd_pct, zone.boxes) == (3, 6, 0.0, [2])
    assert zone.summary.startswith("Poor rock from 3.00 to 6.00 m (box 2): RQD 0.0 %")


def test_a_small_drop_is_not_a_trend():
    top = box(1, [sound(0, 2)])
    here = box(2, [make_fair(2, 4)])
    assert hole.hole_trends([top], here) == []


def make_fair(from_m, to_m):
    # 30 cm intact, then 5 cm pieces: RQD 90 over a 1 m run, repeated
    from test_review import make_run

    pieces, pos = [], 0.0
    while pos < (to_m - from_m) * 100 - 1:
        pieces += [(0, pos, pos + 90, "natural"), (0, pos + 90, pos + 100, "natural")]
        pos += 100
    return make_run(pieces, from_m, to_m)


def test_box_rqd_uses_geometry_for_all_runs_together():
    b = box(1, [sound(0, 1), broken(1, 4)])
    assert hole.box_rqd(b) == pytest.approx(25.0)


def test_weak_zone_across_two_boxes_names_both():
    top = box(1, [sound(0, 2), broken(2, 4)])
    here = box(2, [broken(4, 6), sound(6, 8)])
    zone = [t for t in hole.hole_trends([top], here) if t.kind == "weak_zone"]
    assert len(zone) == 1 and zone[0].boxes == [1, 2]
    assert "(boxes 1 and 2)" in zone[0].summary


def test_a_weak_zone_far_above_the_box_is_not_its_trend():
    top = box(1, [broken(0, 3), sound(3, 6)])
    here = box(2, [sound(6, 8)])
    assert "weak_zone" not in kinds(hole.hole_trends([top], here))


def test_rock_change_at_the_contact_with_the_box_above():
    top = box(1, [described(sound(0, 2), "Pale non-welded tuff with pumice"),
                  described(sound(2, 3), "Pinkish granite to rhyolite")])  # fmt: skip
    here = box(2, [described(sound(3, 5), "Reddish sandstone, poorly sorted")])
    (t,) = hole.hole_trends([top], here)
    assert (t.kind, t.before, t.after) == ("lithology_change", "granite", "sandstone")
    assert t.summary == (
        "Rock changes from granite at the bottom of box 1 (0.00 to 3.00 m) to sandstone "
        "at the top of box 2 (3.00 to 5.00 m)"
    )


@pytest.mark.parametrize(
    "text,rock",
    [
        ("Foliated granitic to migmatitic gneiss", "gneiss"),  # granitic is not granite
        ("Mafic gneiss - amphibolite", "gneiss"),  # the first rock named
        ("Lapilli tuffs", "tuff"),
        ("Dark fine-grained rock", None),
        (None, None),
    ],
)
def test_rock_name_is_the_first_whole_rock_word(text, rock):
    assert hole.rock_name(text) == rock


def test_same_rock_in_other_words_is_no_change():
    top = box(1, [described(sound(0, 2), "Foliated granitic to migmatitic gneiss")])
    here = box(2, [described(sound(2, 4), "Migmatitic veined mica gneiss")])
    assert hole.hole_trends([top], here) == []


def test_sulfides_appear_and_end():
    top = box(1, [described(sound(0, 2), "andesite")])
    here = box(2, [described(sound(2, 4), "andesite", "disseminated pyrite, 2 %")])
    (t,) = hole.hole_trends([top], here)
    assert (t.kind, t.before, t.after) == ("sulfides_appear", "none", "sulfides")
    (t,) = hole.hole_trends([here], box(3, [described(sound(4, 6), "andesite")]))
    assert t.kind == "sulfides_gone"


@pytest.mark.parametrize(
    "mineralization,anomaly,expected",
    [
        ("none visible", None, False),
        ("no visible sulfides", None, False),
        ("Without pyrite; minor calcite", None, False),
        ("calcite veinlets, trace chalcopyrite", None, True),
        ("none visible", AnomalyType.VISIBLE_SULFIDES, True),
    ],
)
def test_sulfides_are_read_without_their_negations(mineralization, anomaly, expected):
    run = described(sound(0, 1), "andesite", mineralization)
    if anomaly:
        run.description.anomalies = [Anomaly(type=anomaly, explanation="seen")]
    assert hole.has_sulfides(run) is expected


def test_first_box_has_only_its_own_zones():
    here = box(1, [broken(0, 3)])
    assert kinds(hole.hole_trends([], here)) == ["weak_zone"]


def test_boxes_not_approved_and_the_box_itself_are_left_out():
    pending = box(1, [sound(0, 3)], status="ready")
    here = box(2, [broken(3, 6)])
    assert kinds(hole.hole_trends([pending, here], here)) == ["weak_zone"]


def test_routing_signals_from_the_box_and_its_trends():
    top = box(1, [sound(0, 3)])
    run = described(broken(3, 5), "andesite", "none visible", "moderate sericite")
    here = box(2, [run, sound(5, 6)])
    trends = hole.hole_trends([top], here)
    s = hole.routing_signals([top], here, trends)
    assert (s.min_rqd_pct, s.sulfides, s.lab_evidence, s.earlier_boxes) == (0.0, False, True, 1)
    assert s.min_tcr_pct == 100.0 and s.trends == trends


def test_no_alteration_or_mineralization_is_no_lab_evidence():
    here = box(1, [sound(0, 2)])
    s = hole.routing_signals([], here, [])
    assert not s.lab_evidence and not s.sulfides and s.earlier_boxes == 0
