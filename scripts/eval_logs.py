"""Day 5: first evaluation of RQD and TCR per run against the labels.

Every labelled box goes photo -> calibrate -> segment (three methods) ->
runs -> geometry.py. Only runs seen whole in the photo are compared (see
coresight.runs): a run that continues in another box cannot be judged from
one photo.

- Kaggle boxes: run markers are detected (magenta foam blocks); the first
  run starts in the box when it starts at 0 m. Reference: the mine
  geologist's RQD and CR on the lid.
- Onkalo boxes: the run blocks are wooden, so the markers come from the
  hand-measured piece sheets; each box starts with its first run.
  Reference: the labels measured on the photo (day 2).

All SAM calls come from data/cache/. Writes outputs/eval/runs.csv and
outputs/eval/report.md.

    .venv\\Scripts\\python scripts\\eval_logs.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import find_trays
from coresight.labeling import PieceSheet
from coresight.meta_client import MetaClient
from coresight.pipeline import build_logs, segment
from coresight.runs import Position, RunMismatchError
from coresight.schemas import BoxLabel
from coresight.segmentation import METHODS

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labels"
REFS = LABELS / "calibration" / "scale_references.json"
OUT_DIR = ROOT / "outputs" / "eval"


def sheet_markers(sheet: PieceSheet, tray) -> list[Position]:
    """Run ends of a hand-measured sheet as positions along the straightened rows."""
    out = []
    for row in sheet.rows:
        y = (row.y1 + row.y2) / 2
        for p in row.pieces:
            if p.after != "run_end":
                continue
            r = tray.row_index(p.x2, row.y1, row.y2)
            x = tray.to_straight(np.array([[p.x2, y]]))[0, 0] + 0.5 * tray.px_per_cm
            out.append(Position(r, x / tray.px_per_cm))
    return out


def stats(errors: list[float]) -> str:
    if not errors:
        return "n=0"
    e = np.array(errors)
    return f"MAE {np.mean(np.abs(e)):.1f}, bias {np.mean(e):+.1f} (n={len(e)})"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sites = json.loads(REFS.read_text(encoding="utf-8"))["sites"]
    client = MetaClient()
    sheets = {p.stem: p for p in (LABELS / "pieces").glob("*.json")}
    rows_out = []
    skipped = []
    onkalo_index = 0
    for path in sorted(LABELS.glob("*.json")):
        label = BoxLabel.model_validate_json(path.read_text(encoding="utf-8"))
        image = cv2.imread(str(ROOT / label.image))
        runs = list(label.runs)
        if path.stem in sheets:
            site, tray_index = "onkalo", onkalo_index
            onkalo_index += 1
        else:
            site, tray_index = "kaggle", 0
        tray = find_trays(image, sites[site]["box_length_cm"], max_trays=tray_index + 1)[tray_index]
        for method in METHODS:
            pieces, markers = segment(image, tray, client, method)
            if site == "onkalo":
                sheet = PieceSheet.model_validate_json(sheets[path.stem].read_text("utf-8"))
                markers, first_starts = sheet_markers(sheet, tray), True
            else:
                first_starts = runs[0].from_m == 0
            try:
                results = build_logs(pieces, markers, runs, first_starts)
            except RunMismatchError as exc:
                if method == METHODS[0]:
                    skipped.append(f"{path.stem}: {exc}")
                break
            for run, res in zip(runs, results, strict=True):
                rows_out.append(
                    {
                        "box": path.stem,
                        "site": site,
                        "method": method,
                        "from_m": run.from_m,
                        "to_m": run.to_m,
                        "complete": res.complete,
                        "rqd_ref": run.rqd_pct,
                        "rqd": res.rqd_pct,
                        "tcr_ref": run.tcr_pct,
                        "tcr": res.tcr_pct,
                        "fractures": res.natural_fractures,
                        "uncertain": res.uncertain_breaks,
                        "ff_per_m": res.fracture_frequency_per_m,
                    }
                )

    with (OUT_DIR / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)

    lines = ["Errors per complete run, in percentage points (found - reference).", ""]
    lines.append("| Method | Site | RQD | TCR |")
    lines.append("|---|---|---|---|")
    for method in METHODS:
        for site in ("kaggle", "onkalo", "all"):
            sel = [
                r
                for r in rows_out
                if r["method"] == method and r["complete"] and site in (r["site"], "all")
            ]
            rqd = [r["rqd"] - r["rqd_ref"] for r in sel]
            tcr = [r["tcr"] - r["tcr_ref"] for r in sel]
            lines.append(f"| {method} | {site} | {stats(rqd)} | {stats(tcr)} |")
    lines.append("")
    best = METHODS[-1]
    worst = sorted(
        (r for r in rows_out if r["method"] == best and r["complete"]),
        key=lambda r: -abs(r["rqd"] - r["rqd_ref"]),
    )[:5]
    lines.append(f"Largest RQD errors ({best}):")
    for r in worst:
        lines.append(
            f"- {r['box']} {r['from_m']:.2f}-{r['to_m']:.2f} m: RQD {r['rqd']:.0f} vs"
            f" {r['rqd_ref']:.0f}, TCR {r['tcr']:.0f} vs {r['tcr_ref']:.0f}"
        )
    if skipped:
        lines += ["", "Not evaluated (markers do not fit the run list):"]
        lines += [f"- {s}" for s in skipped]
    report = "\n".join(lines)
    print(report)
    (OUT_DIR / "report.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
