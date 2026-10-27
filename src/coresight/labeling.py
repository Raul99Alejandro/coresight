"""Turn a hand-measured piece sheet into a BoxLabel.

A piece sheet (``data/labels/pieces/*.json``) is what a geologist measures on
the photo: the core pieces of every row in pixels, the kind of break after each
piece, and the metre marks painted on the core. This module only converts
pixels to centimetres; RQD, TCR and fractures come from ``geometry.log_interval``.

Sheet format::

    {
      "hole_id": "ONK-DTPH5.1", "box_number": 5, "image": "data/raw/...jpg",
      "runs": [{"from_m": 17.94, "to_m": 20.71}, ...],
      "rows": [{"y1": 207, "y2": 353, "pieces": [{"x1": 348, "x2": 1525, "after": "natural"}]}],
      "meter_marks": [{"row": 0, "x": 625, "depth_m": 18.0}, ...]
    }

``after`` is the break after the piece: ``natural``, ``mechanical``,
``uncertain`` or ``run_end`` (the run block, where the next run starts).
Rows are read left to right, top to bottom.
"""

from __future__ import annotations

import statistics
from typing import Literal

import numpy as np
from pydantic import Field

from coresight.calibration import Tray
from coresight.geometry import IntervalLog, Piece, log_interval
from coresight.runs import Position
from coresight.schemas import BoxLabel, Interval, _Strict

BreakKind = Literal["natural", "mechanical", "uncertain", "run_end"]


class SheetPiece(_Strict):
    x1: float
    x2: float
    after: BreakKind


class SheetRow(_Strict):
    y1: float
    y2: float
    pieces: list[SheetPiece] = Field(min_length=1)


class MeterMark(_Strict):
    row: int = Field(ge=0)
    x: float
    depth_m: float


class PieceSheet(_Strict):
    hole_id: str = Field(min_length=1)
    box_number: int = Field(ge=1)
    image: str = Field(min_length=1)
    runs: list[Interval] = Field(min_length=1)
    rows: list[SheetRow] = Field(min_length=1)
    meter_marks: list[MeterMark] = Field(min_length=2)


def _along_core_px(sheet: PieceSheet, row: int, x: float) -> float:
    """Recovered core in pixels from the start of the box to (row, x)."""
    before = sum(p.x2 - p.x1 for r in sheet.rows[:row] for p in r.pieces)
    for p in sheet.rows[row].pieces:
        if p.x1 <= x <= p.x2:
            return before + x - p.x1
        before += p.x2 - p.x1
    raise ValueError(f"meter mark at row {row}, x {x} is not on a piece")


def px_per_cm(sheet: PieceSheet) -> float:
    """Median scale between consecutive metre marks."""
    marks = sorted(sheet.meter_marks, key=lambda m: m.depth_m)
    scales = [
        (_along_core_px(sheet, b.row, b.x) - _along_core_px(sheet, a.row, a.x))
        / ((b.depth_m - a.depth_m) * 100.0)
        for a, b in zip(marks, marks[1:], strict=False)
    ]
    return statistics.median(scales)


def log_sheet(sheet: PieceSheet) -> list[IntervalLog]:
    """One IntervalLog per run, pieces assigned in reading order."""
    scale = px_per_cm(sheet)
    pieces = [p for r in sheet.rows for p in r.pieces]
    if pieces[-1].after != "run_end":
        raise ValueError("the last piece of the box must end its run")
    groups: list[list[SheetPiece]] = [[]]
    for p in pieces:
        groups[-1].append(p)
        if p.after == "run_end":
            groups.append([])
    groups.pop()
    if len(groups) != len(sheet.runs):
        raise ValueError(f"{len(groups)} runs closed by run_end, {len(sheet.runs)} listed")

    logs = []
    for run, group in zip(sheet.runs, groups, strict=True):
        pos, run_pieces = 0.0, []
        for i, p in enumerate(group):
            length = (p.x2 - p.x1) / scale
            last = i == len(group) - 1
            run_pieces.append(
                Piece(
                    pos,
                    pos + length,
                    mechanical_break_after=p.after == "mechanical" and not last,
                    uncertain_break_after=p.after == "uncertain" and not last,
                )
            )
            pos += length
        logs.append(log_interval(run_pieces, run.from_m, run.to_m))
    return logs


def label_from_sheet(sheet: PieceSheet) -> BoxLabel:
    runs = [
        {
            "from_m": log.from_m,
            "to_m": log.to_m,
            "rqd_pct": round(log.rqd_pct, 1),
            "tcr_pct": round(log.tcr_pct, 1),
            "natural_fractures": log.natural_fractures,
        }
        for log in log_sheet(sheet)
    ]
    return BoxLabel(
        hole_id=sheet.hole_id, box_number=sheet.box_number, image=sheet.image, runs=runs
    )


def sheet_markers(sheet: PieceSheet, tray: Tray) -> list[Position]:
    """Run ends of a hand-measured sheet as positions along the straightened rows."""
    out = []
    for row in sheet.rows:
        y = (row.y1 + row.y2) / 2
        for p in row.pieces:
            if p.after != "run_end":
                continue
            r = tray.row_index(p.x2, row.y1, row.y2)
            x = tray.to_straight(np.array([[p.x2, y]]))[0, 0] + 0.5 * tray.px_per_cm
            out.append(Position(r, x / tray.px_per_cm))
    return out
