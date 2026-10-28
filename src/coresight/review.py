"""Stage 5, review: a photo becomes a box the geologist checks, corrects and approves.

- ``analyze``: photo -> calibrate -> gate -> segment -> gate -> runs -> geometry.py ->
  describe, kept per run with every piece's place in the tray (for the overlay).
  The gate (gate.check_input) refuses a photo that is not a core tray, from the
  calibration confidence, Muse Spark's look at the whole photo and, after SAM,
  the SAM confidence: a screenshot is never measured.
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

import os
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
from coresight.gate import check_input
from coresight.geometry import IntervalLog
from coresight.meta_client import SamObject, SamPoint, sam_cache_key, sam_prompt
from coresight.pipeline import row_prompts
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
    GateReason,
    GateResult,
    GeologyDescription,
    Interval,
    IntervalResult,
    Measure,
    ReviewPiece,
    RunReview,
    TrayCheck,
    TrayView,
)
from coresight.segmentation import PROMPT as SAM_PROMPT
from coresight.segmentation import row_masks, run_markers, segment_row

MAX_PHOTO_SIDE_PX = 8000  # larger photos are refused before decoding them twice
# "fallback+": "stone", and Muse Spark's boxes for a row "stone" leaves empty (point B,
# chosen from outputs/eval/report.md)
SEGMENT_METHOD = os.getenv("CORESIGHT_SEGMENT_METHOD", "fallback+sam+fill+profile")
MODEL_NAMES = {"muse-spark-1.3": "Muse Spark 1.3"}


class ReviewError(ValueError):
    """Something the geologist can fix: shown on the page as it is written."""


@dataclass
class Analysis:
    tray: TrayView
    tray_jpg: bytes  # straightened tray, what the overlay is drawn on
    runs: list[RunReview]


PHOTO_FORMATS = "Upload a JPG, PNG or WebP photo of the core box."
_OTHER_FORMATS = [  # magic bytes of files people upload by mistake, and what to say
    ((b"GIF87a", b"GIF89a"), "a GIF"),
    ((b"%PDF",), "a PDF document"),
    ((b"II*\0", b"MM\0*"), "a TIFF file"),
    ((b"BM",), "a BMP file"),
]


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    """Width and height from the first SOF marker, without decoding the image."""
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h = int.from_bytes(data[i + 5 : i + 7], "big")
            w = int.from_bytes(data[i + 7 : i + 9], "big")
            return w, h
        i += 2 + length
    return None


def photo_size(data: bytes) -> tuple[int, int]:
    """Width and height of a JPG, PNG or WebP read from its header, before decoding.

    A small file can declare a huge image (a decompression bomb): the size is
    checked here so cv2 never allocates it. Anything else is refused with what
    it looks like, so the message says what to do.
    """
    if len(data) < 32 and data.startswith((b"\xff\xd8", b"\x89PNG", b"RIFF")) or not data:
        raise ReviewError(f"The file is empty or cut short. {PHOTO_FORMATS}")
    size = None
    if data[:3] == b"\xff\xd8\xff":
        size = _jpeg_size(data)
    elif data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        size = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        le = lambda a, b: int.from_bytes(data[a:b], "little")  # noqa: E731
        if chunk == b"VP8X":
            size = 1 + le(24, 27), 1 + le(27, 30)
        elif chunk == b"VP8 ":
            size = le(26, 28) & 0x3FFF, le(28, 30) & 0x3FFF
        elif chunk == b"VP8L":
            bits = le(21, 25)
            size = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    elif data[4:8] == b"ftyp":
        raise ReviewError("This is a HEIC photo (iPhone). Export it as JPG and upload it again.")
    else:
        for magics, what in _OTHER_FORMATS:
            if data.startswith(magics):
                msg = f"This is {what}, not a photo CoreSight can read. {PHOTO_FORMATS}"
                raise ReviewError(msg)
    if size is None:
        raise ReviewError(f"The photo could not be read. {PHOTO_FORMATS}")
    return size


def decode_photo(data: bytes) -> np.ndarray:
    w, h = photo_size(data)
    if max(w, h) > MAX_PHOTO_SIDE_PX:
        raise ReviewError(
            f"The photo is {w} x {h} px; the limit is {MAX_PHOTO_SIDE_PX} px on a side. "
            "Resize it (a phone photo at full size is fine)."
        )
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:  # the header was fine, the rest is damaged
        raise ReviewError(f"The photo is damaged and could not be read. {PHOTO_FORMATS}")
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

    def gate(self, result: GateResult) -> None: ...


def _tray_check(client, image: np.ndarray) -> TrayCheck | None:
    """Muse Spark's look at the whole photo; None without an answer (the other two decide)."""
    check = getattr(client, "check_tray", None)
    if check is None:
        return None
    try:
        return check(png_bytes(image))
    except Exception:  # an outage must not block a real tray: calibration and SAM still vote
        return None


