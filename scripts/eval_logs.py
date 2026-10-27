"""Evaluation of RQD and TCR per run against logs made by people (days 5 and 9).

Every labelled box goes photo -> calibrate -> segment (every method) ->
runs -> geometry.py. Only runs seen whole in the photo are compared (see
coresight.runs): a run that continues in another box cannot be judged from
one photo.

- kaggle: run markers are detected (magenta foam blocks); the first run
  starts in the box when it starts at 0 m. Reference: the mine geologist's
  RQD and CR on the lid. The only reference not made by us.
- onkalo (dry photo) and nevada: the run blocks are wooden, so the markers
  come from the hand-measured piece sheets. Reference: our labels, measured
  on the same photo.
- onkalo-wet: the same two Onkalo boxes photographed wet (Commons, same
  author, same framing), scored against the same labels. Robustness only,
  not pooled with the rest.

Statistics come from coresight.evaluation: MAE with a 95% cluster bootstrap
by box, Bland-Altman, Deere class agreement.

Writes, all public (errors only, never the Kaggle reference values, which are
CC BY-NC-SA):
- outputs/eval/runs.csv: error per run and method
- outputs/eval/report.md: the tables
- outputs/eval/bland_altman_public.svg: Bland-Altman of our public boxes
- outputs/eval/failures/*.jpg: worst public runs with the breaks found
Private (not in git): outputs/eval/private/runs_with_refs.csv and
outputs/eval/private/bland_altman_kaggle.svg.

SAM calls come from data/cache/ (the wet photo was called once, it is public).

    .venv\\Scripts\\python scripts\\eval_logs.py
"""

from __future__ import annotations

import csv
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import Tray, find_trays
from coresight.evaluation import (
    DEERE_CLASSES,
    bias,
    bland_altman,
    class_agreement,
    cluster_bootstrap,
    mae,
)
from coresight.labeling import PieceSheet, sheet_markers
from coresight.meta_client import MetaClient
from coresight.pipeline import build_logs, segment
from coresight.runs import RunMismatchError
from coresight.schemas import BoxLabel
from coresight.segmentation import METHODS, RowPieces

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labels"
OUT_DIR = ROOT / "outputs" / "eval"
PRIVATE_DIR = OUT_DIR / "private"
FAILURE_DIR = OUT_DIR / "failures"
PUBLIC_FIELDS = (
    "box", "site", "method", "from_m", "to_m", "complete",
    "rqd_err", "tcr_err", "fractures", "uncertain", "mechanical", "ff_per_m",
)  # fmt: skip
ERRS = ("rqd_err", "tcr_err")
HEADLINE = "sam+fill+profile"  # no help from the geologist's paint marks
POOLED = ("kaggle", "onkalo", "nevada")  # onkalo-wet repeats onkalo boxes
PUBLIC_SITES = ("onkalo", "nevada", "onkalo-wet")
KAGGLE_BOX_CM = 104.0  # set from held-out photos, see scale_references.json
BREAK_COLOURS = {  # BGR
    "natural": (40, 40, 230),
    "uncertain": (0, 200, 255),
    "possible_mechanical": (230, 160, 40),
    "mechanical": (230, 160, 40),
}


@dataclass(frozen=True)
class Box:
    label: str  # stem of data/labels/<label>.json
    site: str
    photo: str | None = None  # overrides the label's image
    tray_index: int = 0
    n_rows: int = 5
    box_length_cm: float = 100.0
    sheet: str | None = None  # piece sheet with the run markers

    @property
    def name(self) -> str:
        return f"{self.label}_wet" if self.site == "onkalo-wet" else self.label


def boxes() -> list[Box]:
    out = []
    for path in sorted(LABELS.glob("*.json")):
        if not (LABELS / "pieces" / path.name).exists():
            out.append(Box(path.stem, "kaggle", box_length_cm=KAGGLE_BOX_CM))
    for i, stem in enumerate(("ONK-DTPH5.1_box05", "ONK-DTPH5.1_box06")):
        out.append(Box(stem, "onkalo", tray_index=i, sheet=stem))
        out.append(Box(stem, "onkalo-wet", "data/raw/commons_onkalo_2.jpg", i, sheet=stem))
    # 66 cm tray: from the depths on the wax-sealed samples (SOURCES.md)
    out.append(
        Box("U12G-GF-GT2_box01", "nevada", n_rows=4, box_length_cm=66.0, sheet="U12G-GF-GT2_box01")
    )
    return out


