"""Stage 5, review: a photo becomes a box the geologist checks, corrects and approves.

- ``analyze``: photo -> calibrate -> segment -> runs -> geometry.py -> describe,
  kept per run with every piece's place in the tray (for the overlay).
- ``set_break`` / ``remove_piece`` / ``split_piece``: piece corrections. RQD, TCR and FF are
  recomputed by geometry.log_interval (through runs.log_segment), never by a
  model, and the rule anomalies follow the new numbers.
- ``set_description``: a typed or dictated change to lithology, alteration,
  mineralization or the comment.

Every correction is appended to the run with the value it replaced, and the
machine log and description are kept untouched next to the corrected ones,
so the corrections can be evaluated (and later used for fine-tuning).
``ReviewStore`` keeps each box as one JSON file validated by schemas.BoxReview.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from coresight.anomalies import with_rule_anomalies
from coresight.calibration import CalibrationError, Tray, find_trays
from coresight.crops import run_crops
from coresight.describe import Describer, cache_key, describe_prompt, png_bytes
from coresight.geometry import IntervalLog
from coresight.meta_client import sam_cache_key
from coresight.runs import (
    LaidPiece,
    Position,
    RunMismatchError,
    log_segment,
    n_markers,
    run_segments,
    to_result,
)
from coresight.schemas import (
    BoxReview,
    BreakKind,
    Correction,
    DescriptionField,
    GeologyDescription,
    Interval,
    IntervalResult,
    Measure,
    ReviewPiece,
    RunReview,
    TrayView,
)
from coresight.segmentation import PROMPT as SAM_PROMPT
from coresight.segmentation import row_masks, run_markers, segment_row

MAX_PHOTO_SIDE_PX = 8000  # larger photos are refused before decoding them twice
SEGMENT_METHOD = "sam+fill+profile"  # as pipeline.segment
MODEL_NAMES = {"muse-spark-1.3": "Muse Spark 1.3"}


class ReviewError(ValueError):
    """Something the geologist can fix: shown on the page as it is written."""


@dataclass
class Analysis:
    tray: TrayView
    tray_jpg: bytes  # straightened tray, what the overlay is drawn on
    runs: list[RunReview]


def decode_photo(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ReviewError("The photo could not be read. Upload a JPG or PNG of the core box.")
    if max(image.shape[:2]) > MAX_PHOTO_SIDE_PX:
        raise ReviewError(f"The photo is larger than {MAX_PHOTO_SIDE_PX} px on a side.")
    if min(image.shape[:2]) < 400:
        raise ReviewError("The photo is too small to measure core pieces (under 400 px).")
    return image


def _laid(pieces: list[ReviewPiece]) -> list[LaidPiece]:
    return [
        (Position(p.row, p.start_cm), Position(p.row, p.end_cm), p.break_after) for p in pieces
    ]


def measure(log: IntervalLog) -> Measure:
    return Measure(
        run_length_cm=log.run_length_cm,
        recovered_cm=round(log.recovered_cm, 1),
        rqd_cm=round(log.rqd_cm, 1),
        intact_lengths_cm=[round(x, 1) for x in log.intact_piece_lengths_cm],
    )


def recompute(run: RunReview) -> IntervalResult:
    """The run's numbers from its current pieces, by geometry.py only (and their working)."""
    interval = Interval(from_m=run.from_m, to_m=run.to_m)
    log = log_segment(_laid(run.pieces), interval)
    run.measure = measure(log)
    return to_result(interval, log, run.machine_log.complete)


class Reporter:
    """Receives the analysis as it happens, so the page can show it live. Does nothing here."""

    def stage(self, key: str, **fields) -> None: ...

    def tray(self, view: TrayView, jpg: bytes) -> None: ...

    def masks(self, row: int, png: bytes) -> None: ...

    def crop(self, run: int, jpg: bytes) -> None: ...


MASK_MAX_WIDTH_PX = 1600


