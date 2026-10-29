"""A draft proposes, it never decides for the operation (point 7): the spec check_role is built to.

Agents 102: the person signs. A safety draft once said "Do not continue drilling until
the safety team reviews." and the judge passed it. Stopping a rig is an expensive call
that the shift boss and the geotechnical engineer make, not a draft. So:

- What a draft or the hole agent proposes comes from a closed list (the Pydantic
  literals DraftAction and HoleAction). There is no "stop drilling" in it.
- check_role(text) is a deterministic check of the words. It returns one Check named
  "role". It fails when the text tells the operation to stop, hold, or not go on:
  1. a stop verb (stop, halt, suspend, pause, cease, freeze, shut down, stand down,
     hold off) applied to the work: followed within four words by an operation word
     (drill, drilling, rig, work, works, operation, operations, production, advance,
     or the phrase "the next run"), or used as a command (at the start of the text or
     of a sentence, or right after a colon or a semicolon), as in "Stop and get geotech
     review";
  2. a working subject (drill, drilling, rig, work, works, operation, operations,
     production; not "the next run") followed within four words by a stop verb or by
     wait, waits, hold, holds ("drilling must stop", "drilling should wait for
     clearance");
  3. a negation (do not, don't, must not, should not, cannot, can't, no further, not
     to) followed within three words by a verb of going on (drill, drilling, continue,
     proceed, advance, resume, start) ("Do not drill ahead", "no further drilling").
     "does not" and "did not" describe the rock or the hole and are not negations here
     ("the run does not continue into box 4");
  4. an operation word, then later in the same sentence "until", then within six words
     a clearance word (clears, cleared, clearance, approves, approval, signs off,
     sign-off, released): "advance only until geotechnics signs off".
  Matching ignores case and works on whole words; the apostrophe may be ' or ’. The
  -s forms of the verbs count (stops, halts, shuts down, holds off); past forms do not
  ("drilling stopped at 8.02 m" is a fact about the hole, not an order). Sentences end
  at ".", "!" or "?" followed by any white space (a space, a tab, a line break) or the
  end of the text, and at every line break. A match never crosses the end of a
  sentence, under any of the four rules, and rule 4 tries every "until" after the
  operation word in its sentence. When deciding whether a stop verb starts a sentence
  or follows a colon or semicolon, white space, opening quotes or brackets and list
  marks ("-", "*", "•", "1.") in between are skipped.
- Text that only describes the rock, recommends a check, a review or a warning passes:
  "Check support before the next run", "Geotechnics should review the box before the
  next run", "the fracturing stops at 7.6 m", "the hole was drilled to 8.02 m".
- The detail of a failed check is one sentence for the agent that reads it as feedback,
  without field names: it quotes the words that matched (as the text wrote them, the
  first match), and says the draft only proposes, naming the allowed actions:
  'The draft tells the operation to stop ("Do not continue drilling"). A draft only
  proposes: check support, scale and inspect, review before the next run, warn
  geotechnics, ask for oriented core, sample the contact, send to the lab or ask the
  plant for a test. People in charge decide whether work stops.'
  The quote runs from the first word of the match to its last word, as written: rule 1
  ends at the operation word when there is one within four words and is the stop verb
  alone otherwise ("Hold off the next run", "stop"); rule 2 runs from the subject to
  the verb, rule 3 from the negation to the verb, rule 4 from the operation word to the
  clearance word. When several matches exist, the one that starts first in the text is
  quoted.
- verify() runs check_role as a fifth check, after the four it has, on the title and
  on the body; check_finding runs it as a fourth check on the title, the body and the
  action_reason. Each field is checked on its own, so a match never runs from one field
  into the next and the body starts a sentence; the check is the first field's that
  fails, in that order, or a passing check.
"""

import pytest
from test_review import PIECES, make_box, make_run

from coresight.agents import load_prices
from coresight.schemas import Draft, HoleFinding, Interval
from coresight.verify import check_finding, check_role, verify

DETAIL_TAIL = (". A draft only proposes: check support, scale and inspect, review before "
               "the next run, warn geotechnics, ask for oriented core, sample the contact, "
               "send to the lab or ask the plant for a test. People in charge decide "
               "whether work stops.")  # fmt: skip


def detail(quote: str) -> str:
    return f'The draft tells the operation to stop ("{quote}"){DETAIL_TAIL}'


