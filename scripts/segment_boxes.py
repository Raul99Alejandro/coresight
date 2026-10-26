"""Day 4: pieces per row in cm for the 15 labelled boxes, with both methods.

Calibrates every box (day 3), sends each straightened row to SAM 3.1 (cached
in data/cache/ with the decoded masks, so a rerun costs nothing) and turns the masks into pieces
with each method in coresight.segmentation.METHODS.

Measured against:
- Onkalo: the hand-measured breaks in data/labels/pieces/ (a break counts as
  found within 2 cm), and the length of pieces >= 10 cm per row.
- Kaggle: the "+10cm rock" boxes in train.csv, as length of pieces >= 10 cm
  per row (the quantity RQD is made of).

Writes outputs/segmentation/<box>.json (pieces per row in cm, both methods),
an overlay per box and report.md.

    .venv\\Scripts\\python scripts\\segment_boxes.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import Tray, find_trays
from coresight.labeling import PieceSheet
from coresight.meta_client import MetaClient
from coresight.segmentation import METHODS, RowPieces, row_masks, segment_row

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "data" / "labels" / "calibration" / "scale_references.json"
SHEETS = ROOT / "data" / "labels" / "pieces"
KAGGLE_CSV = ROOT / "data" / "raw" / "kaggle_mining_core" / "train.csv"
OUT_DIR = ROOT / "outputs" / "segmentation"
RQD_MIN_CM = 10.0
BREAK_TOLERANCE_CM = 2.0


def boxes() -> list[tuple[str, str, float, int | None]]:
    """(name, image, box length cm, tray index or None for the only tray)."""
    refs = json.loads(REFS.read_text(encoding="utf-8"))
    out = [
        (name, ref["image"], refs["sites"]["kaggle"]["box_length_cm"], None)
        for name, ref in refs["boxes"].items()
    ]
    for i, path in enumerate(sorted(SHEETS.glob("*.json"))):
        sheet = PieceSheet.model_validate_json(path.read_text(encoding="utf-8"))
        out.append((path.stem, sheet.image, refs["sites"]["onkalo"]["box_length_cm"], i))
    return out


def long_length(intervals_cm: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in intervals_cm if b - a >= RQD_MIN_CM)


def kaggle_truth(tray: Tray, image_name: str) -> list[list[tuple[float, float]]]:
    """'+10cm rock' boxes per detected row, as cm intervals along the row."""
    rows: list[list[tuple[float, float]]] = [[] for _ in tray.rows]
    with KAGGLE_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["image_name"] != image_name or r["label_name"] != "+10cm rock":
                continue
            x, y, w, h = (float(r[k]) for k in ("xmin", "ymin", "width", "height"))
            row = tray.row_index(x + w / 2, y, y + h)
            if row is None:
                continue
            (a, _), (b, _) = tray.to_straight(np.array([[x, y + h / 2], [x + w, y + h / 2]]))
            rows[row].append((a / tray.px_per_cm, b / tray.px_per_cm))
    return rows


def onkalo_truth(tray: Tray, sheet: PieceSheet) -> list[list[tuple[float, float]]]:
    """Hand-measured pieces per row, as cm intervals along the straightened row."""
    rows = []
    for row in sheet.rows:
        y = (row.y1 + row.y2) / 2
        cm = []
        for p in row.pieces:
            (a, _), (b, _) = tray.to_straight(np.array([[p.x1, y], [p.x2, y]]))
            cm.append((a / tray.px_per_cm, b / tray.px_per_cm))
        rows.append(cm)
    return rows


def break_match(truth: list[float], found: list[float]) -> tuple[int, int, int]:
    """(matched, truth count, found count) with greedy matching within tolerance."""
    unused = sorted(found)
    matched = 0
    for t in sorted(truth):
        near = [f for f in unused if abs(f - t) <= BREAK_TOLERANCE_CM]
        if near:
            unused.remove(min(near, key=lambda f: abs(f - t)))
            matched += 1
    return matched, len(truth), len(found)


def boundaries(intervals_cm: list[tuple[float, float]]) -> list[float]:
    """Inner piece ends of a row: one position per break (overlaps merged)."""
    ends = sorted(x for a, b in intervals_cm for x in (a, b))[1:-1]
    merged: list[float] = []
    for x in ends:
        if merged and x - merged[-1] <= BREAK_TOLERANCE_CM:
            merged[-1] = (merged[-1] + x) / 2
        else:
            merged.append(x)
    return merged


def draw(crops: list[np.ndarray], results: dict[str, list[RowPieces]], path: Path) -> None:
    rows = []
    for i, crop in enumerate(crops):
        vis = crop.copy()
        h = vis.shape[0]
        for k, (method, colour) in enumerate(
            zip(METHODS, ((0, 200, 0), (255, 160, 0), (255, 0, 255)), strict=True)
        ):
            y = 8 + k * 14
            for a, b in results[method][i].intervals_px:
                cv2.line(vis, (int(a) + 3, y), (int(b) - 3, y), colour, 8)
                cv2.line(vis, (int(b), 0), (int(b), h), colour, 2)
        rows.append(vis)
    width = max(r.shape[1] for r in rows)
    sheet = np.vstack([cv2.copyMakeBorder(r, 0, 6, 0, width - r.shape[1], 0) for r in rows])
    scale = 1600 / sheet.shape[1]
    cv2.imwrite(str(path), cv2.resize(sheet, None, fx=scale, fy=scale))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = MetaClient()
    sheets = {
        p.stem: PieceSheet.model_validate_json(p.read_text(encoding="utf-8"))
        for p in SHEETS.glob("*.json")
    }
    long_err = {m: [] for m in METHODS}
    breaks = {m: [0, 0, 0] for m in METHODS}
    table = []
    for name, image_path, box_cm, tray_index in boxes():
        image = cv2.imread(str(ROOT / image_path))
        trays = find_trays(image, box_cm, max_trays=1 if tray_index is None else 2)
        tray = trays[tray_index or 0]
        crops = tray.row_crops(image)
        results: dict[str, list[RowPieces]] = {m: [] for m in METHODS}
        for crop in crops:
            masks = row_masks(client, crop)
            for m in METHODS:
                results[m].append(segment_row(crop, masks, tray.px_per_cm, m))
        truth = (
            onkalo_truth(tray, sheets[name])
            if name in sheets
            else kaggle_truth(tray, Path(image_path).name)
        )
        row_line = [name]
        for m in METHODS:
            cm_rows = [[(p.start_cm, p.end_cm) for p in r.pieces] for r in results[m]]
            errs = [long_length(f) - long_length(t) for f, t in zip(cm_rows, truth, strict=True)]
            long_err[m] += errs
            row_line.append(f"{np.mean(np.abs(errs)):.1f}")
            if name in sheets:
                for f, t in zip(cm_rows, truth, strict=True):
                    got = break_match(boundaries(t), boundaries(f))
                    breaks[m] = [x + y for x, y in zip(breaks[m], got, strict=True)]
        table.append(row_line)
        payload = {
            "box": name,
            "image": image_path,
            "px_per_cm": tray.px_per_cm,
            "rows": [
                {
                    "row": i,
                    **{m: [[p.start_cm, p.end_cm] for p in results[m][i].pieces] for m in METHODS},
                }
                for i in range(len(crops))
            ],
        }
        (OUT_DIR / f"{name}.json").write_text(json.dumps(payload, indent=1) + "\n", "utf-8")
        draw(crops, results, OUT_DIR / f"{name}.jpg")

    lines = [
        "Length of pieces >= 10 cm per row, |found - reference| in cm (mean per box):",
        "",
        "| Box | " + " | ".join(METHODS) + " |",
        "|---" * (len(METHODS) + 1) + "|",
        *["| " + " | ".join(r) + " |" for r in table],
        "",
    ]
    for m in METHODS:
        e = np.array(long_err[m])
        lines.append(
            f"- {m}: MAE {np.mean(np.abs(e)):.1f} cm per row, bias {np.mean(e):+.1f} cm,"
            f" {len(e)} rows"
        )
    lines.append("")
    lines.append(f"Onkalo breaks found within {BREAK_TOLERANCE_CM:.0f} cm (hand-measured):")
    for m in METHODS:
        matched, n_truth, n_found = breaks[m]
        lines.append(f"- {m}: recall {matched}/{n_truth}, precision {matched}/{n_found}")
    report = "\n".join(lines)
    print(report)
    (OUT_DIR / "report.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