def ci_cell(rows: list[dict], key: str) -> str:
    if not rows:
        return "n=0"
    errors = [r[key] for r in rows]
    n_boxes = len({r["box"] for r in rows})
    if n_boxes == 1:  # one box resamples to itself: no interval
        return f"{mae(errors):.1f} [one box], bias {bias(errors):+.1f} (n={len(rows)}, 1 box)"
    ci = cluster_bootstrap(errors, [r["box"] for r in rows])
    return (
        f"{ci.value:.1f} [{ci.low:.1f}, {ci.high:.1f}], bias {bias(errors):+.1f}"
        f" (n={len(rows)}, {n_boxes} boxes)"
    )


def select(rows: list[dict], method: str, sites: tuple[str, ...]) -> list[dict]:
    return [r for r in rows if r["method"] == method and r["complete"] and r["site"] in sites]


def bland_altman_svg(points: list[tuple[float, float, str]], title: str, path: Path) -> None:
    """Bland-Altman plot (x mean, y difference) as a small hand-written SVG."""
    ba = bland_altman([m + d / 2 for m, d, _ in points], [m - d / 2 for m, d, _ in points])
    w, h, pad, right = 700, 400, 56, 120  # right margin holds the line labels
    lim = max(40.0, max(abs(d) for _, d, _ in points) + 5)

    def xy(m: float, d: float) -> tuple[float, float]:
        return pad + m / 100 * (w - pad - right), h / 2 - d / lim * (h / 2 - pad)

    colours = {"kaggle": "#7a6ff0", "onkalo": "#2f9e8f", "nevada": "#d9822b", "onkalo-wet": "#555"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif"'
        ' font-size="12">',
        f'<rect width="{w}" height="{h}" fill="#fff"/>',
        f'<text x="{pad}" y="24" font-size="14">{title}</text>',
    ]
    for y_val, label, style in (
        (0.0, "", 'stroke="#ccc"'),
        (ba.bias, f"bias {ba.bias:+.1f}", 'stroke="#333"'),
        (ba.high, f"+1.96 sd {ba.high:+.1f}", 'stroke="#333" stroke-dasharray="4 4"'),
        (ba.low, f"-1.96 sd {ba.low:+.1f}", 'stroke="#333" stroke-dasharray="4 4"'),
    ):
        _, y = xy(0, y_val)
        parts.append(f'<line x1="{pad}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" {style}/>')
        if label:
            parts.append(f'<text x="{w - right + 6}" y="{y + 4:.1f}">{label}</text>')
    for m, d, site in points:
        x, y = xy(m, d)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{colours[site]}" opacity="0.8"/>'
        )
    parts.append(
        f'<text x="{w / 2 - 120}" y="{h - 12}">mean of CoreSight and reference RQD (%)</text>'
    )
    parts.append(
        f'<text x="16" y="{h / 2 + 60}" transform="rotate(-90 16 {h / 2 + 60})">'
        "CoreSight - reference (points)</text>"
    )
    sites = sorted({s for _, _, s in points})
    for i, s in enumerate(sites):
        parts.append(f'<circle cx="{pad + 8 + i * 110}" cy="44" r="4" fill="{colours[s]}"/>')
        parts.append(f'<text x="{pad + 16 + i * 110}" y="48">{s}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def failure_figure(image: np.ndarray, tray: Tray, rows: list[RowPieces], path: Path) -> None:
    """The straightened tray with every break CoreSight found drawn on it."""
    crops = tray.row_crops(image)
    out = []
    for crop, row in zip(crops, rows, strict=True):
        c = crop.copy()
        for (_, b), kind in zip(row.intervals_px, row.breaks, strict=False):
            cv2.line(
                c, (int(b), 0), (int(b), c.shape[0] - 1), BREAK_COLOURS.get(kind, (0, 0, 0)), 3
            )
        out.append(c)
    strip = np.vstack(out)
    scale = 1600 / strip.shape[1]
    small = cv2.resize(strip, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), small, [cv2.IMWRITE_JPEG_QUALITY, 85])


