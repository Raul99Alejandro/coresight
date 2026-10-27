"""The picture of one run, cut from the straightened tray.

A run lies between two run markers (the same markers that split the pieces in
coresight.runs). When it fills several tray rows, the slice of each row is
stacked under the previous one, so the model sees the run in reading order.
"""

from __future__ import annotations

import cv2
import numpy as np

from coresight.calibration import Tray
from coresight.runs import Position, dedupe_markers

ROW_GAP_PX = 12  # dark band between stacked rows, so the model sees where a row ends
MIN_SLICE_CM = 1.0


def run_spans(markers: list[Position], n_runs: int) -> list[tuple[Position, Position]]:
    """(start, end) along the laid-out core for every run, split at the markers.

    Same convention as runs.assign_runs: run i lies between marker i - 1 (or
    the start of the first row) and marker i (or the end of the last row).
    """
    markers = sorted(markers)
    if len(markers) > n_runs:
        markers = dedupe_markers(markers)
    edges = [Position(0, 0.0), *markers, Position(10**6, float("inf"))]
    return list(zip(edges, edges[1:], strict=False))[:n_runs]


def run_crop(
    rows: list[np.ndarray], px_per_cm: float, start: Position, end: Position
) -> np.ndarray:
    """Pixels of the core between ``start`` and ``end``, one slice per row, stacked."""
    slices = []
    for r, row in enumerate(rows):
        if r < start.row or r > end.row:
            continue
        x0 = start.x_cm * px_per_cm if r == start.row else 0.0
        x1 = min(end.x_cm * px_per_cm, row.shape[1]) if r == end.row else row.shape[1]
        if x1 - x0 >= MIN_SLICE_CM * px_per_cm:
            slices.append(row[:, int(x0) : int(np.ceil(x1))])
    if not slices:
        raise ValueError(f"no core between {start} and {end}")
    width = max(s.shape[1] for s in slices)
    out = []
    for i, s in enumerate(slices):
        if i:
            out.append(np.zeros((ROW_GAP_PX, width, 3), dtype=s.dtype))
        out.append(cv2.copyMakeBorder(s, 0, 0, 0, width - s.shape[1], cv2.BORDER_CONSTANT, 0))
    return np.vstack(out)


def run_crops(
    image: np.ndarray, tray: Tray, markers: list[Position], n_runs: int
) -> list[np.ndarray]:
    rows = tray.row_crops(image)
    return [run_crop(rows, tray.px_per_cm, a, b) for a, b in run_spans(markers, n_runs)]
