"""End-to-end pipeline: core box photo -> reviewed interval log.

Each stage is a stub until its day in docs/PLAN.md.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from coresight.calibration import Tray, find_trays


def calibrate(image_path: Path, box_length_cm: float, n_rows: int = 5) -> list[Tray]:
    """Find the trays in a photo: straightened geometry, px->cm along the rows, rows.

    ``box_length_cm`` is the site's tray length (see coresight.calibration).
    Checked by scripts/eval_calibration.py (error < 2% on the labelled boxes).
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    return find_trays(image, box_length_cm, n_rows=n_rows)


def segment(rows):
    """Run SAM 3.1 on each row and convert masks to Piece objects in cm.

    Day 4. Fallback for thin fractures: intensity profile along the core axis.
    """
    raise NotImplementedError("day 4: segmentation")


def build_logs(pieces_by_run, runs):
    """Call geometry.log_interval for each run (RQD/TCR/FF per interval).

    Day 5.
    """
    raise NotImplementedError("day 5: geometry wiring")


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
