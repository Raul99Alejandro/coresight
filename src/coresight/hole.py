"""A drill hole: the approved boxes of one hole joined by depth (point D).

This module only gathers boxes, hands their pieces to ``geometry.log_hole`` and
labels what comes back. Every RQD, TCR, fracture count, gap, overlap and zone is
computed in ``geometry.py``.

Recovered core is laid from the top of each run, as the box log does
(``runs.log_segment``), so a box and its hole agree run by run.
"""

from __future__ import annotations

from collections.abc import Iterable

from coresight.geometry import (
    DEPTH_TOL_M,
    BoxRun,
    IntervalLog,
    Piece,
    log_hole,
    pieces_at_depth,
    rock_quality_class,
)
from coresight.schemas import (
    AnomalyType,
    BoxReview,
    HoleBox,
    HoleInterval,
    HoleIssue,
    HoleTrace,
    HoleView,
    HoleZone,
    RunReview,
)

STEP_M = 1.0  # fixed intervals of the hole log
ZONE_MAX_RQD = 50.0  # a zone is poor or very poor rock (Deere)

# No public hole in the demo has a downhole survey. The 3D view needs an
# orientation, so it uses this one and says on screen that it is an example.
EXAMPLE_TRACE = HoleTrace(
    azimuth_deg=45.0,
    dip_deg=-70.0,
    surveyed=False,
    note="Example trace (azimuth 045, dip -70): this hole has no downhole survey.",
)


def _piece(start: float, end: float, kind: str) -> Piece:
    # as runs._piece: a possible mechanical break stays natural until a geologist confirms it
    return Piece(
        start,
        end,
        mechanical_break_after=kind == "mechanical",
        uncertain_break_after=kind in ("uncertain", "possible_mechanical"),
    )


def run_pieces(run: RunReview) -> list[Piece]:
    """The run's pieces laid end to end from the run start, in cm (as runs.log_segment)."""
    pos, pieces = 0.0, []
    for p in run.pieces:
        length = p.end_cm - p.start_cm
        pieces.append(_piece(pos, pos + length, p.break_after))
        pos += length
    return pieces


def box_runs(box: BoxReview) -> list[BoxRun]:
    return [
        BoxRun(
            box=box.box_number,
            from_m=r.from_m,
            to_m=r.to_m,
            pieces=tuple(pieces_at_depth(run_pieces(r), r.from_m, r.to_m)),
            complete=r.log.complete,
        )
        for r in box.runs
    ]


def logged_boxes(boxes: Iterable[BoxReview], hole_id: str) -> list[BoxReview]:
    """Approved boxes of the hole, the latest approval of each box number."""
    latest: dict[int, BoxReview] = {}
    for b in boxes:
        if b.hole_id != hole_id or b.status != "approved" or not b.runs:
            continue
        seen = latest.get(b.box_number)
        if seen is None or (b.approved_at or b.created_at) > (seen.approved_at or seen.created_at):
            latest[b.box_number] = b
    return sorted(latest.values(), key=lambda b: (b.runs[0].from_m, b.box_number))


def _overlap(a_from: float, a_to: float, b_from: float, b_to: float) -> float:
    return min(a_to, b_to) - max(a_from, b_from)


def _labelled(log: IntervalLog, boxes: list[BoxReview]) -> HoleInterval:
    """An interval of the hole with the boxes, lithology and anomalies of the runs it touches."""
    touched = []
    for b in boxes:
        for r in b.runs:
            shared = _overlap(log.from_m, log.to_m, r.from_m, r.to_m)
            if shared > DEPTH_TOL_M / 2:
                touched.append((shared, b.box_number, r))
    described = [t for t in touched if t[2].description]
    main = max(described, key=lambda t: t[0])[2].description if described else None
    flagged = {a.type for _, _, r in described for a in r.description.anomalies}
    rqd = min(log.rqd_pct, 100.0)
    return HoleInterval(
        from_m=round(log.from_m, 3),
        to_m=round(log.to_m, 3),
        rqd_pct=round(rqd, 1),
        tcr_pct=round(min(log.tcr_pct, 100.0), 1),
        natural_fractures=log.natural_fractures,
        fracture_frequency_per_m=round(log.fracture_frequency_per_m, 2),
        uncertain_breaks=log.uncertain_breaks,
        rock_quality=rock_quality_class(rqd),
        boxes=sorted({n for _, n, _ in touched}),
        lithology=main.lithology if main else None,
        anomalies=[t for t in AnomalyType if t in flagged],
    )


