"""End-to-end pipeline: core box photo -> reviewed interval log.

``log_box`` runs photo -> calibrate -> segment -> runs -> geometry.py and
returns validated IntervalResult rows; ``describe`` adds one validated
description per run (Muse Spark or Glimmer, same contract). The review of a
box (corrections, approval) lives in coresight.review; ``export_csv`` writes
the reviewed log.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import cv2
import numpy as np

from coresight.anomalies import with_rule_anomalies
from coresight.calibration import Tray, find_trays
from coresight.crops import run_crops
from coresight.describe import Describer, png_bytes
from coresight.meta_client import MetaClient
from coresight.runs import Position, assign_runs, to_result
from coresight.schemas import (
    BoxReview,
    GeologyDescription,
    Interval,
    IntervalDescription,
    IntervalResult,
)
from coresight.segmentation import (
    FALLBACK,
    SPARK,
    RowPieces,
    located_masks,
    row_masks,
    run_markers,
    segment_row,
)


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
    """Pieces of every row of a tray (SAM 3.1 + rules) and the run markers found.

    A ``spark+`` method prompts SAM with Muse Spark's boxes instead of "stone";
    a ``fallback+`` method does so only for a row where "stone" finds nothing.
    """
    rows, markers = [], []
    for i, crop in enumerate(tray.row_crops(image)):
        masks, not_core, _ = row_prompts(client, crop, method)
        rows.append(segment_row(crop, masks, tray.px_per_cm, method, not_core))
        markers += [Position(i, x / tray.px_per_cm) for x in run_markers(crop, tray.px_per_cm)]
    return rows, markers


def row_prompts(
    client: MetaClient, crop: np.ndarray, method: str
) -> tuple[list[dict], list[tuple[float, float]], bool]:
    """SAM masks of one row for ``method``, the x spans that are not core, and whether
    Muse Spark localized the row (``spark+`` always, ``fallback+`` when "stone" found nothing)."""
    masks = [] if method.startswith(SPARK) else row_masks(client, crop)
    if method.startswith(SPARK) or (method.startswith(FALLBACK) and not masks):
        return *located_masks(client, crop), True
    return masks, [], False


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


def detect_markers(image: np.ndarray, tray: Tray) -> list[Position]:
    """Run markers (magenta foam blocks) of a tray, without calling SAM."""
    return [
        Position(i, x / tray.px_per_cm)
        for i, crop in enumerate(tray.row_crops(image))
        for x in run_markers(crop, tray.px_per_cm)
    ]


def describe_runs(
    image: np.ndarray,
    tray: Tray,
    markers: list[Position],
    logs: list[IntervalResult],
    describer: Describer,
    context: dict | None = None,
) -> list[IntervalDescription]:
    """One description per run: the run's crop to the backend, then the rule anomalies.

    ``logs`` come from build_logs with the same markers, so crop i is run i.
    """
    out = []
    for log, crop in zip(logs, run_crops(image, tray, markers, len(logs)), strict=True):
        ctx = {**(context or {}), "from_m": log.from_m, "to_m": log.to_m}
        description = describer.describe_interval(png_bytes(crop), ctx)
        out.append(
            IntervalDescription(
                from_m=log.from_m,
                to_m=log.to_m,
                backend=describer.model,
                description=with_rule_anomalies(description, log),
            )
        )
    return out


def describe(
    image_path: Path,
    logs: list[IntervalResult],
    describer: Describer,
    box_length_cm: float,
    tray_index: int = 0,
    markers: list[Position] | None = None,
    context: dict | None = None,
) -> list[IntervalDescription]:
    """Descriptions and anomaly flags for the runs of one photo (Muse Spark or Glimmer).

    Lithology, alteration, mineralization and visible sulfides come from the
    model; low recovery and intense fracturing from the logs (geometry.py).
    ``markers`` overrides the detected run markers, as in log_box.
    """
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    tray = find_trays(image, box_length_cm, max_trays=tray_index + 1)[tray_index]
    if markers is None:
        markers = detect_markers(image, tray)
    return describe_runs(image, tray, markers, logs, describer, context)


def describe_photo(image_path: Path, describer: Describer, context: dict) -> GeologyDescription:
    """A close-up with no tray to measure: the whole photo, no rule anomalies."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(image_path)
    return describer.describe_interval(png_bytes(image), context)


CSV_COLUMNS = [
    "hole_id", "box", "from_m", "to_m", "complete", "rqd_pct", "tcr_pct", "natural_fractures",
    "fracture_frequency_per_m", "rock_quality", "uncertain_breaks", "mechanical_breaks",
    "lithology", "alteration", "mineralization", "anomalies", "comment", "corrections",
    "description_backend", "status",
]  # fmt: skip


def export_csv(box: BoxReview) -> str:
    """The reviewed log of one box as CSV for geological modelling software.

    One row per run; numbers are the corrected ones (geometry.py), and
    ``corrections`` counts the geologist's changes to that run.
    """
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for run in box.runs:
        d = run.description
        writer.writerow(
            {
                "hole_id": box.hole_id,
                "box": box.box_number,
                **run.log.model_dump(include=set(CSV_COLUMNS)),
                "lithology": d.lithology if d else "",
                "alteration": d.alteration if d else "",
                "mineralization": d.mineralization if d else "",
                "anomalies": "; ".join(f"{a.type}: {a.explanation}" for a in d.anomalies)
                if d
                else "",
                "comment": run.comment,
                "corrections": len(run.corrections),
                "description_backend": run.description_backend or "",
                "status": box.status,
            }
        )
    return out.getvalue()


def draft_handoffs(box: BoxReview, history: list[BoxReview]):
    """Stage 6: the orchestrator and area agents on an approved box (coresight.agents).

    Drafts only, each checked by verify.py. Nothing is sent without human approval.
    """
    from coresight import agents
    from coresight.verify import verify

    return agents.draft_handoffs(box, history, MetaClient(), verify)
