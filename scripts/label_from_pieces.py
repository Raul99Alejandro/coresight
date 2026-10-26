"""Write BoxLabels from the hand-measured piece sheets and draw them for review.

For every sheet in data/labels/pieces/ (format in coresight.labeling) this
writes data/labels/<hole_id>_box<NN>.json and an overlay in outputs/labels/
with every piece, break and run result drawn on the photo.

    .venv\\Scripts\\python scripts\\label_from_pieces.py
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2

from coresight.labeling import PieceSheet, label_from_sheet, log_sheet, px_per_cm

ROOT = Path(__file__).resolve().parents[1]
SHEETS = ROOT / "data" / "labels" / "pieces"
OUT_DIR = ROOT / "outputs" / "labels"
# BGR: natural red, uncertain orange, mechanical blue, run block green
BREAK_COLORS = {
    "natural": (0, 0, 230),
    "uncertain": (0, 140, 255),
    "mechanical": (230, 120, 0),
    "run_end": (0, 180, 0),
}


def draw(sheet: PieceSheet, out_path: Path) -> None:
    image = cv2.imread(str(ROOT / sheet.image))
    if image is None:
        raise FileNotFoundError(sheet.image)
    for row in sheet.rows:
        y1, y2 = int(row.y1), int(row.y2)
        for p in row.pieces:
            cv2.rectangle(image, (int(p.x1), y1), (int(p.x2), y2), (255, 255, 255), 3)
            cv2.line(image, (int(p.x2), y1 - 20), (int(p.x2), y2 + 20), BREAK_COLORS[p.after], 9)
    for mark in sheet.meter_marks:
        row = sheet.rows[mark.row]
        cv2.circle(image, (int(mark.x), int((row.y1 + row.y2) / 2)), 14, (255, 0, 255), -1)
    lines = [f"{sheet.hole_id} box {sheet.box_number}  scale {px_per_cm(sheet):.1f} px/cm"]
    for log in log_sheet(sheet):
        lines.append(
            f"{log.from_m:.2f}-{log.to_m:.2f} m  RQD {log.rqd_pct:.0f}%  TCR {log.tcr_pct:.0f}%"
            f"  fractures {log.natural_fractures} ({log.uncertain_breaks} uncertain)"
        )
    y = int(sheet.rows[0].y1) - 30 - 50 * (len(lines) - 1)
    for text in lines:
        cv2.putText(image, text, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 9)
        cv2.putText(image, text, (60, y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3)
        y += 50
    top = max(int(sheet.rows[0].y1) - 400, 0)
    bottom = min(int(sheet.rows[-1].y2) + 60, image.shape[0])
    cv2.imwrite(str(out_path), image[top:bottom])


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(SHEETS.glob("*.json")):
        sheet = PieceSheet.model_validate_json(path.read_text(encoding="utf-8"))
        label = label_from_sheet(sheet)
        out = ROOT / "data" / "labels" / f"{label.hole_id}_box{label.box_number:02d}.json"
        out.write_text(json.dumps(label.model_dump(mode="json"), indent=2) + "\n", "utf-8")
        draw(sheet, OUT_DIR / f"{path.stem}.jpg")
        print(f"{out.relative_to(ROOT)} and outputs/labels/{path.stem}.jpg")


if __name__ == "__main__":
    main()
