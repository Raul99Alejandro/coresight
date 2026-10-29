"""Refuse a photo that is not a measurable core tray before anything is measured."""

from __future__ import annotations

from coresight.schemas import GateReason, GateResult, TrayCheck

MIN_CALIBRATION = 0.5  # below this there is no trustworthy scale in cm
# below this a person checks the rows before any number is shown: the public trays we
# calibrate well score 1.00; NTS 1981 (cut to 3.5 of its rows) 0.68, the others 0.51 to 0.78
SURE_CALIBRATION = 0.9
MIN_SAM = 0.3  # below this SAM found no core piece it is sure of
SPARK_SURE = 0.5  # a "not a tray" at or above this refuses the photo on its own
WEAK_CALIBRATION = 0.7  # below this an unsure Spark "not a tray" counts
WEAK_SAM = 0.5  # below this an unsure Spark "not a tray" counts

ADVICE = (
    "Upload one photo of a core tray taken from above, with the whole tray, its slats "
    "and both ends in view."
)


def _spark_reason(
    spark: TrayCheck | None, calibration: float, sam: float | None
) -> GateReason | None:
    if spark is None or spark.is_core_tray:
        return None
    if spark.confidence < SPARK_SURE:
        other_weak = calibration < WEAK_CALIBRATION or (sam is not None and sam < WEAK_SAM)
        if not other_weak:
            return None
    return GateReason(
        signal="spark",
        value=spark.confidence,
        detail=f"Muse Spark says this is not a core tray: {spark.what_it_shows}.",
    )


def _calibration_reason(calibration: float) -> GateReason | None:
    if calibration >= MIN_CALIBRATION:
        return None
    return GateReason(
        signal="calibration",
        value=calibration,
        detail=(
            f"No tray slats were found (calibration confidence {calibration:.2f}), "
            "so there is no scale to measure in cm."
        ),
    )


def _calibration_doubt(calibration: float) -> GateReason | None:
    if not MIN_CALIBRATION <= calibration < SURE_CALIBRATION:
        return None
    return GateReason(
        signal="calibration",
        value=calibration,
        detail=(
            f"The tray slats were found, but not clearly (calibration confidence "
            f"{calibration:.2f}): the rows may be cut wrong, so check them before any number."
        ),
    )


def _segmentation_reason(sam: float | None) -> GateReason | None:
    if sam is None or sam >= MIN_SAM:
        return None
    return GateReason(
        signal="segmentation",
        value=sam,
        detail=f"SAM 3.1 found no core pieces it is sure of (confidence {sam:.2f}).",
    )


def check_input(calibration: float, sam: float | None, spark: TrayCheck | None) -> GateResult:
    if not 0 <= calibration <= 1:
        raise ValueError(f"calibration {calibration} is outside 0 to 1")
    if sam is not None and not 0 <= sam <= 1:
        raise ValueError(f"sam {sam} is outside 0 to 1")
    reasons = [
        reason
        for reason in (
            _spark_reason(spark, calibration, sam),
            _calibration_reason(calibration),
            _segmentation_reason(sam),
        )
        if reason is not None
    ]
    if not reasons:
        doubt = _calibration_doubt(calibration)
        return GateResult(ok=True, doubts=[doubt] if doubt else [])
    message = " ".join([*(r.detail for r in reasons), ADVICE])
    return GateResult(ok=False, reasons=reasons, message=message)
