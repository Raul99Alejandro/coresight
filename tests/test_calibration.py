import cv2
import numpy as np
import pytest

from coresight.calibration import CalibrationError, find_trays
from coresight.pipeline import calibrate

PX_PER_CM = 10.0
TRAY_CM = 100.0
PITCH_CM = 8.0
SLAT_CM = 1.2


def draw_tray(image, top, left, rng):
    """A 5-row tray: smooth slats and walls, busy core in the rows."""
    width = int(TRAY_CM * PX_PER_CM)
    pitch = int(PITCH_CM * PX_PER_CM)
    slat = int(SLAT_CM * PX_PER_CM)
    wood = (120, 180, 215)
    cv2.rectangle(image, (left - 30, top - 30), (left + width + 30, top + 5 * pitch + 30), wood, -1)
    for r in range(5):
        y = top + r * pitch + slat // 2
        x = left
        while x < left + width - 40:
            length = int(rng.integers(30, 160))
            grey = int(rng.integers(60, 200))
            cv2.rectangle(
                image,
                (x, y + 6),
                (min(x + length, left + width), y + pitch - slat - 6),
                (grey, grey, grey),
                -1,
            )
            x += length + int(rng.integers(3, 12))
    for r in range(6):
        y = top + r * pitch - slat // 2
        cv2.rectangle(image, (left, y), (left + width, y + slat), wood, -1)
    return width, pitch


def photo(trays=1, angle=0.0, seed=0):
    rng = np.random.default_rng(seed)
    image = np.full((1400, 1400, 3), 40, np.uint8)
    image[:] = rng.integers(30, 60, image.shape, dtype=np.uint8)
    for i in range(trays):
        draw_tray(image, 150 + i * 520, 200, rng)
    if angle:
        m = cv2.getRotationMatrix2D((700, 700), angle, 1.0)
        image = cv2.warpAffine(image, m, (1400, 1400), borderValue=(40, 40, 40))
    return image


def test_scale_and_rows_of_a_straight_tray():
    [tray] = find_trays(photo(), TRAY_CM, max_trays=1)
    assert tray.px_per_cm == pytest.approx(PX_PER_CM, rel=0.02)
    assert len(tray.rows) == 5
    heights = [r.y2 - r.y1 for r in tray.rows]
    assert max(heights) == pytest.approx(min(heights))


def test_tilted_tray_measures_the_same_length():
    angle = 2.0
    image = photo(angle=angle)
    [tray] = find_trays(image, TRAY_CM, max_trays=1)
    # a 50 cm segment along the second row, rotated like the photo
    m = cv2.getRotationMatrix2D((700, 700), angle, 1.0)
    ends = np.array([[300, 270, 1], [800, 270, 1]], dtype=float) @ m.T
    p, q = tray.to_straight(ends)
    assert np.linalg.norm(q - p) / tray.px_per_cm == pytest.approx(50.0, rel=0.02)


def test_two_stacked_trays_are_found_top_to_bottom():
    trays = find_trays(photo(trays=2), TRAY_CM, max_trays=2)
    assert len(trays) == 2
    assert trays[0].corners[:, 1].mean() < trays[1].corners[:, 1].mean()
    for tray in trays:
        assert tray.px_per_cm == pytest.approx(PX_PER_CM, rel=0.02)


def test_row_crops_have_the_row_height():
    image = photo()
    [tray] = find_trays(image, TRAY_CM, max_trays=1)
    crops = tray.row_crops(image)
    assert len(crops) == 5
    assert all(abs(c.shape[0] - PITCH_CM * PX_PER_CM) <= 3 for c in crops)


def test_photo_without_a_tray_is_rejected():
    blank = np.full((800, 1000, 3), 128, np.uint8)
    with pytest.raises(CalibrationError):
        find_trays(blank, TRAY_CM)


def test_box_length_must_be_positive():
    with pytest.raises(ValueError):
        find_trays(photo(), 0)


def test_pipeline_calibrate_reads_the_file(tmp_path):
    path = tmp_path / "box.png"
    cv2.imwrite(str(path), photo())
    trays = calibrate(path, TRAY_CM)
    assert trays[0].px_per_cm == pytest.approx(PX_PER_CM, rel=0.02)
    with pytest.raises(FileNotFoundError):
        calibrate(tmp_path / "missing.png", TRAY_CM)
