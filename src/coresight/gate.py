"""Refuse a photo that is not a measurable core tray before anything is measured."""

from __future__ import annotations

from coresight.schemas import GateReason, GateResult, TrayCheck

MIN_CALIBRATION = 0.5  # below this there is no trustworthy scale in cm
MIN_SAM = 0.3  # below this SAM found no core piece it is sure of
SPARK_SURE = 0.5  # a "not a tray" at or above this refuses the photo on its own
WEAK_CALIBRATION = 0.7  # below this an unsure Spark "not a tray" counts
WEAK_SAM = 0.5  # below this an unsure Spark "not a tray" counts

_ADVICE = (
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
        return GateResult(ok=True)
    message = " ".join([*(r.detail for r in reasons), _ADVICE])
    return GateResult(ok=False, reasons=reasons, message=message)
