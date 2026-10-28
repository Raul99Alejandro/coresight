"""Stage 2, segmentation: pieces of core along one straightened row, in cm.

Four methods, each a layer on the previous one, measurable for the ablation
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
- ``"sam+fill+profile+marks"``: then classify every break. A break with the
  geologist's small red "x" marks next to it is mechanical (rejoined for
  RQD by geometry.py). A tight break between two long pieces whose drawn
  orientation line runs on across it is a possible mechanical break: still
  counted as natural (uncertain), but listed first for review.

Each method also has a ``"spark+"`` twin (point B of docs/ANALISIS-2.md):
instead of the phrase "stone", Muse Spark first localizes every core piece
of the row and everything that is not core (run blocks, cards, tools), and
SAM 3.1 cuts the core pieces with those boxes as prompts. Wax-sealed samples
are core (taken for testing, still recovered) and are cut too. What Spark
calls not core is taken out of the row's length (``located_masks``).
A ``"fallback+"`` method uses "stone" and turns to Spark's boxes only for a
row where "stone" returns no mask at all.

Positions are in cm from the left end of the row crop. RQD and the rest are
computed later by geometry.py; this module only measures pieces.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from coresight.geometry import Piece
from coresight.meta_client import (
    DEFAULT_CACHE_DIR,
    MAX_SAM_OBJECTS,
    MetaClient,
    SamObject,
    grid_box_to_pixels,
    sam_cache_key,
    sam_masks,
    sam_prompt,
)

PROMPT = "stone"
MIN_PIECE_CM = 0.5  # shorter masks are specks, not core
CONTAINED = 0.85  # an object this much inside a larger one is a duplicate or a chip
MARKER_MIN_FRACTION = 0.3  # share of magenta pixels that makes a mask a depth marker
DIP_MAX_WIDTH_CM = 1.0  # a fracture line is thinner than this
DIP_MIN_CONTRAST = 0.2  # relative darkening at the line
DIP_MIN_CROSSING = 0.8  # share of the core height the dark line must cross
FILL_MIN_GAP_CM = 5.0  # only stretches SAM left empty for this long are filled
WOOD_DISTANCE = 25.0  # Lab distance from the slat colour that counts as core
MARK_WINDOW_CM = 3.0  # x marks this close to a break belong to it
MARK_MIN_CM, MARK_MAX_CM = 0.3, 2.5  # size of one hand-drawn x
MARK_MIN_SAT, MARK_SAT_CONTRAST = 60, 45  # ink is saturated, and much more than the rock
MARK_MIN_NEIGHBOUR_CM = 3.0  # rubble is not marked: both pieces must be this long
FIT_MAX_GAP_CM = 0.3  # a possible mechanical break closes this tight
FIT_MIN_PIECE_CM = 10.0  # between two pieces at least this long
METHODS = ("sam", "sam+fill", "sam+fill+profile", "sam+fill+profile+marks")
SPARK = "spark+"  # prefix of the methods whose SAM prompts are Muse Spark's boxes
SPARK_METHODS = tuple(SPARK + m for m in METHODS)
FALLBACK = "fallback+"  # "stone" first; Spark's boxes only for a row where "stone" finds nothing
FALLBACK_METHODS = tuple(FALLBACK + m for m in METHODS)
BreakKind = str  # "natural", "uncertain", "possible_mechanical" or "mechanical"
DIP_END_MARGIN_CM = 2.0  # ignore dips this close to a piece end
TILE_ASPECT = 2.5  # Muse Spark sees a row in tiles about this much wider than tall
TILE_OVERLAP = 0.15  # share of a tile repeated on each side, so no piece is lost at an edge
TILE_EDGE = 0.01  # a box this close to a tile edge was cut by it
# a wax-sealed sample is core taken for testing: it counts as recovered, as in our labels
CORE_KINDS = ("core", "waxed_sample")
BOX_MARGIN = 0.05  # a box-prompt mask may pass its box by this share of the box width
TILE_DUPLICATE = 0.6  # boxes of one kind sharing this much of the smaller one are one object


@dataclass
class RowPieces:
    """Pieces found in one row, with the raw intervals in crop pixels."""

    method: str
    px_per_cm: float
    intervals_px: list[tuple[float, float]] = field(default_factory=list)
    cuts_px: list[float] = field(default_factory=list)  # fracture-profile cuts (uncertain)
    breaks: list[BreakKind] = field(default_factory=list)  # kind of break after each piece

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


def png_of(crop: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("could not encode the row crop")
    return buf.tobytes()


def row_masks(
    client: MetaClient,
    crop: np.ndarray,
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
    prompt: str = PROMPT,
) -> list[dict]:
    """Decoded SAM masks for one row crop (the phrase "stone", or a box and point prompt).

    Decoding with meta_sam_parser takes seconds per row, so the decoded masks
    are cached next to the raw SAM text, under the same key.
    """
    png = png_of(crop)
    path = None
    if cache_dir is not None:
        path = Path(cache_dir) / "sam_masks" / f"{sam_cache_key(png, prompt)}.npz"
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
    masks = sam_masks(client.segment_row_raw(png, prompt))
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


def tiles(w: int, h: int) -> list[tuple[int, int]]:
    """x ranges of the tiles Muse Spark sees: about TILE_ASPECT:1, overlapping by TILE_OVERLAP.

    On a whole row (9:1 and longer) Spark's boxes drift and it calls a label core;
    on tiles of about 2.5:1 they land on the pieces (docs/SAM-PROMPTS.md).
    """
    n = max(1, int(np.ceil(w / (TILE_ASPECT * h))))
    step = w / n
    pad = TILE_OVERLAP * step
    return [(int(max(0, t * step - pad)), int(min(w, (t + 1) * step + pad))) for t in range(n)]


def merge_tile_boxes(
    boxes: list[tuple[str, tuple[int, int, int, int], bool, bool]],
) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Join the two halves of an object a tile edge cut; keep one box of an object seen twice.

    Each box: kind, (x1, y1, x2, y2) in row px, cut by its tile's left edge, cut
    by its tile's right edge. Two overlapping boxes of one kind are the two
    halves of one object when the first was cut on its right and the second on
    its left; they are one object seen by two tiles when most of the smaller one
    is shared, and then the larger box is kept. Touching pieces stay apart.
    """
    out: list[list] = []
    for kind, box, cut_left, cut_right in sorted(boxes, key=lambda b: (b[0], b[1][0])):
        prev = out[-1] if out and out[-1][0] == kind else None
        if prev:
            (a1, ay1, a2, ay2), (b1, by1, b2, by2) = prev[1], box
            shared = min(a2, b2) - max(a1, b1)
            if shared > 0 and prev[3] and cut_left:
                prev[1] = (min(a1, b1), min(ay1, by1), max(a2, b2), max(ay2, by2))
                prev[3] = cut_right
                continue
            if shared >= TILE_DUPLICATE * (min(a2 - a1, b2 - b1) + 1):
                if b2 - b1 > a2 - a1:
                    prev[1:] = [box, cut_left, cut_right]
                continue
        out.append([kind, box, cut_left, cut_right])
    return [(kind, box) for kind, box, _, _ in sorted(out, key=lambda b: b[1][0])]