def _gate(calibration: float, sam: float | None, spark: TrayCheck | None, report) -> None:
    result = check_input(calibration, sam, spark)
    report.gate(result)
    if not result.ok:
        stage = "calibration" if sam is None else "segmentation"
        report.stage(stage, status="failed", detail="Refused: not a measurable core tray")
        raise ReviewError(result.message)


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
        found = f"No core tray with {n_rows} rows was found, so the photo has no scale."
        msg = (f"{found} Take the photo from above with the whole tray in view, the slats"
               " visible and no strong glare.")  # fmt: skip
        reason = GateReason(signal="calibration", value=0.0, detail=found)
        report.gate(GateResult(ok=False, reasons=[reason], message=msg))  # the page says why
        raise ReviewError(msg) from exc
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
        detail=f"{len(tray.rows)} rows, {tray.px_per_cm:.1f} px per cm, "
               f"confidence {tray.confidence:.2f}",
    )  # fmt: skip
    spark = _tray_check(client, image)
    _gate(tray.confidence, None, spark, report)  # before SAM: a screenshot costs no SAM call

    # stage 2 as pipeline.segment, one row at a time so the page can follow it
    t, calls, cached, rows, found = time.perf_counter(), 0, 0, [], []
    crops = tray.row_crops(image)
    pieces, confidences, located = 0, [], 0
    for i, crop in enumerate(crops):
        report.stage(
            "segmentation", status="working", current=i, progress=i / len(crops),
            detail=f"Row {i + 1} of {len(crops)}",
        )  # fmt: skip
        hit = _sam_cached(client, crop)
        masks, not_core, spark_row = row_prompts(client, crop, SEGMENT_METHOD)
        calls, cached, located = calls + (not hit), cached + hit, located + spark_row
        report.masks(i, mask_overlay(masks, crop.shape[:2]))
        row = segment_row(crop, masks, tray.px_per_cm, SEGMENT_METHOD, not_core)
        rows.append(row)
        found += [Position(i, x / tray.px_per_cm) for x in run_markers(crop, tray.px_per_cm)]
        pieces += len(row.intervals_px)
        confidences += [m["confidence"] for m in masks if m["confidence"] is not None]
        mean = sum(confidences) / len(confidences) if confidences else 0
        report.stage(
            "segmentation", progress=(i + 1) / len(crops), calls=calls, cached=cached,
            detail=f"Row {i + 1} of {len(crops)}: {pieces} pieces, confidence {mean:.2f}"
                   + (", Muse Spark boxed the core" if spark_row else ""),
        )  # fmt: skip
    mean = sum(confidences) / len(confidences) if confidences else 0
    report.stage(
        "segmentation", status="done", progress=1, current=None, calls=calls, cached=cached,
        seconds=time.perf_counter() - t,
        detail=f"{pieces} pieces in {len(crops)} rows, confidence {mean:.2f}"
               + (f", {located} row{'s' if located > 1 else ''} boxed by Muse Spark"
                  if located else ""),
    )  # fmt: skip
    # no mask at all is SAM's "nothing here"; masks without a confidence say nothing
    sam = mean if confidences else (None if pieces else 0.0)
    _gate(tray.confidence, sam, spark, report)

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


