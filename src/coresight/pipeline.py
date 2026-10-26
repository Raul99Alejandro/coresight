"""End-to-end pipeline: core box photo -> reviewed interval log.

Stages still marked NotImplemented are waiting for their day in docs/PLAN.md.
``log_box`` runs what exists end to end: photo -> calibrate -> segment -> runs
-> geometry.py, and returns validated IntervalResult rows.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import Tray, find_trays
from coresight.meta_client import MetaClient
from coresight.runs import Position, assign_runs, to_result
from coresight.schemas import Interval, IntervalResult
from coresight.segmentation import RowPieces, row_masks, run_markers, segment_row


def calibrate(image_path: Path, box_length_cm: float, n_rows: int = 5) -> list[Tray]:
    """Find the trays in a photo: straightened geometry, px->cm along the rows, rows.

    ``box_length_cm`` is the site's tray length (see coresight.calibration).
    Checked by scripts/eval_calibration.py (error < 2% on the labelled boxes).
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    return find_trays(image, box_length_cm, n_rows=n_rows)


def segment(
    image: np.ndarray, tray: Tray, client: MetaClient, method: str = "sam+fill+profile"
) -> tuple[list[RowPieces], list[Position]]:
    """Pieces of every row of a tray (SAM 3.1 + rules) and the run markers found."""
    rows, markers = [], []
    for i, crop in enumerate(tray.row_crops(image)):
        rows.append(segment_row(crop, row_masks(client, crop), tray.px_per_cm, method))
        markers += [Position(i, x / tray.px_per_cm) for x in run_markers(crop, tray.px_per_cm)]
    return rows, markers


def build_logs(
    rows: list[RowPieces],
    markers: list[Position],
    runs: list[Interval],
    first_starts_in_box: bool,
) -> list[IntervalResult]:
    """RQD, TCR and fracture frequency per run, all from geometry.log_interval."""
    return [to_result(*r) for r in assign_runs(rows, markers, runs, first_starts_in_box)]


def log_box(
    image_path: Path,
    box_length_cm: float,
    runs: list[Interval],
    client: MetaClient,
    first_starts_in_box: bool,
    tray_index: int = 0,
    markers: list[Position] | None = None,
    method: str = "sam+fill+profile",
) -> list[IntervalResult]:
    """One photo end to end. ``markers`` overrides the detected run markers
    (for boxes whose run blocks are not the magenta foam the detector knows)."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    tray = find_trays(image, box_length_cm, max_trays=tray_index + 1)[tray_index]
    rows, found = segment(image, tray, client, method)
    return build_logs(rows, found if markers is None else markers, runs, first_starts_in_box)


def describe(image_path: Path, logs):
    """Attach Muse Spark descriptions and anomaly flags to each interval.

    Day 6.
    """
    raise NotImplementedError("day 6: descriptions")


def export_csv(logs, out_path: Path) -> Path:
    """Write the approved log to CSV for geological modelling software.

    Day 7.
    """
    raise NotImplementedError("day 7: review UI and CSV export")


def draft_handoffs(approved_logs):
    """Draft the assay request (lab) and ground-condition alert (safety).

    Drafts only. Nothing is sent without human approval. Day 8.
    """
    raise NotImplementedError("day 8: handoffs")