def located_masks(
    client: MetaClient, crop: np.ndarray, cache_dir: Path | None = DEFAULT_CACHE_DIR
) -> tuple[list[dict], list[tuple[float, float]]]:
    """Spark localizes, SAM cuts: masks of the core pieces and x spans that are not core.

    Muse Spark boxes every core piece (wax-sealed samples included) and every
    object that is not core (MetaClient.locate_row, validated as
    schemas.RowLocation), one tile of the row at a time, in parallel. The
    core boxes go to SAM 3.1 on the whole row as box prompts, at most 16 per
    request; each mask comes back under the index of its box. The other boxes
    are returned as x spans (crop px) to take out of the row's length.
    """
    h, w = crop.shape[:2]
    spans = tiles(w, h)
    with ThreadPoolExecutor(max_workers=len(spans)) as pool:
        answers = list(pool.map(lambda t: client.locate_row(png_of(crop[:, t[0] : t[1]])), spans))
    found = []
    for (a, b), location in zip(spans, answers, strict=True):
        for o in location.objects:
            x1, y1, x2, y2 = grid_box_to_pixels((o.x_min, o.y_min, o.x_max, o.y_max), (b - a, h))
            edge = TILE_EDGE * (b - a)
            found.append((o.kind, (a + x1, y1, a + x2, y2), a > 0 and x1 <= edge,
                          b < w and x2 >= b - a - 1 - edge))  # fmt: skip
    boxes = merge_tile_boxes(found)
    core = [b for kind, b in boxes if kind in CORE_KINDS]
    other = [(float(b[0]), float(b[2] + 1)) for kind, b in boxes if kind not in CORE_KINDS]
    masks: list[dict] = []
    for start in range(0, len(core), MAX_SAM_OBJECTS):
        batch = core[start : start + MAX_SAM_OBJECTS]
        objects = [SamObject(start + i, box=b) for i, b in enumerate(batch)]
        found_masks = row_masks(client, crop, cache_dir, sam_prompt(objects, (w, h)))
        masks += [clip_to_box(m, core[m["id"]]) for m in found_masks if m["id"] < len(core)]
    return masks, sorted(other)