# SAM with a click (point C): the geologist taps a piece, SAM 3.1 cuts it again.

MAX_POINTS = 8  # points of one piece: the first tap and the refining ones
MASK_MIN_COLUMN = 0.2  # a column is the piece's when the mask covers this share of its height
SNAP_CM = 1.0  # a mask end this close to a break the row already has is that break
_EPS_CM = 1e-6


@dataclass
class PointMask:
    """The piece SAM 3.1 cut at the geologist's points, measured on its mask."""

    row: int
    start_cm: float  # cm from the row start, from the mask's columns (not its box)
    end_cm: float
    confidence: float | None
    overlay: bytes  # see-through PNG of the mask over the row crop
    seconds: float


def sam_point_mask(
    client, tray_image: np.ndarray, view: TrayView, points: list[tuple[float, float, bool]]
) -> PointMask:
    """SAM 3.1 on one row with the geologist's points (x, y in tray px, positive or not).

    The row is the one under the first point, cropped from the straightened tray
    as in calibration.Tray.row_crops. The piece is the run of mask columns that
    holds the first positive point, so SAM's box (often wider) is not used.
    """
    if not points or not points[0][2]:
        raise ReviewError("Tap the piece first: the first point must be on the piece.")
    if len(points) > MAX_POINTS:
        raise ReviewError(f"Use at most {MAX_POINTS} points for one piece.")
    y = points[0][1]
    row = next((r for r, (y1, y2) in enumerate(view.rows) if y1 <= y < y2), None)
    if row is None:
        raise ReviewError("Tap on a row of core.")
    top, bottom = max(int(view.rows[row][0]), 0), int(np.ceil(view.rows[row][1]))
    crop = tray_image[top:bottom]
    h, w = crop.shape[:2]
    if any(not top <= py < bottom for _, py, _ in points):
        raise ReviewError("All the points of one piece must be in the same row.")
    prompt_points = tuple(
        SamPoint(min(max(px, 0), w - 1), min(max(py - top, 0), h - 1), positive)
        for px, py, positive in points
    )
    prompt = sam_prompt([SamObject(1, points=prompt_points)], (w, h))
    started = time.perf_counter()
    masks = [
        m
        for m in row_masks(client, crop, getattr(client, "cache_dir", None), prompt)
        if m["id"] == 1
    ]
    seconds = time.perf_counter() - started
    full = np.zeros((h, w), dtype=bool)
    for m in masks:
        left, mtop, right, mbottom = (int(v) for v in m["bounds"])
        part = m["mask"][: max(0, min(mbottom, h) - mtop), : max(0, min(right, w) - left)]
        full[mtop : mtop + part.shape[0], left : left + part.shape[1]] |= part
    cols = full.sum(axis=0)
    if cols.max() == 0:
        raise ReviewError("SAM found no piece there. Tap the middle of the piece, or use Split.")
    on = np.where(cols >= MASK_MIN_COLUMN * cols.max())[0]
    x0 = int(on[np.argmin(np.abs(on - prompt_points[0].x))])
    a = b = x0
    while a > 0 and cols[a - 1] >= MASK_MIN_COLUMN * cols.max():
        a -= 1
    while b < w - 1 and cols[b + 1] >= MASK_MIN_COLUMN * cols.max():
        b += 1
    confidences = [m["confidence"] for m in masks if m["confidence"] is not None]
    return PointMask(
        row=row,
        start_cm=a / view.px_per_cm,
        end_cm=(b + 1) / view.px_per_cm,
        confidence=max(confidences) if confidences else None,
        overlay=mask_overlay([{"bounds": (0, 0, w, h), "mask": full}], (h, w)),
        seconds=round(seconds, 2),
    )


