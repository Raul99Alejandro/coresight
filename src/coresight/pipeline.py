"""End-to-end pipeline: core box photo -> reviewed interval log.

Each stage is a stub until its day in docs/PLAN.md.
"""

from __future__ import annotations

from pathlib import Path


def calibrate(image_path: Path):
    """Detect box edges and scale markers, return px->cm scale and row crops.

    Day 3. Done when the px->cm error is below 2% on the labelled boxes.
    """
    raise NotImplementedError("day 3: calibration")


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