def clip_to_box(m: dict, box: tuple[int, int, int, int]) -> dict:
    """A box-prompt mask kept to its box along x: SAM sometimes runs on into the next piece."""
    left, top, right, bottom = m["bounds"]
    margin = BOX_MARGIN * (box[2] - box[0] + 1)
    lo, hi = max(left, int(box[0] - margin)), min(right, int(np.ceil(box[2] + 1 + margin)))
    mask = np.zeros_like(m["mask"])
    if hi > lo:
        mask[:, lo - left : hi - left] = m["mask"][:, lo - left : hi - left]
    return {**m, "mask": mask}


def exclude_spans(
    intervals: list[tuple[float, float]], spans: list[tuple[float, float]], px_per_cm: float
) -> list[tuple[float, float]]:
    """Intervals with the x spans that are not core taken out (a block inside a piece cuts it)."""
    out = []
    for a, b in intervals:
        parts = [(a, b)]
        for s, e in spans:
            parts = [
                q
                for x, y in parts
                for q in ([(x, y)] if e <= x or s >= y else [(x, s), (e, y)])
                if q[1] > q[0]
            ]
        out += [(x, y) for x, y in parts if y - x >= MIN_PIECE_CM * px_per_cm]
    return out


def _red(crop_hsv: np.ndarray) -> np.ndarray:
    h, s, v = crop_hsv[..., 0], crop_hsv[..., 1], crop_hsv[..., 2]
    return ((h < 10) | (h > 165)) & (s > 70) & (v > 60)


def mechanical_marks(crop: np.ndarray, px_per_cm: float) -> list[float]:
    """x centres of the small red "x" marks a geologist draws beside a mechanical break.

    The red orientation line is removed first (a horizontal opening, plus
    everything at the line's height for dashed lines); what is left must be a
    compact blob of hand-drawn size inside the core band, not on the slats
    where depths are written.
    """
    h = crop.shape[0]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[..., 1].astype(np.float32)
    red = _red(hsv).astype(np.uint8)
    line_len = max(3, int(3 * px_per_cm))
    line = cv2.morphologyEx(red, cv2.MORPH_OPEN, np.ones((1, line_len), np.uint8))
    line = cv2.dilate(line, np.ones((5, 9), np.uint8))
    marks = red & (1 - line)
    # a dashed red line survives the opening: drop everything on the line's height
    rows = red[int(0.12 * h) : int(0.88 * h)].sum(axis=1)
    line_y = int(0.12 * h) + int(np.argmax(rows)) if rows.max() > 0 else -1
    band = 0.6 * px_per_cm
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(marks, connectivity=8)
    lo, hi = MARK_MIN_CM * px_per_cm, MARK_MAX_CM * px_per_cm
    out = []
    for i in range(1, n):
        _, top, w, hh, area = stats[i]
        if not (0.2 * h <= centroids[i][1] <= 0.85 * h):
            continue
        if line_y >= 0 and top - band <= line_y <= top + hh + band:
            continue
        if not (lo <= max(w, hh) <= hi) or max(w, hh) > 2 * min(w, hh):
            continue
        # an ink stroke: thin (not a filled reddish stone) on a background that is not red
        if not (0.15 * w * hh <= area <= 0.6 * w * hh):
            continue
        x0, y0 = stats[i][0], top
        pad = int(0.5 * px_per_cm)
        ring = red[max(y0 - pad, 0) : y0 + hh + pad, max(x0 - pad, 0) : x0 + w + pad]
        if (ring.sum() - area) > 0.15 * (ring.size - w * hh):
            continue
        # ink stands out in colour; on reddish or brown rock it does not, so skip
        ring_sat = sat[max(y0 - pad, 0) : y0 + hh + pad, max(x0 - pad, 0) : x0 + w + pad]
        blob_sat = sat[labels == i]
        if (
            blob_sat.mean() < MARK_MIN_SAT
            or blob_sat.mean() < np.median(ring_sat) + MARK_SAT_CONTRAST
        ):
            continue
        out.append(float(centroids[i][0]))
    return out