def _span(p: ReviewPiece) -> str:
    return f"{p.start_cm:.1f}-{p.end_cm:.1f}"


def sam_piece_ready(box: BoxReview, i: int) -> None:
    """Refuse a tap before paying for SAM when the run cannot be corrected."""
    _run(box, i)


def sam_piece(
    box: BoxReview, i: int, cut: PointMask, n_points: int, refine: bool = False
) -> tuple[RunReview, bool]:
    """Make SAM's piece one piece of run i: breaks inside it go, its ends become breaks.

    So one tap fixes a missing break (the mask ends inside a piece) or an
    extra one (the mask runs over a break). Mask ends near a break the row
    already has snap to it. ``refine`` replaces the run's last SAM correction
    (the same piece, tapped again with more points). Returns the run and
    whether anything changed; geometry.py recomputes the numbers.
    """
    run = _run(box, i)
    last = run.corrections[-1] if run.corrections else None
    reverted = bool(refine and last and last.source == "sam-point" and last.pieces_before)
    if reverted:
        run.corrections.pop()
        run.pieces = list(last.pieces_before)
    before = list(run.pieces)
    r = cut.row
    # the run ends at its run blocks and where the neighbouring runs' pieces are
    mid = (cut.start_cm + cut.end_cm) / 2
    blocks = [x for row, x in (box.tray.markers if box.tray else []) if row == r]
    left = max(
        [p.end_cm for o in box.runs[:i] for p in o.pieces if p.row == r]
        + [x for x in blocks if x <= mid],
        default=0.0,
    )
    right = min(
        [p.start_cm for o in box.runs[i + 1 :] for p in o.pieces if p.row == r]
        + [x for x in blocks if x > mid],
        default=float("inf"),
    )
    a, b = max(cut.start_cm, left), min(cut.end_cm, right)
    if b - a < MIN_SPLIT_CM:
        raise ReviewError(f"That piece is not in run {i + 1}. Open the run it belongs to.")
    in_row = [p for p in run.pieces if p.row == r]
    ends = [v for p in in_row for v in (p.start_cm, p.end_cm)]

    def snap(v: float) -> float:
        near = min(ends, key=lambda e: abs(e - v), default=None)
        return near if near is not None and abs(near - v) <= SNAP_CM else v

    a, b = snap(a), snap(b)
    kept, touched, kind = [], [], "natural"
    for p in in_row:
        if p.end_cm <= a + _EPS_CM or p.start_cm >= b - _EPS_CM:
            kept.append(p)
            continue
        touched.append(p)
        if p.start_cm < a - _EPS_CM:
            kept.append(p.model_copy(update={"end_cm": a, "break_after": "natural"}))
        if p.end_cm > b + _EPS_CM:
            kept.append(p.model_copy(update={"start_cm": b}))
            kind = "natural"  # a new break at the mask's end
        else:
            kind = p.break_after
    piece = ReviewPiece(row=r, start_cm=a, end_cm=b, break_after=kind)
    new_row = sorted([*kept, piece], key=lambda p: p.start_cm)
    if new_row == in_row:
        if reverted:
            _after_pieces(run)
        return run, reverted
    others = [p for p in run.pieces if p.row != r]
    run.pieces = sorted([*others, *new_row], key=lambda p: (p.row, p.start_cm))
    _after_pieces(run)
    was = ", ".join(_span(p) for p in touched)
    run.corrections.append(
        Correction(
            at=_now(),
            target=f"row {r + 1}, {a:.1f}-{b:.1f} cm",
            original=f"{len(touched)} piece{'s' if len(touched) != 1 else ''}"
            + (f": {was} cm" if touched else ""),
            corrected=f"one piece {_span(piece)} cm from the SAM 3.1 mask"
            f" ({n_points} point{'s' if n_points != 1 else ''})",
            source="sam-point",
            pieces_before=before,
        )
    )
    return run, True


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
