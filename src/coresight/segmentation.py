"""Stage 2, segmentation: pieces of core along one straightened row, in cm.

Three methods, each a layer on the previous one, measurable for the ablation
(docs/PLAN.md, day 9):

- ``"sam"``: SAM 3.1 masks for the prompt "stone". Each mask becomes an
  interval along the row; depth markers (magenta foam), slivers and objects
  lying inside a larger one are dropped; overlapping neighbours (diagonal
  breaks) are split at the middle of the overlap.
- ``"sam+fill"``: SAM misses long smooth cylinders (it returns nothing for
  some whole rows). Stretches of 5 cm or more that SAM left empty are filled
  where the row does not look like the tray's wood: a column is core when its
  colour, across the middle of the row, is far from the slats' colour.
- ``"sam+fill+profile"``: then cut where a thin dark line crosses the core
  (plan B for fine fractures inside one mask). The brightness along the core
  axis is compared with its local median; a narrow, strong dip that crosses
  most of the core's height is a fracture.

Positions are in cm from the left end of the row crop. RQD and the rest are
computed later by geometry.py; this module only measures pieces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from coresight.geometry import Piece
from coresight.meta_client import DEFAULT_CACHE_DIR, MetaClient, sam_cache_key, sam_masks

PROMPT = "stone"
MIN_PIECE_CM = 0.5  # shorter masks are specks, not core
CONTAINED = 0.85  # an object this much inside a larger one is a duplicate or a chip
MARKER_MIN_FRACTION = 0.3  # share of magenta pixels that makes a mask a depth marker
DIP_MAX_WIDTH_CM = 1.0  # a fracture line is thinner than this
DIP_MIN_CONTRAST = 0.2  # relative darkening at the line
DIP_MIN_CROSSING = 0.8  # share of the core height the dark line must cross
FILL_MIN_GAP_CM = 5.0  # only stretches SAM left empty for this long are filled
WOOD_DISTANCE = 25.0  # Lab distance from the slat colour that counts as core
METHODS = ("sam", "sam+fill", "sam+fill+profile")
DIP_END_MARGIN_CM = 2.0  # ignore dips this close to a piece end


@dataclass
class RowPieces:
    """Pieces found in one row, with the raw intervals in crop pixels."""

    method: str
    px_per_cm: float
    intervals_px: list[tuple[float, float]] = field(default_factory=list)
    cuts_px: list[float] = field(default_factory=list)  # fracture-profile cuts (uncertain)

    @property
    def pieces(self) -> list[Piece]:
        return [Piece(a / self.px_per_cm, b / self.px_per_cm) for a, b in self.intervals_px]


def _magenta(crop_hsv: np.ndarray) -> np.ndarray:
    h, s, v = crop_hsv[..., 0], crop_hsv[..., 1], crop_hsv[..., 2]
    return (h >= 135) & (h <= 175) & (s >= 90) & (v >= 80)


def _is_marker(crop_hsv: np.ndarray, mask: np.ndarray) -> bool:
    """Magenta or pink foam block used as a depth marker."""
    if not mask.any():
        return False
    return bool(_magenta(crop_hsv)[mask].mean() >= MARKER_MIN_FRACTION)


def run_markers(crop: np.ndarray, px_per_cm: float) -> list[float]:
    """x centres (crop px) of the magenta foam blocks that mark the end of a run.

    A block stands across the middle of the row; seen at different angles it
    shows 0.5 to 10 cm of magenta. The tape measure and paint lie on the
    slats, outside the middle band. Pieces of one block less than 2.5 cm apart
    are one block; two blocks side by side (a run with no recovery) stay two.
    """
    h = crop.shape[0]
    share = _magenta(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV))[h // 4 : 3 * h // 4].mean(axis=0)
    spans: list[list[int]] = []
    x, w = 0, len(share)
    while x < w:
        if share[x] < 0.1:
            x += 1
            continue
        end = x
        while end < w and share[end] >= 0.1:
            end += 1
        if share[x:end].max() >= 0.3:
            if spans and x - spans[-1][1] < 2.5 * px_per_cm:
                spans[-1][1] = end
            else:
                spans.append([x, end])
        x = end
    return [(a + b) / 2 for a, b in spans if 0.5 * px_per_cm <= b - a <= 10 * px_per_cm]


def masks_to_intervals(
    masks: list[dict], crop: np.ndarray, px_per_cm: float
) -> tuple[list[tuple[float, float]], np.ndarray]:
    """SAM masks -> sorted, non-overlapping intervals along x, and the union mask."""
    h, w = crop.shape[:2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    union = np.zeros((h, w), dtype=bool)
    spans = []
    for m in masks:
        left, top, right, bottom = (int(v) for v in m["bounds"])
        full = np.zeros((h, w), dtype=bool)
        sub = m["mask"][: max(0, min(bottom, h) - top), : max(0, min(right, w) - left)]
        full[top : top + sub.shape[0], left : left + sub.shape[1]] = sub
        if not full.any() or _is_marker(hsv, full):
            continue
        cols = np.where(full.any(axis=0))[0]
        if (cols[-1] + 1 - cols[0]) < MIN_PIECE_CM * px_per_cm:
            continue
        spans.append((float(cols[0]), float(cols[-1] + 1), full))

    # drop objects lying inside a larger one (chips on top, duplicate masks)
    kept = []
    for i, (a, b, full) in enumerate(spans):
        inside = any(
            j != i and (b2 - a2) > (b - a) and min(b, b2) - max(a, a2) >= CONTAINED * (b - a)
            for j, (a2, b2, _) in enumerate(spans)
        )
        if not inside:
            kept.append((a, b))
            union |= full
    kept.sort()

    # neighbours that overlap (diagonal break): cut at the middle of the overlap
    intervals: list[list[float]] = []
    for a, b in kept:
        if intervals and a < intervals[-1][1]:
            cut = (a + intervals[-1][1]) / 2
            intervals[-1][1] = cut
            a = cut
        if b - a >= MIN_PIECE_CM * px_per_cm:
            intervals.append([a, b])
    return [(a, b) for a, b in intervals], union


def fill_gaps(
    crop: np.ndarray, intervals: list[tuple[float, float]], px_per_cm: float
) -> tuple[list[tuple[float, float]], np.ndarray]:
    """Add core SAM missed: long empty stretches whose colour is not the tray's wood.

    The crop runs from slat centre to slat centre, so its top and bottom
    strips are wood. Returns the intervals and a mask of the filled core.
    """
    h, w = crop.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(crop, (0, 0), 2), cv2.COLOR_BGR2LAB).astype(np.float32)
    strip = max(2, h // 12)
    wood = np.median(np.vstack([lab[:strip], lab[-strip:]]).reshape(-1, 3), axis=0)
    middle = lab[h // 4 : 3 * h // 4]
    distance = np.linalg.norm(middle - wood, axis=2)
    magenta = _magenta(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV))[h // 4 : 3 * h // 4]
    core_col = (np.median(distance, axis=0) > WOOD_DISTANCE) & (magenta.mean(axis=0) < 0.3)
    filled = np.zeros((h, w), dtype=bool)

    covered = np.zeros(w, dtype=bool)
    for a, b in intervals:
        covered[int(a) : int(np.ceil(b))] = True
    out = list(intervals)
    min_gap = FILL_MIN_GAP_CM * px_per_cm
    x = 0
    while x < w:
        if covered[x]:
            x += 1
            continue
        end = x
        while end < w and not covered[end]:
            end += 1
        if end - x >= min_gap:
            run_start = None
            for c in range(x, end + 1):
                is_core = c < end and core_col[c]
                if is_core and run_start is None:
                    run_start = c
                elif not is_core and run_start is not None:
                    if c - run_start >= MIN_PIECE_CM * px_per_cm:
                        out.append((float(run_start), float(c)))
                        filled[h // 4 : 3 * h // 4, run_start:c] = True
                    run_start = None
        x = end
    return sorted(out), filled


def _core_band(union: np.ndarray, a: int, b: int) -> tuple[int, int]:
    """Rows covering the middle half of the core between columns a and b."""
    rows = np.where(union[:, a:b].any(axis=1))[0]
    if len(rows) == 0:
        return 0, union.shape[0]
    top, bottom = rows[0], rows[-1] + 1
    quarter = (bottom - top) // 4
    return top + quarter, bottom - quarter


def fracture_cuts(
    crop: np.ndarray, union: np.ndarray, interval: tuple[float, float], px_per_cm: float
) -> list[float]:
    """x positions (crop px) of thin dark lines that cross the core inside one piece."""
    a, b = int(interval[0]), int(interval[1])
    margin = int(DIP_END_MARGIN_CM * px_per_cm)
    if b - a <= 2 * margin + 2:
        return []
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # drawn lines (red/blue orientation lines, metre ticks) are not fractures
    ink = (hsv[..., 1] > 110) & (hsv[..., 2] > 60)
    top, bottom = _core_band(union, a, b)
    band = gray[top:bottom, a:b]
    band_ink = ink[top:bottom, a:b]
    clean = np.where(band_ink, np.nan, band)
    profile = np.nanmedian(np.where(np.isnan(clean).all(axis=0), band, clean), axis=0)
    profile = cv2.GaussianBlur(profile.reshape(1, -1), (0, 0), 1.5).ravel()
    win = max(5, int(3 * px_per_cm) | 1)
    padded = np.pad(profile, win // 2, mode="edge")
    baseline = np.median(np.lib.stride_tricks.sliding_window_view(padded, win), axis=1)
    contrast = (baseline - profile) / (baseline + 1e-6)

    max_width = DIP_MAX_WIDTH_CM * px_per_cm
    cuts = []
    x = margin
    while x < len(contrast) - margin:
        if contrast[x] < DIP_MIN_CONTRAST:
            x += 1
            continue
        end = x
        while end < len(contrast) and contrast[end] >= DIP_MIN_CONTRAST / 2:
            end += 1
        start = x
        while start > 0 and contrast[start - 1] >= DIP_MIN_CONTRAST / 2:
            start -= 1
        if end - start <= max_width:
            centre = start + int(np.argmax(contrast[start:end]))
            column = band[:, max(centre - 2, 0) : centre + 3].min(axis=1)
            crossing = (column < baseline[centre] * (1 - DIP_MIN_CONTRAST / 2)).mean()
            if crossing >= DIP_MIN_CROSSING:
                cuts.append(float(a + centre))
        x = end + 1
    return cuts


def split_intervals(
    intervals: list[tuple[float, float]], cuts: list[float], px_per_cm: float
) -> list[tuple[float, float]]:
    """Cut intervals at ``cuts``; a cut too close to an end would only make a speck."""
    min_px = MIN_PIECE_CM * px_per_cm
    out = []
    for a, b in intervals:
        inner = [c for c in sorted(cuts) if a + min_px <= c <= b - min_px]
        edges = [a] + inner + [b]
        out.extend(zip(edges, edges[1:], strict=False))
    return out


def row_masks(
    client: MetaClient, crop: np.ndarray, cache_dir: Path | None = DEFAULT_CACHE_DIR
) -> list[dict]:
    """Decoded SAM masks for one row crop.

    Decoding with meta_sam_parser takes seconds per row, so the decoded masks
    are cached next to the raw SAM text, under the same key.
    """
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("could not encode the row crop")
    png = buf.tobytes()
    path = None
    if cache_dir is not None:
        path = Path(cache_dir) / "sam_masks" / f"{sam_cache_key(png, PROMPT)}.npz"
        if path.exists():
            with np.load(path) as data:
                return [
                    {
                        "id": int(data["ids"][i]),
                        "bounds": tuple(int(v) for v in data["bounds"][i]),
                        "confidence": float(data["confidence"][i]),
                        "mask": data[f"mask_{i}"],
                    }
                    for i in range(len(data["ids"]))
                ]
    masks = sam_masks(client.segment_row_raw(png, PROMPT))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            ids=np.array([m["id"] for m in masks], dtype=np.int64),
            bounds=np.array([m["bounds"] for m in masks], dtype=np.int64).reshape(-1, 4),
            confidence=np.array([m["confidence"] or 0.0 for m in masks], dtype=np.float64),
            **{f"mask_{i}": m["mask"] for i, m in enumerate(masks)},
        )
    return masks


def segment_row(
    crop: np.ndarray, masks: list[dict], px_per_cm: float, method: str = "sam+fill+profile"
) -> RowPieces:
    """Pieces of one straightened row crop from its decoded SAM masks."""
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}")
    intervals, union = masks_to_intervals(masks, crop, px_per_cm)
    if method != "sam":
        intervals, filled = fill_gaps(crop, intervals, px_per_cm)
        union |= filled
    cuts: list[float] = []
    if method == "sam+fill+profile":
        cuts = [c for iv in intervals for c in fracture_cuts(crop, union, iv, px_per_cm)]
        intervals = split_intervals(intervals, cuts, px_per_cm)
    return RowPieces(method=method, px_per_cm=px_per_cm, intervals_px=intervals, cuts_px=cuts)