@pytest.mark.parametrize("text, quote", [
    ("Do not continue drilling until the safety team reviews.", "Do not continue"),
    ("Before the next run: stop and get geotech review.", "stop"),
    ("Do not drill ahead without clearance.", "Do not drill"),
    ("Stop drilling at 8.02 m.", "Stop drilling"),
    ("We recommend that drilling must stop here.", "drilling must stop"),
    ("Drilling should wait for clearance.", "Drilling should wait"),
    ("Halt the rig until geotech reviews.", "Halt the rig"),
    ("Suspend operations in this zone.", "Suspend operations"),
    ("No further drilling in this hole.", "No further drilling"),
    ("The crew should not proceed.", "should not proceed"),
    ("Pause work; get a geotechnical review.", "Pause work"),
    ("Hold off the next run.", "Hold off the next run"),
    ("Production stops until the area is checked.", "Production stops"),
    ("RQD is 16.2 %; shut down the drill.", "shut down the drill"),
    ("Advance only until geotechnics signs off.", "Advance only until geotechnics signs off"),
    ("Don't resume until it is checked.", "Don't resume"),
])  # fmt: skip
def test_text_that_stops_the_operation_fails_and_quotes_it(text, quote):
    c = check_role(text)
    assert c.name == "role" and not c.ok
    assert c.detail == detail(quote)


@pytest.mark.parametrize("text", [
    "Check support before the next run.",
    "Geotechnics should review the box before the next run.",
    "Warn geotechnics: RQD falls from 32.8 % to 16.2 %.",
    "The intense fracturing stops at 7.6 m.",
    "Drilling stopped at 8.02 m, the end of the hole.",
    "The hole was drilled to 8.02 m with good recovery.",
    "Ask for oriented core in the next runs.",
    "Scale loose ground and inspect the walls for fallout.",
    "Sample across the contact at 6.1 m.",
    "Continue logging the next box as usual.",
    "Do not mix the samples of runs 1 and 2.",
    "The run does not continue into box 4.",
])  # fmt: skip
def test_text_that_only_proposes_passes(text):
    c = check_role(text)
    assert c.name == "role" and c.ok and c.detail == ""


def test_the_first_match_is_quoted_as_written():
    c = check_role("Run 2 is poor. STOP DRILLING now. Also do not continue.")
    assert c.detail == detail("STOP DRILLING")


def test_an_empty_text_passes():
    assert check_role("").ok


# --- Wired into the two checks the agents already pass --------------------------


@pytest.fixture
def box():
    return make_box(make_run(PIECES, 10, 11), make_run(PIECES, 11, 12.5))


def test_verify_runs_the_role_check_fifth_on_title_and_body(box):
    ok = Draft(title="Ground alert", body="Check support before the next run.",
               intervals=[Interval(from_m=11.0, to_m=12.5)])  # fmt: skip
    checks = verify("safety", ok, box, load_prices())
    assert [c.name for c in checks] == ["intervals", "figures", "numbers", "prices", "role"]
    assert checks[-1].ok
    bad = ok.model_copy(update={"title": "Stop drilling"})
    assert not verify("safety", bad, box, load_prices())[-1].ok
    bad = ok.model_copy(update={"body": "Do not drill ahead."})
    assert verify("safety", bad, box, load_prices())[-1].detail == detail("Do not drill")


def test_check_finding_runs_the_role_check_fourth_on_its_words(box):
    f = HoleFinding(title="Nothing along the hole", body="No trend reaches this box.",
                    trends=[], action="none", action_reason="Nothing to act on.")  # fmt: skip
    checks = check_finding(f, [], box, [])
    assert [c.name for c in checks] == ["trends", "action", "numbers", "role"]
    assert checks[-1].ok
    bad = f.model_copy(update={"action_reason": "Halt the rig until geotech reviews."})
    assert check_finding(bad, [], box, [])[-1].detail == detail("Halt the rig")


# --- From the read-only review of round 1 -----------------------------------------


@pytest.mark.parametrize("text, quote", [
    ("RQD is poor.\nStop and await review.", "Stop"),
    ("RQD is poor\n- Stop drilling at the contact", "Stop drilling"),
    ('Before the next run: "stop and get geotech review."', "stop"),
    ("Drill until a b c d e f g, and until lab approves.", "Drill until a b c d e f g, and "
                                                          "until lab approves"),
])  # fmt: skip
def test_review_round_1_misses(text, quote):
    c = check_role(text)
    assert not c.ok and c.detail == detail(quote)


@pytest.mark.parametrize("text", [
    "Log the drill core.\nUntil the lab approves the assay, store samples.",
    "Do not mix samples. Drilling continues as usual.",
    "Do not mix samples.\nDrilling continues as usual.",
])  # fmt: skip
def test_review_round_1_false_refusals(text):
    assert check_role(text).ok


def test_a_command_at_the_start_of_the_body_is_seen_and_fields_do_not_run_together(box):
    prices = load_prices()
    stop = Draft(title="Ground alert", body="Stop and get geotech review.")
    assert verify("safety", stop, box, prices)[-1].detail == detail("Stop")
    joined = Draft(title="The drill core is poor",
                   body="Keep samples until lab approves the assay.")  # fmt: skip
    assert verify("safety", joined, box, prices)[-1].ok
    f = HoleFinding(title="Nothing along the hole", body="No trend",
                    trends=[], action="none", action_reason="Stop and get geotech review.")
    assert check_finding(f, [], box, [])[-1].detail == detail("Stop")
    both = Draft(title="Stop drilling", body="Do not continue.")
    assert verify("safety", both, box, prices)[-1].detail == detail("Stop drilling")
