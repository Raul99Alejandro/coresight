"""The deterministic draft check (verify.py): the spec the verifier is built against.

Box DDH-1, box 3: run 0 is 10-11 m (RQD 85.0, TCR 93.0, FF 2.0, 2 fractures),
run 1 is 11-12.5 m (RQD 56.7, TCR 62.0, FF 1.33, 2 fractures).
verify() also takes the earlier approved boxes of the hole (what hole_history and quote see).
"""

import pytest
from test_review import PIECES, make_box, make_run

from coresight.agents import load_prices
from coresight.schemas import AreaDraft, Draft, DraftFigure, DraftLine, Handoffs, Interval
from coresight.verify import verify

CHECKS = ["intervals", "figures", "numbers", "prices"]


@pytest.fixture
def box():
    return make_box(make_run(PIECES, 10, 11), make_run(PIECES, 11, 12.5))


@pytest.fixture
def prices():
    return load_prices()


def by_name(checks):
    assert [c.name for c in checks] == CHECKS  # always the same four, in this order
    return {c.name: c for c in checks}


def safety(**kw) -> Draft:
    fields = dict(
        title="Ground condition alert, DDH-1 box 3",
        body="Run 11.0-12.5 m is fair rock: RQD 56.7%, fracture frequency 1.33 per metre.",
        intervals=[Interval(from_m=11.0, to_m=12.5)],
        figures=[
            DraftFigure(run=1, metric="rqd_pct", value=56.7),
            DraftFigure(run=1, metric="fracture_frequency_per_m", value=1.33),
        ],
    )
    fields.update(kw)
    return Draft(**fields)


def test_a_traceable_draft_passes(box, prices):
    checks = by_name(verify("safety", safety(), box, prices))
    assert all(c.ok for c in checks.values()), checks


def test_figure_that_differs_from_geometry_fails(box, prices):
    draft = safety(figures=[DraftFigure(run=1, metric="rqd_pct", value=45.0)])
    checks = by_name(verify("safety", draft, box, prices))
    assert not checks["figures"].ok
    assert "56.7" in checks["figures"].detail  # says what geometry.py has


def test_figure_of_a_run_that_does_not_exist_fails(box, prices):
    draft = safety(figures=[DraftFigure(run=5, metric="rqd_pct", value=56.7)])
    assert not by_name(verify("safety", draft, box, prices))["figures"].ok


def test_figure_is_compared_at_the_precision_it_is_quoted(box, prices):
    draft = safety(figures=[DraftFigure(run=1, metric="fracture_frequency_per_m", value=1.3)])
    assert by_name(verify("safety", draft, box, prices))["figures"].ok


def test_interval_outside_the_box_fails(box, prices):
    draft = safety(intervals=[Interval(from_m=12.0, to_m=14.0)])
    checks = by_name(verify("safety", draft, box, prices))
    assert not checks["intervals"].ok
    assert "12.0" in checks["intervals"].detail or "14.0" in checks["intervals"].detail


def test_interval_inside_one_run_passes(box, prices):
    draft = safety(intervals=[Interval(from_m=10.2, to_m=10.8)])
    assert by_name(verify("safety", draft, box, prices))["intervals"].ok


def test_number_in_the_text_that_no_tool_gave_fails(box, prices):
    draft = safety(body="Run 11.0-12.5 m: RQD 45%, expect 3.7 fractures per metre.")
    checks = by_name(verify("safety", draft, box, prices))
    assert not checks["numbers"].ok
    assert "45" in checks["numbers"].detail and "3.7" in checks["numbers"].detail


def test_rounded_numbers_and_small_counts_are_traceable(box, prices):
    draft = safety(body="DDH-1 box 3, 2 runs. Run 11-12.5 m: RQD 57%, TCR 62%.")
    assert by_name(verify("safety", draft, box, prices))["numbers"].ok


def test_prices_only_apply_to_drafts_with_lines(box, prices):
    assert by_name(verify("safety", safety(), box, prices))["prices"].ok


