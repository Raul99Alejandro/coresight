"""The input gate (gate.py): the spec Muse Code builds the rule against.

Three signals decide whether a photo is measured at all:
- calibration: how clearly calibration.py found the tray slats (0 to 1). Below
  0.5 there is no trustworthy scale, so no length in cm can be measured.
- sam: the mean SAM 3.1 mask confidence of the rows (0 to 1), or None before
  SAM has run (the gate runs once before SAM, to save the call, and once after).
- spark: Muse Spark's TrayCheck of the whole photo, or None when Spark did not
  answer. A missing answer never refuses a photo on its own.

Values measured on real photos (docs/ANALISIS-2.md): core trays give
calibration 1.0 and SAM 0.69 to 0.74; a screenshot of a web page gave
calibration 0.0, SAM 0.00 and Spark "not a tray" with confidence 1.0;
close-ups of core pieces without a tray give calibration about 0.2.
"""

import pytest

from coresight.gate import check_input
from coresight.schemas import GateResult, TrayCheck

ADVICE = (
    "Upload one photo of a core tray taken from above, with the whole tray, its slats "
    "and both ends in view."
)


def tray(yes: bool, what: str, confidence: float) -> TrayCheck:
    return TrayCheck(is_core_tray=yes, what_it_shows=what, confidence=confidence)


TRAY = tray(True, "a core tray with five rows of core", 0.95)


def signals(result: GateResult) -> list[str]:
    return [r.signal for r in result.reasons]


def test_a_core_tray_passes():
    result = check_input(1.0, 0.74, TRAY)
    assert result == GateResult(ok=True, reasons=[], message="")


def test_a_core_tray_passes_before_sam_runs():
    assert check_input(1.0, None, TRAY).ok


def test_a_web_screenshot_is_refused_by_spark_and_calibration():
    shot = tray(False, "a screenshot of a web page with icons", 1.0)
    result = check_input(0.0, None, shot)
    assert not result.ok
    assert signals(result) == ["spark", "calibration"]
    assert result.reasons[0].value == 1.0 and result.reasons[1].value == 0.0
    assert result.message == (
        "Muse Spark says this is not a core tray: a screenshot of a web page with icons. "
        "No tray slats were found (calibration confidence 0.00), so there is no scale to "
        "measure in cm. " + ADVICE
    )


def test_after_sam_all_three_signals_are_reported_in_order():
    shot = tray(False, "a screenshot of a web page with icons", 1.0)
    result = check_input(0.0, 0.0, shot)
    assert signals(result) == ["spark", "calibration", "segmentation"]
    assert (
        result.reasons[2].detail == "SAM 3.1 found no core pieces it is sure of (confidence 0.00)."
    )


def test_a_selfie_is_refused():
    selfie = tray(False, "a person's face, a selfie", 0.97)
    result = check_input(0.12, None, selfie)
    assert not result.ok
    assert signals(result) == ["spark", "calibration"]
    assert (
        result.reasons[0].detail
        == "Muse Spark says this is not a core tray: a person's face, a selfie."
    )
    assert result.message.endswith(ADVICE)


def test_core_without_a_tray_has_no_scale_and_is_refused():
    closeup = tray(True, "a close-up of two pieces of drill core", 0.8)
    result = check_input(0.17, None, closeup)
    assert not result.ok
    assert signals(result) == ["calibration"]
    assert result.reasons[0].detail == (
        "No tray slats were found (calibration confidence 0.17), so there is no scale to "
        "measure in cm."
    )
    assert result.message == result.reasons[0].detail + " " + ADVICE


def test_low_sam_confidence_alone_refuses():
    result = check_input(1.0, 0.29, TRAY)
    assert signals(result) == ["segmentation"]
    assert result.reasons[0].value == 0.29
    assert result.message == (
        "SAM 3.1 found no core pieces it is sure of (confidence 0.29). " + ADVICE
    )


def test_thresholds_are_inclusive():
    assert check_input(0.5, 0.3, TRAY).ok
    assert not check_input(0.49, 0.3, TRAY).ok
    assert not check_input(0.5, 0.29, TRAY).ok


def test_spark_sure_it_is_not_a_tray_refuses_even_with_good_numbers():
    result = check_input(1.0, 0.9, tray(False, "a stack of bricks", 0.6))
    assert signals(result) == ["spark"]


def test_spark_unsure_counts_only_when_another_signal_is_weak():
    unsure = tray(False, "maybe rocks on a table", 0.4)
    assert check_input(0.9, None, unsure).ok
    assert check_input(0.9, 0.6, unsure).ok
    assert signals(check_input(0.6, None, unsure)) == ["spark"]  # calibration below 0.7
    assert signals(check_input(0.9, 0.45, unsure)) == ["spark"]  # SAM below 0.5


def test_spark_saying_it_is_a_tray_never_refuses():
    assert check_input(0.5, 0.3, tray(True, "a core tray", 0.1)).ok


def test_without_spark_the_other_two_decide():
    assert check_input(1.0, 0.7, None).ok
    assert signals(check_input(0.2, None, None)) == ["calibration"]
    assert signals(check_input(0.2, 0.1, None)) == ["calibration", "segmentation"]


@pytest.mark.parametrize("calibration, sam", [(-0.1, None), (1.1, None), (0.5, -0.01), (0.5, 1.5)])
def test_confidences_outside_0_to_1_are_a_bug(calibration, sam):
    with pytest.raises(ValueError):
        check_input(calibration, sam, TRAY)