def hole_view(boxes: Iterable[BoxReview], hole_id: str, step_m: float = STEP_M) -> HoleView:
    """The hole log from every box of ``hole_id``; only approved boxes enter the log."""
    boxes = list(boxes)
    mine = [b for b in boxes if b.hole_id == hole_id]
    logged = logged_boxes(mine, hole_id)
    used = {b.id for b in logged}
    numbers = {b.box_number for b in logged}
    # an older copy of a box already in the log is left out
    listed = [
        HoleBox(
            id=b.id,
            box_number=b.box_number,
            from_m=b.runs[0].from_m if b.runs else 0.0,
            to_m=b.runs[-1].to_m if b.runs else 0.0,
            status=b.status,
            source=b.source,
            in_log=b.id in used,
        )
        for b in sorted(mine, key=lambda b: (b.box_number, b.created_at))
        if b.id in used or b.box_number not in numbers
    ]
    view = HoleView(
        hole_id=hole_id,
        step_m=step_m,
        zone_max_rqd=ZONE_MAX_RQD,
        boxes=listed,
        trace=EXAMPLE_TRACE,
    )
    runs = [r for b in logged for r in box_runs(b)]
    if not runs:
        return view
    log = log_hole(runs, step_m=step_m, zone_max_rqd=ZONE_MAX_RQD)
    view.from_m = round(log.boxes[0][1], 3)
    view.to_m = round(max(to for _, _, to in log.boxes), 3)
    view.issues = [
        HoleIssue(
            kind=i.kind,
            from_m=round(i.from_m, 3),
            to_m=round(i.to_m, 3),
            box_before=i.box_before,
            box_after=i.box_after,
        )
        for i in log.issues
    ]
    view.runs = [_labelled(r, logged) for r in log.runs]
    view.intervals = [_labelled(i, logged) for i in log.intervals]
    view.zones = [
        HoleZone(
            from_m=round(z.from_m, 3),
            to_m=round(z.to_m, 3),
            rqd_pct=round(z.rqd_pct, 1),
            min_rqd_pct=round(z.min_rqd_pct, 1),
            intervals=z.intervals,
            rock_quality=rock_quality_class(min(z.rqd_pct, 100.0)),
        )
        for z in log.zones
    ]
    return view


def hole_summaries(boxes: Iterable[BoxReview]) -> list[dict]:
    """One line per hole that has at least one approved box."""
    boxes = list(boxes)
    out = []
    for hole_id in sorted({b.hole_id for b in boxes}):
        logged = logged_boxes(boxes, hole_id)
        if not logged:
            continue
        mine = [b for b in boxes if b.hole_id == hole_id]
        out.append(
            {
                "hole_id": hole_id,
                "boxes_in_log": [b.box_number for b in logged],
                "boxes_pending": sorted(
                    {
                        b.box_number
                        for b in mine
                        if b.status in ("processing", "ready")
                        and b.box_number not in {x.box_number for x in logged}
                    }
                ),
                "from_m": logged[0].runs[0].from_m,
                "to_m": max(b.runs[-1].to_m for b in logged),
            }
        )
    return out


def depth_history(view: HoleView) -> dict:
    """The hole by depth, for an agent: read-only, every number from geometry.py."""

    def row(i: HoleInterval) -> dict:
        return {
            "from_m": i.from_m,
            "to_m": i.to_m,
            "rqd_pct": i.rqd_pct,
            "tcr_pct": i.tcr_pct,
            "fracture_frequency_per_m": i.fracture_frequency_per_m,
            "rock_quality_deere": i.rock_quality,
            "lithology": i.lithology,
            "anomalies": [a.value for a in i.anomalies],
            "boxes": i.boxes,
        }

    return {
        "hole_id": view.hole_id,
        "from_m": view.from_m,
        "to_m": view.to_m,
        "boxes_in_log": [b.box_number for b in view.boxes if b.in_log],
        "runs": [row(r) for r in view.runs],
        f"intervals_{view.step_m:g}_m": [row(i) for i in view.intervals],
        "weak_zones": [z.model_dump() for z in view.zones],
        "gaps_and_overlaps": [i.model_dump() for i in view.issues],
        "note": (
            f"Weak zone: at least two consecutive {view.step_m:g} m intervals with RQD "
            f"below {view.zone_max_rqd:g}. A gap is depth no approved box covers."
        ),
        "source": "geometry.log_hole (deterministic), from the approved boxes",
    }