def mask_overlay(masks: list[dict], shape: tuple[int, int]) -> bytes:
    """SAM masks of one row as a see-through PNG of the row crop: one colour per object."""
    h, w = shape
    out = np.zeros((h, w, 4), np.uint8)
    for i, m in enumerate(masks):
        left, top, right, bottom = m["bounds"]
        full = np.zeros((h, w), np.uint8)
        mh, mw = max(min(bottom, h) - top, 0), max(min(right, w) - left, 0)
        part = m["mask"].astype(np.uint8)[:mh, :mw]
        full[top : top + part.shape[0], left : left + part.shape[1]] = part
        hue = int((0.72 + 0.11 * i) % 1.0 * 180)  # violet to pink, the colour of the models
        bgr = cv2.cvtColor(np.uint8([[[hue, 140, 255]]]), cv2.COLOR_HSV2BGR)[0, 0]
        b, g, r = (int(v) for v in bgr)
        out[full > 0] = (b, g, r, 105)
        contours, _ = cv2.findContours(full, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(out, contours, -1, (b, g, r, 255), max(2, w // 800))
    if w > MASK_MAX_WIDTH_PX:
        size = (MASK_MAX_WIDTH_PX, max(1, round(h * MASK_MAX_WIDTH_PX / w)))
        out = cv2.resize(out, size, interpolation=cv2.INTER_AREA)
    return cv2.imencode(".png", out)[1].tobytes()


def _jpg(image: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ReviewError("An image could not be encoded.")
    return buf.tobytes()


def _sam_cached(client, crop: np.ndarray) -> bool:
    """Whether SAM's answer for this row is already on disk (so no call is paid)."""
    cache = getattr(client, "cache_dir", None)
    if cache is None:
        return False
    key = sam_cache_key(cv2.imencode(".png", crop)[1].tobytes(), SAM_PROMPT)
    return (Path(cache) / "sam_masks" / f"{key}.npz").exists() or (
        Path(cache) / "sam" / f"{key}.txt"
    ).exists()


def _describe_cached(describer, png: bytes, ctx: dict) -> bool:
    cache = getattr(describer, "cache_dir", None)
    if cache is None:
        return False
    key = cache_key(describer.model, describe_prompt(ctx), png)
    return (Path(cache) / "describe" / describer.model / f"{key}.json").exists()


def analyze(
    photo: bytes,
    box_length_cm: float,
    runs: list[Interval],
    first_starts_in_box: bool,
    client,
    describer: Describer | None,
    tray_index: int = 0,
    markers: list[Position] | Callable[[Tray], list[Position]] | None = None,
    context: dict | None = None,
    report: Reporter | None = None,
    n_rows: int = 5,
) -> Analysis:
    """One photo end to end, ready for review.

    ``markers`` overrides the detected run markers, as in pipeline.log_box (or
    maps the tray to them). ``client`` segments (MetaClient: SAM 3.1).
    ``describer`` writes the descriptions; None skips them. A run whose
    description fails keeps its numbers and shows the error, so one bad answer
    does not lose the box. ``report`` hears every stage, row and run as it ends.
    """
    report = report or Reporter()
    if not runs:
        raise ReviewError("Add at least one run (from and to, in metres).")
    image = decode_photo(photo)

    t = time.perf_counter()
    report.stage("calibration", status="working")
    try:
        trays = find_trays(image, box_length_cm, n_rows=n_rows, max_trays=tray_index + 1)
    except CalibrationError as exc:
        report.stage("calibration", status="failed", detail=f"No tray with {n_rows} rows found")
        raise ReviewError(
            f"No core tray with {n_rows} rows was found, so the photo has no scale. Take the photo"
            " from above with the whole tray in view, the slats visible and no strong glare."
        ) from exc
    if tray_index >= len(trays):
        report.stage("calibration", status="failed", detail=f"Tray {tray_index + 1} not found")
        raise ReviewError(f"Tray {tray_index + 1} was not found in the photo.")
    tray = trays[tray_index]
    view = TrayView(
        width=tray.width,
        height=tray.height,
        px_per_cm=tray.px_per_cm,
        rows=[(r.y1, r.y2) for r in tray.rows],
        markers=[],
    )
    tray_jpg = _jpg(tray.straighten(image))
    report.tray(view, tray_jpg)
    report.stage(
        "calibration", status="done", progress=1, seconds=time.perf_counter() - t,
        detail=f"{len(tray.rows)} rows, {tray.px_per_cm:.1f} px per cm",
    )  # fmt: skip

    # stage 2 as pipeline.segment, one row at a time so the page can follow it
    t, calls, cached, rows, found = time.perf_counter(), 0, 0, [], []
    crops = tray.row_crops(image)
    pieces, confidences = 0, []
    for i, crop in enumerate(crops):
        report.stage(
            "segmentation", status="working", current=i, progress=i / len(crops),
            detail=f"Row {i + 1} of {len(crops)}",
        )  # fmt: skip
        hit = _sam_cached(client, crop)
        masks = row_masks(client, crop)
        calls, cached = calls + (not hit), cached + hit
        report.masks(i, mask_overlay(masks, crop.shape[:2]))
        row = segment_row(crop, masks, tray.px_per_cm, SEGMENT_METHOD)
        rows.append(row)
        found += [Position(i, x / tray.px_per_cm) for x in run_markers(crop, tray.px_per_cm)]
        pieces += len(row.intervals_px)
        confidences += [m["confidence"] or 0 for m in masks]
        mean = sum(confidences) / len(confidences) if confidences else 0
        report.stage(
            "segmentation", progress=(i + 1) / len(crops), calls=calls, cached=cached,
            detail=f"Row {i + 1} of {len(crops)}: {pieces} pieces, confidence {mean:.2f}",
        )  # fmt: skip
    mean = sum(confidences) / len(confidences) if confidences else 0
    report.stage(
        "segmentation", status="done", progress=1, current=None, calls=calls, cached=cached,
        seconds=time.perf_counter() - t,
        detail=f"{pieces} pieces in {len(crops)} rows, confidence {mean:.2f}",
    )  # fmt: skip

    if markers is None:
        markers = found
    elif callable(markers):  # measured on the photo, so they need the tray
        markers = markers(tray)
    view.markers = [(m.row, m.x_cm) for m in sorted(markers)]
    try:
        segments = run_segments(rows, markers, len(runs))
    except RunMismatchError as exc:
        report.stage("geometry", status="failed", detail="Run markers do not fit the run list")
        raise ReviewError(
            f"The photo shows {len(markers)} run markers but the box lists {len(runs)} runs"
            " (expected one marker fewer than the runs, or as many). Check the run list."
        ) from exc

    t = time.perf_counter()
    report.stage("geometry", status="working")
    out = []
    n = n_markers(markers, len(runs))
    for i, (run, laid) in enumerate(zip(runs, segments, strict=True)):
        complete = i < n and (i > 0 or first_starts_in_box)  # as runs.assign_runs
        interval_log = log_segment(laid, run)
        log = to_result(run, interval_log, complete)
        run_pieces = [
            ReviewPiece(row=a.row, start_cm=a.x_cm, end_cm=b.x_cm, break_after=kind)
            for a, b, kind in laid
            if b.x_cm > a.x_cm
        ]
        out.append(
            RunReview(
                from_m=run.from_m, to_m=run.to_m, pieces=run_pieces,
                measure=measure(interval_log), machine_log=log, log=log,
            )  # fmt: skip
        )
    report.stage(
        "geometry", status="done", progress=1, seconds=time.perf_counter() - t,
        detail=f"RQD, TCR and fracture frequency for {len(runs)} run{'s' if len(runs) > 1 else ''}",
    )  # fmt: skip

    if describer is None:
        report.stage("description", status="done", progress=1, detail="Skipped")
        return Analysis(tray=view, tray_jpg=tray_jpg, runs=out)
    t, calls, cached = time.perf_counter(), 0, 0
    report.stage("description", name=MODEL_NAMES.get(describer.model, describer.model))
    run_images = run_crops(image, tray, markers, len(runs))
    for i, (review, crop) in enumerate(zip(out, run_images, strict=True)):
        report.stage(
            "description", status="working", current=i, progress=i / len(out),
            detail=f"Run {i + 1} of {len(out)}",
        )  # fmt: skip
        report.crop(i, _jpg(crop, 80))
        ctx = {**(context or {}), "from_m": review.from_m, "to_m": review.to_m}
        png = png_bytes(crop)
        hit = _describe_cached(describer, png, ctx)
        started = time.perf_counter()
        try:
            d = with_rule_anomalies(describer.describe_interval(png, ctx), review.log)
            review.machine_description = review.description = d
            review.description_backend = describer.model
        except Exception as exc:  # shown per run; the numbers are still good
            review.description_error = f"{type(exc).__name__}: {exc}"[:300]
        review.description_seconds = round(time.perf_counter() - started, 2)
        calls, cached = calls + (not hit), cached + hit
        report.stage("description", calls=calls, cached=cached, progress=(i + 1) / len(out))
    failed = sum(r.description is None for r in out)
    detail = f"{len(out) - failed} of {len(out)} run{'s' if len(out) > 1 else ''} described"
    report.stage(
        "description", status="done", progress=1, current=None, calls=calls, cached=cached,
        seconds=time.perf_counter() - t,
        detail=detail + (f", {failed} without an answer" if failed else ""),
    )  # fmt: skip
    return Analysis(tray=view, tray_jpg=tray_jpg, runs=out)


def _now() -> datetime:
    return datetime.now(UTC)


def _run(box: BoxReview, i: int) -> RunReview:
    if box.status != "ready":
        raise ReviewError(f"The box is {box.status}; only a box under review can be corrected.")
    if not 0 <= i < len(box.runs):
        raise ReviewError(f"Run {i + 1} does not exist.")
    return box.runs[i]


def _after_pieces(run: RunReview) -> None:
    run.log = recompute(run)
    if run.description is not None:
        run.description = with_rule_anomalies(run.description, run.log)


def set_break(box: BoxReview, i: int, j: int, kind: BreakKind) -> RunReview:
    """Change the kind of break after piece j of run i (mechanical rejoins the pieces)."""
    run = _run(box, i)
    if not 0 <= j < len(run.pieces) - 1:
        raise ReviewError("Only a break between two pieces of the run can be changed.")
    old = run.pieces[j].break_after
    if old == kind:
        return run
    run.pieces[j] = run.pieces[j].model_copy(update={"break_after": kind})
    _after_pieces(run)
    run.corrections.append(
        Correction(at=_now(), target=f"break {j + 1}", original=old, corrected=kind)
    )
    return run


def remove_piece(box: BoxReview, i: int, j: int) -> RunReview:
    """Drop piece j of run i: something that is not core (a block, a chip, a label)."""
    run = _run(box, i)
    if not 0 <= j < len(run.pieces):
        raise ReviewError(f"Piece {j + 1} does not exist.")
    p = run.pieces.pop(j)
    _after_pieces(run)
    run.corrections.append(
        Correction(
            at=_now(),
            target=f"piece {j + 1}",
            original=f"row {p.row + 1}, {p.start_cm:.1f}-{p.end_cm:.1f} cm",
            corrected="removed",
        )
    )
    return run


MIN_SPLIT_CM = 0.5


def split_piece(
    box: BoxReview, i: int, j: int, at_cm: float, kind: BreakKind = "natural"
) -> RunReview:
    """Cut piece j of run i at ``at_cm`` (cm from the row start): a break SAM missed."""
    run = _run(box, i)
    if not 0 <= j < len(run.pieces):
        raise ReviewError(f"Piece {j + 1} does not exist.")
    p = run.pieces[j]
    if not p.start_cm + MIN_SPLIT_CM <= at_cm <= p.end_cm - MIN_SPLIT_CM:
        raise ReviewError(
            f"Cut piece {j + 1} between {p.start_cm + MIN_SPLIT_CM:.1f} and"
            f" {p.end_cm - MIN_SPLIT_CM:.1f} cm."
        )
    run.pieces[j : j + 1] = [
        p.model_copy(update={"end_cm": at_cm, "break_after": kind}),
        p.model_copy(update={"start_cm": at_cm}),
    ]
    _after_pieces(run)
    run.corrections.append(
        Correction(
            at=_now(),
            target=f"piece {j + 1}",
            original=f"row {p.row + 1}, {p.start_cm:.1f}-{p.end_cm:.1f} cm",
            corrected=f"split at {at_cm:.1f} cm ({kind} break)",
        )
    )
    return run


def set_description(
    box: BoxReview,
    i: int,
    field: DescriptionField,
    value: str,
    source: str = "typed",
    transcript: str | None = None,
) -> RunReview:
    """A typed or dictated change to one description field of run i."""
    run = _run(box, i)
    value = value.strip()
    if field == "comment":
        old, run.comment = run.comment, value
    else:
        if field == "lithology" and not value:
            raise ReviewError("Lithology cannot be empty.")
        d = run.description or GeologyDescription(
            lithology="-", alteration="", mineralization="", confidence=1.0
        )
        old = getattr(run.description, field) if run.description else ""
        run.description = with_rule_anomalies(d.model_copy(update={field: value}), run.log)
    if old == value:
        return run
    run.corrections.append(
        Correction(
            at=_now(),
            target=field,
            original=old,
            corrected=value,
            source=source,
            transcript=transcript,
        )
    )
    return run


def approve(box: BoxReview) -> BoxReview:
    if box.status != "ready":
        raise ReviewError(f"The box is {box.status}; only a box under review can be approved.")
    missing = [i + 1 for i, r in enumerate(box.runs) if r.description is None]
    if missing:
        raise ReviewError(f"Write a lithology for run(s) {missing} before approving.")
    box.status, box.approved_at = "approved", _now()
    return box


class ReviewStore:
    """One JSON file per box (schemas.BoxReview) and its tray image, in ``root``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _json(self, box_id: str) -> Path:
        if not box_id.isalnum():
            raise KeyError(box_id)
        return self.root / f"{box_id}.json"

    def tray_path(self, box_id: str) -> Path:
        return self._json(box_id).with_suffix(".jpg")

    def file_path(self, box_id: str, name: str) -> Path:
        """An image that belongs to a box: SAM masks of a row, the crop of a run."""
        if not name.replace(".", "").isalnum():
            raise KeyError(name)
        return self.root / f"{self._json(box_id).stem}_{name}"

    def save_file(self, box_id: str, name: str, data: bytes) -> None:
        self.file_path(box_id, name).write_bytes(data)

    def get(self, box_id: str) -> BoxReview:
        path = self._json(box_id)
        if not path.exists():
            raise KeyError(box_id)
        return BoxReview.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, box: BoxReview) -> None:
        with self._lock:
            path = self._json(box.id)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(box.model_dump_json(indent=1), encoding="utf-8")
            for attempt in range(5):  # Windows refuses while a reader has the file open
                try:
                    tmp.replace(path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.05)

    def save_tray(self, box_id: str, jpg: bytes) -> None:
        self.tray_path(box_id).write_bytes(jpg)

    def all(self) -> list[BoxReview]:
        paths = self.root.glob("*.json")
        boxes = [BoxReview.model_validate_json(p.read_text("utf-8")) for p in paths]
        return sorted(boxes, key=lambda b: b.created_at, reverse=True)
