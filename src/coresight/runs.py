"""Stage 3 wiring: pieces of every row -> drilling runs -> geometry.log_interval.

Rows are read left to right, top to bottom, as core is laid in a box. Run
markers (the blocks the driller puts at the end of every run) split that
sequence; each stretch between markers is one run of the box's list.

A box usually shows one marker fewer than the runs on its list: the first
run may have started in the previous box and the last one may go on in the
next. Only runs seen whole get ``complete=True``: those that end at a marker
in this box and either are not the first or start in this box.

Every number comes from geometry.log_interval. Break kinds come from
coresight.segmentation: mechanical breaks are rejoined; uncertain and
possible mechanical breaks count as natural (the conservative choice) and
are flagged for review.
"""

from __future__ import annotations

from dataclasses import dataclass

from coresight.geometry import IntervalLog, Piece, log_interval, rock_quality_class
from coresight.schemas import Interval, IntervalResult
from coresight.segmentation import RowPieces

DUPLICATE_MARKER_CM = 3.0  # same block seen in two neighbouring rows


@dataclass(frozen=True, order=True)
class Position:
    """A point along the laid-out core: row index, then cm from the row's start."""

    row: int
    x_cm: float


class RunMismatchError(ValueError):
    """The markers in the photo do not fit the box's run list."""


def dedupe_markers(markers: list[Position]) -> list[Position]:
    """Drop a marker repeated at the same x in the next row (a block standing on a slat).

    Two real blocks at the ends of two rows also share an x, so this is only
    applied when the photo shows more markers than the run list allows.
    """
    out: list[Position] = []
    for m in sorted(markers):
        if any(k.row == m.row - 1 and abs(m.x_cm - k.x_cm) <= DUPLICATE_MARKER_CM for k in out):
            continue
        out.append(m)
    return out


def _laid_pieces(rows: list[RowPieces]) -> list[tuple[Position, Position, str]]:
    """(start, end, kind of break after) for every piece in reading order."""
    out = []
    for r, row in enumerate(rows):
        ppc = row.px_per_cm
        for (a, b), kind in zip(row.intervals_px, row.breaks, strict=True):
            out.append((Position(r, a / ppc), Position(r, b / ppc), kind))
    return out


def _piece(start: float, end: float, kind: str) -> Piece:
    # a possible mechanical break stays natural (uncertain) until a geologist confirms it
    return Piece(
        start,
        end,
        mechanical_break_after=kind == "mechanical",
        uncertain_break_after=kind in ("uncertain", "possible_mechanical"),
    )


LaidPiece = tuple[Position, Position, str]  # start, end and kind of break after


def run_segments(
    rows: list[RowPieces], markers: list[Position], n_runs: int
) -> list[list[LaidPiece]]:
    """The laid-out pieces of every run, in reading order, split at the markers.

    A piece across a marker is cut there; the cut counts as a natural break.
    """
    markers = sorted(markers)
    if len(markers) > n_runs:
        markers = dedupe_markers(markers)
    n = len(markers)
    if n not in (n_runs - 1, n_runs):
        raise RunMismatchError(f"{n} run markers for {n_runs} runs")

    segments: list[list[LaidPiece]] = [[] for _ in range(n + 1)]
    for start, end, kind in _laid_pieces(rows):
        seg = sum(m <= start for m in markers)
        cut_inside = [m for m in markers if start < m < end]
        if cut_inside:  # a piece across a marker: the marker splits it
            edges = [start, *cut_inside, end]
            for j, (lo, hi) in enumerate(zip(edges, edges[1:], strict=False)):
                last = j == len(edges) - 2
                segments[seg + j].append((lo, hi, kind if last else "natural"))
            continue
        segments[seg].append((start, end, kind))
    return segments[:n_runs]


def log_segment(laid: list[LaidPiece], run: Interval) -> IntervalLog:
    """geometry.log_interval of one run's pieces, laid end to end from the run start."""
    pos, pieces = 0.0, []
    for start, end, kind in laid:
        length = end.x_cm - start.x_cm
        pieces.append(_piece(pos, pos + length, kind))
        pos += length
    return log_interval(pieces, run.from_m, run.to_m)


def assign_runs(
    rows: list[RowPieces],
    markers: list[Position],
    runs: list[Interval],
    first_starts_in_box: bool,
) -> list[tuple[Interval, IntervalLog, bool]]:
    """(run, log, complete) for every run on the list, pieces split at the markers."""
    segments = run_segments(rows, markers, len(runs))
    n = n_markers(markers, len(runs))
    out = []
    for i, run in enumerate(runs):
        complete = i < n and (i > 0 or first_starts_in_box)
        out.append((run, log_segment(segments[i], run), complete))
    return out


def n_markers(markers: list[Position], n_runs: int) -> int:
    """Markers that split the runs, after dropping duplicates when there are too many."""
    return len(dedupe_markers(markers)) if len(markers) > n_runs else len(markers)


def to_result(run: Interval, log: IntervalLog, complete: bool) -> IntervalResult:
    """Validated output for one run (schemas.IntervalResult)."""
    return IntervalResult(
        from_m=run.from_m,
        to_m=run.to_m,
        rqd_pct=round(log.rqd_pct, 1),
        tcr_pct=round(min(log.tcr_pct, 100.0), 1),
        natural_fractures=log.natural_fractures,
        fracture_frequency_per_m=round(log.fracture_frequency_per_m, 2),
        uncertain_breaks=log.uncertain_breaks,
        mechanical_breaks=log.mechanical_breaks,
        rock_quality=rock_quality_class(min(log.rqd_pct, 100.0)),
        complete=complete,
    )
