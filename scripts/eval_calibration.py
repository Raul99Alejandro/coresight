"""Day 3 check: px->cm error and row detection on the labelled boxes.

Scale error: a known length in the photo is measured with the calibration
and compared with its true length. Kaggle boxes use the tape measure (10 to
90 cm); Onkalo boxes use the metre marks along the core (data/labels/pieces/).
Rows: every piece annotated in the Kaggle train.csv ("+10cm rock") must fall
inside one detected row; Onkalo rows come from the piece sheets.

Writes a table to stdout and outputs/calibration/ (report.md and an overlay
per photo). Reference points: data/labels/calibration/scale_references.json.

    .venv\\Scripts\\python scripts\\eval_calibration.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import Tray, find_trays
from coresight.labeling import PieceSheet

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "data" / "labels" / "calibration" / "scale_references.json"
SHEETS = ROOT / "data" / "labels" / "pieces"
KAGGLE_CSV = ROOT / "data" / "raw" / "kaggle_mining_core" / "train.csv"
OUT_DIR = ROOT / "outputs" / "calibration"
MAX_ERROR_PCT = 2.0


def straight_length_cm(tray: Tray, a, b) -> float:
    p, q = tray.to_straight(np.array([a, b], dtype=float))
    return float(np.linalg.norm(q - p)) / tray.px_per_cm


def row_of(tray: Tray, y1: float, y2: float, x: float) -> int | None:
    """Detected row holding at least 80% of the vertical extent y1..y2 at x."""
    top, bottom = tray.to_straight(np.array([[x, y1], [x, y2]], dtype=float))[:, 1]
    for row in tray.rows:
        overlap = min(bottom, row.y2) - max(top, row.y1)
        if overlap >= 0.8 * (bottom - top):
            return row.index
    return None


def kaggle_pieces(image_name: str) -> list[tuple[float, float, float, float]]:
    if not KAGGLE_CSV.exists():
        return []
    with KAGGLE_CSV.open(encoding="utf-8") as f:
        return [
            (float(r["xmin"]), float(r["ymin"]), float(r["width"]), float(r["height"]))
            for r in csv.DictReader(f)
            if r["image_name"] == image_name and r["label_name"] == "+10cm rock"
        ]


def onkalo_reference(sheet: PieceSheet, tray: Tray) -> tuple[float, float]:
    """(measured cm, true cm) of the core between the first and last metre mark."""
    marks = sorted(sheet.meter_marks, key=lambda m: m.depth_m)
    first, last = marks[0], marks[-1]
    measured = 0.0
    for i, row in enumerate(sheet.rows):
        y = (row.y1 + row.y2) / 2
        for p in row.pieces:
            x1, x2 = p.x1, p.x2
            if i < first.row or i > last.row:
                continue
            if i == first.row:
                x1 = max(x1, first.x)
            if i == last.row:
                x2 = min(x2, last.x)
            if x2 > x1:
                measured += straight_length_cm(tray, (x1, y), (x2, y))
    return measured, (last.depth_m - first.depth_m) * 100.0


def draw(image: np.ndarray, trays: list[Tray], path: Path) -> None:
    out = image.copy()
    for tray in trays:
        inv = np.linalg.inv(tray.homography)
        for row in tray.rows:
            for y in (row.y1, row.y2):
                ends = np.array([[[0, y]], [[tray.width, y]]], dtype=np.float64)
                a, b = cv2.perspectiveTransform(ends, inv).reshape(-1, 2).astype(int)
                cv2.line(out, tuple(a), tuple(b), (255, 0, 255), 6)
        cv2.polylines(out, [tray.corners.astype(np.int32)], True, (0, 255, 0), 8)
    scale = 1600 / out.shape[1]
    cv2.imwrite(
        str(path), cv2.resize(out, None, fx=scale, fy=scale), [cv2.IMWRITE_JPEG_QUALITY, 85]
    )


def main() -> int:
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    sites = refs["sites"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for name, ref in refs["boxes"].items():
        image = cv2.imread(str(ROOT / ref["image"]))
        tray = find_trays(image, sites["kaggle"]["box_length_cm"], max_trays=1)[0]
        a, b = ref["tape_points_px"]
        true_cm = ref["tape_cm"][1] - ref["tape_cm"][0]
        measured = straight_length_cm(tray, a, b)
        pieces = kaggle_pieces(Path(ref["image"]).name)
        in_row = sum(row_of(tray, y, y + h, x + w / 2) is not None for x, y, w, h in pieces)
        draw(image, [tray], OUT_DIR / f"{name}.jpg")
        results.append((name, measured, true_cm, in_row, len(pieces)))

    for path in sorted(SHEETS.glob("*.json")):
        sheet = PieceSheet.model_validate_json(path.read_text(encoding="utf-8"))
        image = cv2.imread(str(ROOT / sheet.image))
        trays = find_trays(image, sites["onkalo"]["box_length_cm"], max_trays=2)
        y_mid = (sheet.rows[0].y1 + sheet.rows[-1].y2) / 2
        tray = min(trays, key=lambda t: abs(t.corners[:, 1].mean() - y_mid))
        measured, true_cm = onkalo_reference(sheet, tray)
        in_row = sum(
            row_of(tray, r.y1, r.y2, (r.pieces[0].x1 + r.pieces[-1].x2) / 2) == i
            for i, r in enumerate(sheet.rows)
        )
        draw(image, trays, OUT_DIR / "onkalo.jpg")
        results.append((path.stem, measured, true_cm, in_row, len(sheet.rows)))

    lines = [
        "| Box | Reference | Measured | Error | Pieces inside one row |",
        "|---|---|---|---|---|",
    ]
    worst = 0.0
    for name, measured, true_cm, in_row, total in results:
        err = (measured / true_cm - 1) * 100
        worst = max(worst, abs(err))
        lines.append(
            f"| {name} | {true_cm:.0f} cm | {measured:.1f} cm | {err:+.2f}% | {in_row}/{total} |"
        )
    errors = [abs(m / t - 1) * 100 for _, m, t, _, _ in results]
    lines.append("")
    lines.append(
        f"Mean absolute error {np.mean(errors):.2f}%, worst {worst:.2f}% "
        f"(target < {MAX_ERROR_PCT}%) over {len(results)} boxes."
    )
    report = "\n".join(lines)
    print(report)
    (OUT_DIR / "report.md").write_text(report + "\n", encoding="utf-8")
    return 0 if worst < MAX_ERROR_PCT else 1


if __name__ == "__main__":
    raise SystemExit(main())