def main() -> None:
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    FAILURE_DIR.mkdir(parents=True, exist_ok=True)
    client = MetaClient()
    rows_out: list[dict] = []
    skipped: list[str] = []
    seen: dict[tuple[str, str], tuple[np.ndarray, Tray, list[RowPieces]]] = {}
    for box in boxes():
        label = BoxLabel.model_validate_json((LABELS / f"{box.label}.json").read_text("utf-8"))
        image = cv2.imread(str(ROOT / (box.photo or label.image)))
        runs = list(label.runs)
        tray = find_trays(
            image, box.box_length_cm, n_rows=box.n_rows, max_trays=box.tray_index + 1
        )[box.tray_index]
        for method in METHODS:
            start = time.perf_counter()
            pieces, markers = segment(image, tray, client, method)
            if method == METHODS[0]:
                print(f"{box.name}: segment {time.perf_counter() - start:.1f} s")
            seen[(box.name, method)] = (image, tray, pieces)
            if box.sheet:
                sheet_path = LABELS / "pieces" / f"{box.sheet}.json"
                sheet = PieceSheet.model_validate_json(sheet_path.read_text("utf-8"))
                markers, first_starts = sheet_markers(sheet, tray), True
            else:
                first_starts = runs[0].from_m == 0
            try:
                results = build_logs(pieces, markers, runs, first_starts)
            except RunMismatchError as exc:
                if method == METHODS[0]:
                    skipped.append(f"{box.name}: {exc}")
                break
            for run, res in zip(runs, results, strict=True):
                rows_out.append(
                    {
                        "box": box.name,
                        "site": box.site,
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
                        "mechanical": res.mechanical_breaks,
                        "ff_per_m": res.fracture_frequency_per_m,
                    }
                )

    for r in rows_out:
        r["rqd_err"] = round(r["rqd"] - r["rqd_ref"], 2)
        r["tcr_err"] = round(r["tcr"] - r["tcr_ref"], 2)
    with (PRIVATE_DIR / "runs_with_refs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0]))
        writer.writeheader()
        writer.writerows(rows_out)
    with (OUT_DIR / "runs.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PUBLIC_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows_out)

    lines = [
        "# Evaluation report",
        "",
        "Errors per complete run, in percentage points (CoreSight - reference).",
        "MAE with a 95% interval from a cluster bootstrap by box (10,000 resamples):"
        " runs of one box share a photo and a calibration, so whole boxes are resampled.",
        "",
        "Sites: `kaggle` is scored against the mine geologist's log (independent reference);"
        " `onkalo` and `nevada` against our own labels on the same photo;"
        " `all` pools the three. `onkalo-wet` is robustness only.",
        "",
        "## RQD and TCR by method (ablation)",
        "",
        "| Method | Site | RQD MAE [95% CI], bias | TCR MAE [95% CI], bias |",
        "|---|---|---|---|",
    ]
    for method in METHODS:
        for site, sites in (
            ("kaggle", ("kaggle",)),
            ("onkalo", ("onkalo",)),
            ("nevada", ("nevada",)),
            ("all", POOLED),
        ):
            sel = select(rows_out, method, sites)
            lines.append(
                f"| {method} | {site} | {ci_cell(sel, 'rqd_err')} | {ci_cell(sel, 'tcr_err')} |"
            )

    head_k = select(rows_out, HEADLINE, ("kaggle",))
    head_all = select(rows_out, HEADLINE, POOLED)
    lines += [
        "",
        f"## Bland-Altman of RQD ({HEADLINE})",
        "",
        "| Site | n | Bias | 95% limits of agreement |",
        "|---|---|---|---|",
    ]
    for site, sel in (("kaggle", head_k), ("all", head_all)):
        ba = bland_altman([r["rqd"] for r in sel], [r["rqd_ref"] for r in sel])
        lines.append(f"| {site} | {ba.n} | {ba.bias:+.1f} | {ba.low:+.1f} to {ba.high:+.1f} |")
    lines += [
        "",
        "Plot of the public boxes: `bland_altman_public.svg`. The Kaggle plot stays private:"
        " its x axis would give away the geologist's values.",
        "",
        f"## Deere class ({HEADLINE})",
        "",
        "| Site | n | Same class | Same or next class |",
        "|---|---|---|---|",
    ]
    for site, sel in (("kaggle", head_k), ("all", head_all)):
        agree = class_agreement([r["rqd"] for r in sel], [r["rqd_ref"] for r in sel])
        lines.append(
            f"| {site} | {agree.n} | {agree.exact} ({agree.accuracy:.0%}) |"
            f" {agree.within_one} ({agree.within_one_rate:.0%}) |"
        )
    agree = class_agreement([r["rqd"] for r in head_all], [r["rqd_ref"] for r in head_all])
    lines += [
        "",
        "Confusion, all sites (rows: reference class, columns: CoreSight class):",
        "",
        "| | " + " | ".join(DEERE_CLASSES) + " |",
        "|---" * (len(DEERE_CLASSES) + 1) + "|",
    ]
    for ref in DEERE_CLASSES:
        cells = [str(agree.confusion.get((ref, found), 0)) for found in DEERE_CLASSES]
        lines.append(f"| {ref} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Robustness: Onkalo dry against wet",
        "",
        "Same boxes, same labels, two photos (Commons, Kallerna). Per run, by method.",
        "",
        "| Method | Run | RQD error dry | RQD error wet | TCR error dry | TCR error wet |",
        "|---|---|---|---|---|---|",
    ]
    for method in METHODS:
        dry = {(r["box"], r["from_m"]): r for r in select(rows_out, method, ("onkalo",))}
        wet = {
            (r["box"].removesuffix("_wet"), r["from_m"]): r
            for r in select(rows_out, method, ("onkalo-wet",))
        }
        for key in sorted(dry):
            d, w = dry[key], wet.get(key)
            cells = [f"{d[k]:+.1f} | " + (f"{w[k]:+.1f}" if w else "not scored") for k in ERRS]
            lines.append(f"| {method} | {key[0][-5:]} {key[1]:.2f} m | " + " | ".join(cells) + " |")
        both = [(dry[k], wet[k]) for k in dry if k in wet]
        if both:
            cells = [
                f"{mae([d[k] for d, _ in both]):.1f} | {mae([w[k] for _, w in both]):.1f}"
                for k in ERRS
            ]
            lines.append(f"| {method} | MAE | " + " | ".join(cells) + " |")

    lines += ["", f"## Largest RQD errors ({HEADLINE})", ""]
    worst = sorted(select(rows_out, HEADLINE, ("kaggle",)), key=lambda r: -abs(r["rqd_err"]))[:5]
    lines.append("Kaggle (no photo: the set is non-commercial):")
    lines += [
        f"- {r['box']} {r['from_m']:.2f}-{r['to_m']:.2f} m: RQD error {r['rqd_err']:+.0f},"
        f" TCR error {r['tcr_err']:+.0f}"
        for r in worst
    ]
    lines += [
        "",
        "Public boxes, with the breaks CoreSight found drawn on the tray"
        " (red natural, yellow uncertain, blue mechanical). Onkalo photos: Kallerna,"
        " Wikimedia Commons, CC BY-SA 4.0, and these figures under the same license;"
        " Nevada: U.S. Department of Energy (NNSA), public domain.",
    ]
    public = sorted(select(rows_out, HEADLINE, PUBLIC_SITES), key=lambda r: -abs(r["rqd_err"]))
    drawn = set()
    for r in public[:4]:
        lines.append(
            f"- {r['box']} {r['from_m']:.2f}-{r['to_m']:.2f} m: RQD error {r['rqd_err']:+.1f},"
            f" TCR error {r['tcr_err']:+.1f}, {r['uncertain']} uncertain breaks"
            f" (`failures/{r['box']}.jpg`)"
        )
        if r["box"] not in drawn:
            failure_figure(*seen[(r["box"], HEADLINE)], FAILURE_DIR / f"{r['box']}.jpg")
            drawn.add(r["box"])

    if skipped:
        lines += ["", "Not evaluated (markers do not fit the run list):"]
        lines += [f"- {s}" for s in skipped]

    points = [
        (r["rqd"] / 2 + r["rqd_ref"] / 2, r["rqd_err"], r["site"])
        for r in select(rows_out, HEADLINE, ("onkalo", "nevada"))
    ]
    if len(points) >= 2:
        bland_altman_svg(
            points, f"RQD, public boxes ({HEADLINE})", OUT_DIR / "bland_altman_public.svg"
        )
    points = [(r["rqd"] / 2 + r["rqd_ref"] / 2, r["rqd_err"], r["site"]) for r in head_k]
    bland_altman_svg(points, f"RQD, Kaggle ({HEADLINE})", PRIVATE_DIR / "bland_altman_kaggle.svg")

    report = "\n".join(lines)
    print(report)
    (OUT_DIR / "report.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