def finance(lines, total, body=None) -> Draft:
    return Draft(
        title="Assay cost, DDH-1 box 3",
        body=body or f"Example prices. Total ${total:,.2f}.",
        lines=lines,
        total_usd=total,
    )


def test_priced_from_the_table_passes(box, prices):
    lines = [
        DraftLine(code="PREP", samples=3, unit_usd=9.0, total_usd=27.0),
        DraftLine(code="AU-FA", samples=3, unit_usd=18.0, total_usd=54.0),
    ]
    body = "3 samples. PREP $9.00 each, AU-FA $18.00 each, total $81.00 of a $12,000 budget."
    checks = by_name(verify("finance", finance(lines, 81.0, body), box, prices))
    assert all(c.ok for c in checks.values()), checks


@pytest.mark.parametrize(
    "line",
    [
        DraftLine(code="CU-XRF", samples=3, unit_usd=10.0, total_usd=30.0),  # not in the table
        DraftLine(code="PREP", samples=3, unit_usd=12.0, total_usd=36.0),  # wrong unit price
        DraftLine(code="PREP", samples=3, unit_usd=9.0, total_usd=30.0),  # wrong line total
    ],
)
def test_price_not_from_the_table_fails(box, prices, line):
    checks = by_name(verify("finance", finance([line], line.total_usd), box, prices))
    assert not checks["prices"].ok


def test_total_must_be_the_sum_of_the_lines(box, prices):
    lines = [DraftLine(code="PREP", samples=3, unit_usd=9.0, total_usd=27.0)]
    assert not by_name(verify("finance", finance(lines, 30.0), box, prices))["prices"].ok


def test_finance_draft_without_lines_fails(box, prices):
    draft = Draft(title="Assay cost", body="Cost to be confirmed.")
    assert not by_name(verify("finance", draft, box, prices))["prices"].ok


PREP_3 = [DraftLine(code="PREP", samples=3, unit_usd=9.0, total_usd=27.0)]


def earlier_box(spent=None):
    """Box 2 of the same hole, 7-8.5 m, with an approved finance draft of `spent` USD."""
    b = make_box(make_run(PIECES, 7, 8.5), status="approved")
    b.box_number = 2
    if spent is not None:
        cost = Draft(title="Assay cost", body="Approved.", lines=PREP_3, total_usd=spent)
        b.handoffs = Handoffs(drafts=[AreaDraft(area="finance", model="m", draft=cost,
                                                status="approved")])  # fmt: skip
    return b


def test_budget_left_after_the_quote_is_traceable(box, prices):
    body = "Total $27.00. The $12,000.00 budget keeps $11,973.00 after it."
    assert by_name(verify("finance", finance(PREP_3, 27.0, body), box, prices))["numbers"].ok


def test_budget_left_counts_what_earlier_boxes_spent(box, prices):
    body = "Total $27.00. $27.00 spent before; $11,946.00 left after it."
    draft = finance(PREP_3, 27.0, body)
    assert by_name(verify("finance", draft, box, prices, [earlier_box(27.0)]))["numbers"].ok
    assert not by_name(verify("finance", draft, box, prices))["numbers"].ok  # no history: 11,973


def test_budget_left_that_no_tool_gave_fails(box, prices):
    body = "Total $27.00. The budget keeps $11,500.00 after it."
    checks = by_name(verify("finance", finance(PREP_3, 27.0, body), box, prices))
    assert not checks["numbers"].ok
    assert "11,500" in checks["numbers"].detail


def test_numbers_from_earlier_boxes_of_the_hole_are_traceable(box, prices):
    draft = Draft(title="Ore change, DDH-1 box 3",
                  body="Box 2 (7.0-8.5 m) was fair rock; box 3 starts at 10.0 m.")  # fmt: skip
    assert not by_name(verify("plant", draft, box, prices))["numbers"].ok
    assert by_name(verify("plant", draft, box, prices, [earlier_box()]))["numbers"].ok


def test_runs_can_be_named_from_one(box, prices):
    draft = safety(body="Run 2 (11.0-12.5 m) is fair rock: RQD 56.7%.")
    assert by_name(verify("safety", draft, box, prices))["numbers"].ok
