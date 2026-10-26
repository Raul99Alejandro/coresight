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