def _line_y(crop_hsv: np.ndarray, x1: int, x2: int) -> float | None:
    """Median y of the drawn orientation lines (blue or red) between x1 and x2."""
    h, s, v = (crop_hsv[:, x1:x2, i].astype(int) for i in range(3))
    blue = (h >= 100) & (h <= 130) & (s > 70) & (v > 50)
    red = ((h < 10) | (h > 165)) & (s > 70) & (v > 60)
    ys = np.where((blue | red).any(axis=1))[0]
    return float(np.median(ys)) if len(ys) else None


def default_breaks(intervals: list[tuple[float, float]], cuts: list[float]) -> list[BreakKind]:
    """Without classification: profile cuts and the row end are uncertain, gaps natural."""
    return [
        "uncertain"
        if i == len(intervals) - 1 or any(abs(b - c) <= 1.0 for c in cuts)
        else "natural"
        for i, (_, b) in enumerate(intervals)
    ]


def classify_breaks(
    crop: np.ndarray, intervals: list[tuple[float, float]], cuts: list[float], px_per_cm: float
) -> list[BreakKind]:
    """Kind of break after each piece (the last one is the row end)."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    marks = mechanical_marks(crop, px_per_cm)
    window = MARK_WINDOW_CM * px_per_cm
    kinds = default_breaks(intervals, cuts)
    for i, (a, b) in enumerate(intervals):
        last = i == len(intervals) - 1
        nxt = b if last else intervals[i + 1][0]
        nb = intervals[i + 1][1] - nxt if not last else b - a
        marked = any(b - window <= m <= nxt + window for m in marks)
        if marked and min(b - a, nb) >= MARK_MIN_NEIGHBOUR_CM * px_per_cm:
            kinds[i] = "mechanical"
            continue
        if kinds[i] != "natural":
            continue
        long_pieces = min(b - a, intervals[i + 1][1] - nxt) >= FIT_MIN_PIECE_CM * px_per_cm
        if not long_pieces or nxt - b > FIT_MAX_GAP_CM * px_per_cm:
            continue
        span = int(2 * px_per_cm)
        left = _line_y(hsv, max(int(b) - span, 0), max(int(b) - 2, 1))
        right = _line_y(hsv, int(nxt) + 2, min(int(nxt) + span, crop.shape[1]))
        if left is not None and right is not None and abs(left - right) <= 0.5 * px_per_cm:
            kinds[i] = "possible_mechanical"
    return kinds


def segment_row(
    crop: np.ndarray,
    masks: list[dict],
    px_per_cm: float,
    method: str = METHODS[-1],
    not_core: list[tuple[float, float]] = (),
) -> RowPieces:
    """Pieces of one straightened row crop from its decoded SAM masks.

    ``not_core``: x spans (crop px) that are not core, from located_masks.
    """
    if method not in METHODS + SPARK_METHODS + FALLBACK_METHODS:
        raise ValueError(f"unknown method {method!r}")
    layers = method.removeprefix(SPARK).removeprefix(FALLBACK)
    intervals, union = masks_to_intervals(masks, crop, px_per_cm)
    if layers != "sam":
        intervals, filled = fill_gaps(crop, intervals, px_per_cm)
        union |= filled
    intervals = exclude_spans(intervals, list(not_core), px_per_cm)
    cuts: list[float] = []
    if layers.startswith("sam+fill+profile"):
        cuts = [c for iv in intervals for c in fracture_cuts(crop, union, iv, px_per_cm)]
        intervals = split_intervals(intervals, cuts, px_per_cm)
    if layers.endswith("+marks"):
        breaks = classify_breaks(crop, intervals, cuts, px_per_cm)
    else:
        breaks = default_breaks(intervals, cuts)
    return RowPieces(method, px_per_cm, intervals, cuts, breaks)
