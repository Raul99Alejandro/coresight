"""Deterministic geotechnical engine (symbolic layer).

No LLM ever touches these numbers. Every value in an IntervalLog can be traced
back to the list of piece lengths that produced it.

Conventions
-----------
- Piece positions are in centimetres measured from the start of the run
  (0 cm = ``from_m``), along the core axis.
- A break flagged ``mechanical_break_after`` was made by drilling or handling.
  The core was intact in situ, so both sides are rejoined into one piece.
- A break flagged ``uncertain_break_after`` is treated as natural (the
  conservative choice, as Deere recommends) and is counted so a geologist
  can review it.
- A break after the last piece in the run is the run boundary, not a fracture.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

RQD_MIN_PIECE_CM = 10.0
_EPS = 1e-9


@dataclass(frozen=True)
class Piece:
    start_cm: float
    end_cm: float
    mechanical_break_after: bool = False
    uncertain_break_after: bool = False

    def __post_init__(self) -> None:
        if not (math.isfinite(self.start_cm) and math.isfinite(self.end_cm)):
            raise ValueError("piece positions must be finite numbers")
        if self.end_cm <= self.start_cm:
            raise ValueError(
                f"piece end ({self.end_cm}) must be greater than start ({self.start_cm})"
            )
        if self.mechanical_break_after and self.uncertain_break_after:
            raise ValueError("a break cannot be both mechanical and uncertain")

    @property
    def length_cm(self) -> float:
        return self.end_cm - self.start_cm


@dataclass(frozen=True)
class IntervalLog:
    from_m: float
    to_m: float
    run_length_cm: float
    recovered_cm: float
    rqd_cm: float
    rqd_pct: float
    tcr_pct: float
    intact_piece_lengths_cm: tuple[float, ...]
    natural_fractures: int
    fracture_frequency_per_m: float
    uncertain_breaks: int
    mechanical_breaks: int

    @property
    def intact_pieces(self) -> int:
        return len(self.intact_piece_lengths_cm)


def _clip(pieces: Iterable[Piece], run_length_cm: float) -> list[Piece]:
    """Sort pieces, reject overlaps and cut them to the run length."""
    ordered = sorted(pieces, key=lambda p: p.start_cm)
    for prev, nxt in zip(ordered, ordered[1:], strict=False):
        if nxt.start_cm < prev.end_cm - _EPS:
            raise ValueError(
                f"pieces overlap: [{prev.start_cm}, {prev.end_cm}] and "
                f"[{nxt.start_cm}, {nxt.end_cm}]"
            )
    clipped = []
    for p in ordered:
        start, end = max(p.start_cm, 0.0), min(p.end_cm, run_length_cm)
        if end - start > _EPS:
            clipped.append(
                Piece(start, end, p.mechanical_break_after, p.uncertain_break_after)
            )
    return clipped


def log_interval(pieces: Iterable[Piece], from_m: float, to_m: float) -> IntervalLog:
    """Compute RQD, TCR and fracture frequency for one drilling run.

    RQD = sum of intact pieces >= 10 cm / run length x 100
    TCR = recovered core / run length x 100
    natural fractures = intact pieces - 1; frequency = fractures / metre
    """
    if not (math.isfinite(from_m) and math.isfinite(to_m)):
        raise ValueError("interval depths must be finite numbers")
    if to_m <= from_m:
        raise ValueError(f"to_m ({to_m}) must be greater than from_m ({from_m})")

    run_length_cm = (to_m - from_m) * 100.0
    clipped = _clip(pieces, run_length_cm)

    intact: list[float] = []
    current = 0.0
    mechanical = uncertain = 0
    for i, p in enumerate(clipped):
        current += p.length_cm
        is_last = i == len(clipped) - 1
        if p.mechanical_break_after and not is_last:
            mechanical += 1
            continue  # rejoin with the next piece
        if p.uncertain_break_after and not is_last:
            uncertain += 1
        intact.append(current)
        current = 0.0

    recovered_cm = sum(p.length_cm for p in clipped)
    rqd_cm = sum(length for length in intact if length >= RQD_MIN_PIECE_CM - _EPS)
    natural_fractures = max(len(intact) - 1, 0)
    run_length_m = run_length_cm / 100.0

    return IntervalLog(
        from_m=from_m,
        to_m=to_m,
        run_length_cm=run_length_cm,
        recovered_cm=recovered_cm,
        rqd_cm=rqd_cm,
        rqd_pct=rqd_cm / run_length_cm * 100.0,
        tcr_pct=recovered_cm / run_length_cm * 100.0,
        intact_piece_lengths_cm=tuple(intact),
        natural_fractures=natural_fractures,
        fracture_frequency_per_m=natural_fractures / run_length_m,
        uncertain_breaks=uncertain,
        mechanical_breaks=mechanical,
    )


def rock_quality_class(rqd: float) -> str:
    """Deere (1964) rock quality designation class for an RQD in percent."""
    if not math.isfinite(rqd) or rqd < 0 or rqd > 100 + _EPS:
        raise ValueError(f"RQD must be between 0 and 100, got {rqd}")
    if rqd < 25:
        return "very poor"
    if rqd < 50:
        return "poor"
    if rqd < 75:
        return "fair"
    if rqd < 90:
        return "good"
    return "excellent"


# --- Drill hole: boxes joined by depth (point D) -----------------------------
#
# A hole is the approved boxes of one drill hole laid end to end by depth. Box
# runs give their pieces in metres from the collar (``DepthPiece``). Recovered
# core is laid from the top of each run, as ``log_interval`` assumes.

DEPTH_TOL_M = 0.01  # gaps and overlaps up to 1 cm are rounding, not a problem


@dataclass(frozen=True)
class DepthPiece:
    from_m: float
    to_m: float
    mechanical_break_after: bool = False
    uncertain_break_after: bool = False

    def __post_init__(self) -> None:
        if not (math.isfinite(self.from_m) and math.isfinite(self.to_m)):
            raise ValueError("piece depths must be finite numbers")
        if self.to_m <= self.from_m:
            raise ValueError(
                f"piece to_m ({self.to_m}) must be greater than from_m ({self.from_m})"
            )


@dataclass(frozen=True)
class BoxRun:
    """One run, or the part of a run, as logged in one box."""

    box: int
    from_m: float
    to_m: float
    pieces: tuple[DepthPiece, ...]
    complete: bool = True  # False: the run continues in the previous or next box


@dataclass(frozen=True)
class DepthIssue:
    kind: str  # "gap" (no box covers it) or "overlap" (two boxes claim it)
    from_m: float
    to_m: float
    box_before: int
    box_after: int


@dataclass(frozen=True)
class WeakZone:
    """Consecutive fixed intervals with RQD below the zone threshold."""

    from_m: float
    to_m: float
    rqd_pct: float  # length weighted over the zone
    min_rqd_pct: float
    intervals: int


@dataclass(frozen=True)
class HoleLog:
    boxes: tuple[tuple[int, float, float], ...]  # (box, from_m, to_m), by depth
    issues: tuple[DepthIssue, ...]
    runs: tuple[IntervalLog, ...]
    intervals: tuple[IntervalLog, ...]
    zones: tuple[WeakZone, ...]


def _box_extents(runs: list[BoxRun]) -> list[tuple[int, float, float]]:
    """One (box, from_m, to_m) per box number, sorted by from_m."""
    ends: dict[int, list[float]] = {}
    for r in runs:
        if r.box in ends:
            ends[r.box][0] = min(ends[r.box][0], r.from_m)
            ends[r.box][1] = max(ends[r.box][1], r.to_m)
        else:
            ends[r.box] = [r.from_m, r.to_m]
    items = ((box, v[0], v[1]) for box, v in ends.items())
    return sorted(items, key=lambda b: (b[1], b[0]))


def _depth_issues(
    boxes: list[tuple[int, float, float]],
) -> list[DepthIssue]:
    """Gaps and overlaps between boxes next to each other by depth."""
    issues: list[DepthIssue] = []
    for prev, nxt in zip(boxes, boxes[1:], strict=False):
        box_before, _, end_before = prev
        box_after, start_after, end_after = nxt
        if start_after > end_before + DEPTH_TOL_M:
            issues.append(
                DepthIssue("gap", end_before, start_after, box_before, box_after)
            )
        elif start_after < end_before - DEPTH_TOL_M:
            overlap_to = min(end_before, end_after)
            issues.append(
                DepthIssue("overlap", start_after, overlap_to, box_before, box_after)
            )
    return issues


def _cut_overlaps(
    runs: list[BoxRun], boxes: list[tuple[int, float, float]]
) -> list[BoxRun]:
    """Cut later boxes to start where earlier boxes end; drop emptied runs."""
    by_box: dict[int, list[BoxRun]] = {}
    for r in runs:
        by_box.setdefault(r.box, []).append(r)
    trimmed: list[BoxRun] = []
    covered_to = float("-inf")
    for box, _, box_to in boxes:
        for r in by_box.get(box, []):
            start = max(r.from_m, covered_to)
            if start >= r.to_m:
                continue
            kept: list[DepthPiece] = []
            for p in r.pieces:
                s = max(p.from_m, start)
                e = min(p.to_m, r.to_m)
                if e - s <= _EPS / 100.0:
                    continue
                kept.append(
                    DepthPiece(s, e, p.mechanical_break_after, p.uncertain_break_after)
                )
            trimmed.append(BoxRun(r.box, start, r.to_m, tuple(kept), r.complete))
        covered_to = max(covered_to, box_to)
    return trimmed


def _join_parts(
    runs: list[BoxRun],
) -> list[tuple[float, float, list[DepthPiece]]]:
    """Group split runs (incomplete, different boxes, contiguous) into one."""
    ordered = sorted(runs, key=lambda r: (r.from_m, r.to_m, r.box))
    groups: list[list[BoxRun]] = []
    for r in ordered:
        if groups:
            prev = groups[-1][-1]
            gap = r.from_m - prev.to_m
            if (
                not prev.complete
                and not r.complete
                and prev.box != r.box
                and gap <= DEPTH_TOL_M + 1e-9
                and gap >= -1e-9
            ):
                groups[-1].append(r)
                continue
        groups.append([r])
    joined: list[tuple[float, float, list[DepthPiece]]] = []
    for group in groups:
        pieces: list[DepthPiece] = []
        for part in group:
            pieces.extend(part.pieces)
        pieces.sort(key=lambda p: p.from_m)
        joined.append((group[0].from_m, group[-1].to_m, pieces))
    return joined


def _as_run_pieces(pieces: list[DepthPiece], from_m: float) -> list[Piece]:
    """Depth pieces as cm from the run start, flags kept."""
    return [
        Piece(
            (p.from_m - from_m) * 100.0,
            (p.to_m - from_m) * 100.0,
            p.mechanical_break_after,
            p.uncertain_break_after,
        )
        for p in pieces
    ]


def _cover_stretches(
    boxes: list[tuple[int, float, float]],
) -> list[tuple[float, float]]:
    """Contiguous boxes merged; gaps wider than tolerance split the cover."""
    start, end = boxes[0][1], boxes[0][2]
    stretches: list[tuple[float, float]] = []
    for _, b_from, b_to in boxes[1:]:
        if b_from > end + DEPTH_TOL_M:
            stretches.append((start, end))
            start, end = b_from, b_to
        else:
            end = max(end, b_to)
    stretches.append((start, end))
    return stretches


def _fixed_bounds(
    stretches: list[tuple[float, float]], step_m: float
) -> list[tuple[float, float]]:
    """Grid intervals at multiples of step_m, cut to the cover, slivers skipped."""
    bounds: list[tuple[float, float]] = []
    for s_from, s_to in stretches:
        k_start = math.floor(s_from / step_m)
        k_end = math.ceil(s_to / step_m)
        for k in range(k_start, k_end):
            a = max(s_from, k * step_m)
            b = min(s_to, (k + 1) * step_m)
            if b <= a or b - a + 1e-9 < DEPTH_TOL_M:
                continue
            bounds.append((a, b))
    return bounds


def _cut_for_interval(
    pieces: list[DepthPiece], from_m: float, to_m: float
) -> list[Piece]:
    """Pieces clipped to one fixed interval; a cut at its end keeps no flag."""
    out: list[Piece] = []
    for p in pieces:
        if p.to_m <= from_m or p.from_m >= to_m:
            continue
        s = max(p.from_m, from_m)
        e = min(p.to_m, to_m)
        if e - s <= _EPS / 100.0:
            continue
        cut = e < p.to_m - 1e-9
        mech = False if cut else p.mechanical_break_after
        unc = False if cut else p.uncertain_break_after
        out.append(Piece((s - from_m) * 100.0, (e - from_m) * 100.0, mech, unc))
    return out


def _weak_zones(
    intervals: tuple[IntervalLog, ...],
    zone_max_rqd: float,
    zone_min_intervals: int,
) -> tuple[WeakZone, ...]:
    """Groups of poor, contiguous intervals long enough to be a zone."""
    zones: list[WeakZone] = []
    group: list[IntervalLog] = []

    def flush() -> None:
        if len(group) >= zone_min_intervals:
            rqd = sum(i.rqd_cm for i in group)
            length = sum(i.run_length_cm for i in group)
            zones.append(
                WeakZone(
                    group[0].from_m,
                    group[-1].to_m,
                    rqd / length * 100.0,
                    min(i.rqd_pct for i in group),
                    len(group),
                )
            )
        group.clear()

    for iv in intervals:
        contiguous = not group or iv.from_m - group[-1].to_m <= DEPTH_TOL_M + 1e-9
        if iv.rqd_pct < zone_max_rqd and contiguous:
            group.append(iv)
        else:
            flush()
            if iv.rqd_pct < zone_max_rqd:
                group.append(iv)
    flush()
    return tuple(zones)


def pieces_at_depth(pieces: Iterable[Piece], from_m: float, to_m: float) -> list[DepthPiece]:
    """Run pieces (cm from the run start) as depths in metres, cut at ``to_m``.

    Depths are ``from_m + cm / 100``; flags are kept as given.
    """
    if not (math.isfinite(from_m) and math.isfinite(to_m)):
        raise ValueError("interval depths must be finite numbers")
    if to_m <= from_m:
        raise ValueError(f"to_m ({to_m}) must be greater than from_m ({from_m})")
    out: list[DepthPiece] = []
    for p in pieces:
        start_m = from_m + p.start_cm / 100.0
        end_m = from_m + p.end_cm / 100.0
        if start_m >= to_m or end_m <= from_m:
            continue
        s = max(start_m, from_m)
        e = min(end_m, to_m)
        if e - s <= _EPS / 100.0:
            continue
        out.append(DepthPiece(s, e, p.mechanical_break_after, p.uncertain_break_after))
    return out


def log_hole(
    runs: Iterable[BoxRun],
    step_m: float = 1.0,
    zone_max_rqd: float = 50.0,
    zone_min_intervals: int = 2,
) -> HoleLog:
    """Join the runs of a hole's boxes by depth and log it by run and by fixed interval.

    Boxes are sorted by depth; gaps and overlaps reported; runs joined and logged.
    """
    runs_list = list(runs)
    if not runs_list:
        raise ValueError("hole has no runs")
    if not (math.isfinite(step_m) and step_m > 0):
        raise ValueError(f"step_m ({step_m}) must be a positive finite number")
    if zone_min_intervals < 1:
        raise ValueError(
            f"zone_min_intervals ({zone_min_intervals}) must be at least 1"
        )
    for r in runs_list:
        if not (math.isfinite(r.from_m) and math.isfinite(r.to_m)):
            raise ValueError("run depths must be finite numbers")
        if r.to_m <= r.from_m:
            raise ValueError(
                f"run to_m ({r.to_m}) must be greater than from_m ({r.from_m})"
            )
    boxes = _box_extents(runs_list)
    issues = tuple(_depth_issues(boxes))
    trimmed = _cut_overlaps(runs_list, boxes)
    joined = _join_parts(trimmed)
    run_logs = tuple(
        log_interval(_as_run_pieces(pieces, f), f, t) for f, t, pieces in joined
    )
    stretches = _cover_stretches(boxes)
    bounds = _fixed_bounds(stretches, step_m)
    all_pieces: list[DepthPiece] = []
    for r in trimmed:
        all_pieces.extend(r.pieces)
    all_pieces.sort(key=lambda p: p.from_m)
    interval_logs = tuple(
        log_interval(_cut_for_interval(all_pieces, a, b), a, b) for a, b in bounds
    )
    zones = _weak_zones(interval_logs, zone_max_rqd, zone_min_intervals)
    return HoleLog(
        boxes=tuple(boxes),
        issues=issues,
        runs=run_logs,
        intervals=interval_logs,
        zones=zones,
    )
