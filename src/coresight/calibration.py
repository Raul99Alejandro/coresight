"""Stage 1, calibration: find core trays, straighten them and split the rows.

Classical computer vision only (OpenCV + numpy), no model calls.

How it works, on a copy of the photo reduced to ``WORK_WIDTH`` px:

1. Divider evidence. Slats between rows and the tray walls are smooth bands
   with straight edges across the whole tray. Per y: how far the colour
   variation along x dips below its surroundings, plus the strength of
   horizontal edges longer than 30% of the photo (painted lid tables, short
   text and rubble have none).
2. Comb. A tray is ``n_rows + 1`` equally spaced dividers. The pitch and the
   start that put a comb of that many teeth on the strongest evidence, and no
   evidence in the middle of the rows, win. This tolerates a divider that does
   not show (one hidden under a tape measure) and rows of very uniform core.
   Several trays are found one after another.
3. Lines. Each divider is fitted with a line through its valley in every
   vertical strip; positions are then regularised to equal spacing.
4. Straightening. The top and bottom dividers and the tray ends give four
   corners and a transform that removes tilt. All dividers share one slope,
   so strong perspective (converging slats) is not modelled: photos are
   expected from above, as core photos usually are.
5. Scale. px/cm along the core = straightened inner length of the tray /
   ``box_length_cm``. The tray ends are where the inner slats' edges stop.
   The tray length is a fixed property of the boxes a site uses, set once per
   site from a reference photo with a tape. The scale is only valid along the
   rows: some photos are stretched differently in height (the Kaggle set was
   straightened by its author), so the row pitch is never used as a scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

WORK_WIDTH = 1000
N_STRIPS = 12
BLUR_SIGMA = 4.0
SECOND_TRAY_MIN_SCORE = 0.6  # a further tray must score this fraction of the best


@dataclass(frozen=True)
class Row:
    """One row of core in the straightened tray, in straightened pixels."""

    index: int
    y1: float
    y2: float


@dataclass
class Tray:
    """A detected core tray.

    ``corners`` are top-left, top-right, bottom-right and bottom-left in the
    original photo, on the centre lines of the first and last divider.
    ``homography`` maps original pixels to straightened pixels, where the
    tray is ``width`` x ``height`` px.
    """

    corners: np.ndarray
    homography: np.ndarray
    width: int
    height: int
    px_per_cm: float  # along the rows (x) of the straightened tray
    rows: list[Row] = field(default_factory=list)

    def to_straight(self, points: np.ndarray) -> np.ndarray:
        """Map (N, 2) original-photo points into straightened tray pixels."""
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.homography).reshape(-1, 2)

    def row_index(self, x: float, y1: float, y2: float) -> int | None:
        """Row holding at least 80% of the vertical span y1..y2 (original px) at x."""
        top, bottom = self.to_straight(np.array([[x, y1], [x, y2]], dtype=float))[:, 1]
        for row in self.rows:
            if min(bottom, row.y2) - max(top, row.y1) >= 0.8 * (bottom - top):
                return row.index
        return None

    def straighten(self, image: np.ndarray) -> np.ndarray:
        return cv2.warpPerspective(image, self.homography, (self.width, self.height))

    def row_crops(self, image: np.ndarray) -> list[np.ndarray]:
        straight = self.straighten(image)
        return [straight[max(int(r.y1), 0) : int(np.ceil(r.y2))] for r in self.rows]


class CalibrationError(ValueError):
    """The photo does not show a tray the calibration can measure."""


def _lab(small: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(small, (0, 0), BLUR_SIGMA)
    return cv2.cvtColor(blurred, cv2.COLOR_BGR2LAB).astype(np.float32)


def _profile_y(lab: np.ndarray, x1: int, x2: int) -> np.ndarray:
    """Colour standard deviation along x, for every y, between x1 and x2."""
    return np.sqrt(lab[:, x1:x2].var(axis=1).sum(axis=1))


def _moving_max(values: np.ndarray, half: int) -> np.ndarray:
    if half <= 0:
        return values
    padded = np.pad(values, half, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half + 1)
    return windows.max(axis=1)


def _valley_depth(profile: np.ndarray, pitch: int) -> np.ndarray:
    """How far each y sits below the local average over one pitch (>= 0)."""
    kernel = np.ones(pitch) / pitch
    baseline = np.convolve(np.pad(profile, pitch, mode="edge"), kernel, mode="same")
    baseline = baseline[pitch:-pitch]
    return np.clip(baseline - profile, 0, None) / (np.median(profile) + 1e-6)


def _best_comb(
    profile: np.ndarray, edges: np.ndarray, n_rows: int, pitches: range, blocked: np.ndarray
) -> tuple[float, int, int]:
    """(score, pitch, start) of the comb whose teeth sit on smooth, straight-edged bands."""
    best = (0.0, 0, 0)
    n = len(profile)
    for pitch in pitches:
        span = n_rows * pitch
        if span >= n:
            break
        evidence = _valley_depth(profile, pitch) + edges
        evidence[blocked] = 0
        reach = _moving_max(evidence, max(1, round(0.08 * pitch)))
        starts = np.arange(n - span)
        teeth = sum(reach[starts + i * pitch] for i in range(n_rows + 1))
        # a valley in the middle of a row means the comb skipped a slat
        middles = sum(reach[starts + i * pitch + pitch // 2] for i in range(n_rows))
        score = teeth - middles
        i = int(np.argmax(score))
        if score[i] > best[0]:
            best = (float(score[i]), pitch, i)
    return best


def _fit_divider(
    lab: np.ndarray, y0: float, window: int, x_lo: int, x_hi: int
) -> tuple[float, float, float]:
    """(slope, y at x_lo, depth) of the divider valley near y0, from vertical strips."""
    lo = max(int(y0) - window, 0)
    hi = min(int(y0) + window + 1, lab.shape[0])
    edges = np.linspace(x_lo, x_hi, N_STRIPS + 1).astype(int)
    xs, ys, depths = [], [], []
    for a, b in zip(edges, edges[1:], strict=False):
        prof = _profile_y(lab[lo:hi], a, b)
        j = int(np.argmin(prof))
        xs.append((a + b) / 2 - x_lo)
        ys.append(lo + j)
        depths.append((np.median(prof) - prof[j]) / (np.median(prof) + 1e-6))
    xs_a, ys_a = np.array(xs), np.array(ys, dtype=float)
    keep = np.abs(ys_a - np.median(ys_a)) <= max(2.0, window / 3)
    if keep.sum() < 3:
        return 0.0, float(y0), 0.0
    slope, intercept = np.polyfit(xs_a[keep], ys_a[keep], 1)
    return float(slope), float(intercept), float(np.median(depths))


def _regular_dividers(fits: list[tuple[float, float, float]], pitch: int) -> np.ndarray:
    """Divider y at x_lo, forced to equal spacing; clear inner slats decide the fit.

    The first and last dividers are the tray's frame boards, thicker than a
    slat, so their centres are off the slat pitch: they only count when fewer
    than three slats show.
    """
    idx = np.arange(len(fits))
    ys = np.array([f[1] for f in fits])
    depths = np.array([f[2] for f in fits])
    keep = depths >= 0.3 * np.median(depths)
    inner = keep & (idx > 0) & (idx < len(fits) - 1)
    if inner.sum() >= 3:
        keep = inner
    for _ in range(3):
        step, start = np.polyfit(idx[keep], ys[keep], 1)
        resid = np.abs(ys - (start + step * idx))
        new_keep = keep & (resid <= max(1.5, 0.08 * pitch))
        if new_keep.sum() < 3 or new_keep.sum() == keep.sum():
            break
        keep = new_keep
    return start + step * idx


def _long_edge_map(gray: np.ndarray) -> np.ndarray:
    gy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    kernel = np.ones((1, int(0.3 * gray.shape[1])), np.uint8)
    return cv2.morphologyEx(gy, cv2.MORPH_OPEN, kernel)


def _tray_ends(
    gray: np.ndarray, ys: np.ndarray, slope: float, x_lo: int, band: int
) -> tuple[float, float]:
    """Inner wall x on each side: where the inner slats' edges stop.

    Slats run from wall to wall, so their straight horizontal edges are there
    at every x inside the tray, also next to empty stretches of floor. The
    side walls are vertical boards and the background beyond them has no edges
    at the slat heights, so the slat signal ends at the inner wall.
    """
    h, w = gray.shape
    gy = np.abs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    xs = np.arange(w)
    offsets = np.arange(-band, band + 1)
    signal = np.zeros(w)
    for y0 in ys[1:-1]:
        centre = np.round(y0 + slope * (xs - x_lo)).astype(int)
        rows = np.clip(centre[None, :] + offsets[:, None], 0, h - 1)
        signal += gy[rows, xs[None, :]].max(axis=0)
    smooth = np.convolve(signal, np.ones(9) / 9, mode="same")
    inside = smooth > 0.35 * np.median(smooth[w // 4 : 3 * w // 4])
    run = max(3, w // 100)  # the slat signal must be gone for 1% of the width
    left = right = None
    for x in range(w // 4, -1, -1):
        if not inside[max(x - run + 1, 0) : x + 1].any():
            left = x + run
            break
    for x in range(3 * w // 4, w):
        if not inside[x : x + run].any():
            right = x - 1
            break
    return float(left if left is not None else 0), float(right if right is not None else w - 1)


def find_trays(
    image: np.ndarray,
    box_length_cm: float,
    n_rows: int = 5,
    max_trays: int = 2,
) -> list[Tray]:
    """Detect up to ``max_trays`` trays of ``n_rows`` rows, top to bottom.

    ``box_length_cm`` is the inner length of the site's trays as this
    function measures it (see ``scripts/eval_calibration.py`` to set it).
    """
    if image is None or image.ndim != 3:
        raise CalibrationError("expected a colour image")
    if box_length_cm <= 0:
        raise ValueError("box_length_cm must be positive")
    h, w = image.shape[:2]
    k = WORK_WIDTH / w
    small = cv2.resize(image, (WORK_WIDTH, round(h * k)), interpolation=cv2.INTER_AREA)
    lab = _lab(small)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (0, 0), 1.2).astype(np.float32)
    x_lo, x_hi = int(0.1 * WORK_WIDTH), int(0.9 * WORK_WIDTH)
    profile = _profile_y(lab, x_lo, x_hi)
    edge_map = _long_edge_map(gray)
    edges = edge_map.mean(axis=1)
    edges = edges / (np.percentile(edges, 99) + 1e-6)
    sh = small.shape[0]
    pitches = range(max(6, sh // 60), sh // (n_rows + 1) + 1)

    combs = []
    blocked = np.zeros(sh, dtype=bool)
    for _ in range(max_trays):
        score, pitch, start = _best_comb(profile, edges, n_rows, pitches, blocked)
        if pitch == 0 or (combs and score < SECOND_TRAY_MIN_SCORE * combs[0][0]):
            break
        combs.append((score, pitch, start))
        blocked[max(start - pitch // 2, 0) : start + n_rows * pitch + pitch // 2] = True
    if not combs:
        raise CalibrationError(f"no tray with {n_rows} rows found")

    trays = []
    for _, pitch, start in sorted(combs, key=lambda c: c[2]):
        window = max(2, round(0.2 * pitch))
        fits = [_fit_divider(lab, start + i * pitch, window, x_lo, x_hi) for i in range(n_rows + 1)]
        ys = _regular_dividers(fits, pitch)
        slope = float(np.median([f[0] for f in fits]))
        left, right = _tray_ends(gray, ys, slope, x_lo, max(2, round(0.12 * pitch)))

        def at(x: float, y_at_lo: float, slope: float = slope) -> tuple[float, float]:
            return x, y_at_lo + slope * (x - x_lo)

        corners = (
            np.array([at(left, ys[0]), at(right, ys[0]), at(right, ys[-1]), at(left, ys[-1])]) / k
        )
        width = (
            np.linalg.norm(corners[1] - corners[0]) + np.linalg.norm(corners[2] - corners[3])
        ) / 2
        height = (
            np.linalg.norm(corners[3] - corners[0]) + np.linalg.norm(corners[2] - corners[1])
        ) / 2
        target = np.array([[0, 0], [width, 0], [width, height], [0, height]], dtype=np.float32)
        homography = cv2.getPerspectiveTransform(corners.astype(np.float32), target)
        row_px = height / n_rows
        tray = Tray(
            corners=corners,
            homography=homography,
            width=round(width),
            height=round(height),
            px_per_cm=width / box_length_cm,
            rows=[Row(i, i * row_px, (i + 1) * row_px) for i in range(n_rows)],
        )
        trays.append(tray)
    return trays
