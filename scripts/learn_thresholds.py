"""The learning loop, measured (point F): do a site's corrections lower the RQD error?

The geologist's corrections give each corrected run its true RQD. Here our
hand labels of the public boxes play that role (Onkalo boxes 5 and 6, Nevada
U12G boxes 1 and 3: the same labels as outputs/eval). The Kaggle set (NC) is
never used: not to fit, not to score.

For every box, the production segmentation (review.SEGMENT_METHOD) runs once per
candidate pair of profile thresholds, on SAM masks read from data/cache (no API
call is paid), and geometry.py logs every run. coresight.learning then fits a
pair per site and scores it on photos it never saw, and draws the learning
curve: the held-out RQD error after n corrected runs of the site. The unit of
cross-validation is the photo, not the box: Onkalo boxes 5 and 6 are two trays
of one photo (same light, same camera), so holding out one box would still let
the fit see its photo. Onkalo has one photo, so it gets no held-out score. Two starts:
the hand-set default, and a site whose thresholds start badly set (a new mine
before anyone tuned them), to show whether the loop finds its way back.

Writes outputs/eval/learning.md, learning.csv and learning.svg.

    .venv\\Scripts\\python scripts\\learn_thresholds.py
"""

from __future__ import annotations

import csv
import itertools
from dataclasses import dataclass
from pathlib import Path

import cv2

from coresight.calibration import find_trays
from coresight.labeling import PieceSheet, sheet_markers
from coresight.learning import RunError, fit, learning_curve, leave_one_box_out, mae_of
from coresight.meta_client import MetaClient
from coresight.pipeline import build_logs, row_prompts
from coresight.review import SEGMENT_METHOD
from coresight.schemas import BoxLabel
from coresight.segmentation import DEFAULT_PROFILE, ProfileThresholds, segment_row

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "labels"
OUT = ROOT / "outputs" / "eval"
CONTRASTS = (0.10, 0.125, 0.15, 0.175, 0.20, 0.25, 0.30, 0.40, 9.99)  # 9.99: no profile cut
CROSSINGS = (0.6, 0.7, 0.8, 0.9, 1.0)
DEFAULT = (DEFAULT_PROFILE.min_contrast, DEFAULT_PROFILE.min_crossing)
POOR_START = (0.10, 0.7)  # a site before anyone tuned it: cuts at faint lines
assert DEFAULT in itertools.product(CONTRASTS, CROSSINGS)
assert POOR_START in itertools.product(CONTRASTS, CROSSINGS)
Curve = list[tuple[int, float, float]]


@dataclass(frozen=True)
class Box:
    label: str
    site: str
    tray_index: int = 0
    n_rows: int = 5
    box_length_cm: float = 100.0
    first_starts_in_box: bool = True


BOXES = [  # public photos only (data/labels/SOURCES.md)
    Box("ONK-DTPH5.1_box05", "onkalo", tray_index=0),
    Box("ONK-DTPH5.1_box06", "onkalo", tray_index=1),
    Box("U12G-GF-GT2_box01", "nevada", n_rows=4, box_length_cm=66.0),
    Box("U12G-GF-GT2_box03", "nevada", n_rows=4, box_length_cm=68.0, first_starts_in_box=False),
]


def box_errors(box: Box, client: MetaClient, k: int) -> list[RunError]:
    """RQD error of every complete run, for every candidate pair (geometry.py logs them).

    ``RunError.box`` is the photo (the unit of cross-validation); runs are numbered
    ``100 * k + i`` so two boxes of one photo never share a run key.
    """
    label = BoxLabel.model_validate_json((LABELS / f"{box.label}.json").read_text("utf-8"))
    image = cv2.imread(str(ROOT / label.image))
    tray = find_trays(image, box.box_length_cm, n_rows=box.n_rows,
                      max_trays=box.tray_index + 1)[box.tray_index]  # fmt: skip
    sheet = PieceSheet.model_validate_json((LABELS / "pieces" / f"{box.label}.json").read_text())
    markers = sheet_markers(sheet, tray)
    crops = tray.row_crops(image)
    prompts = [row_prompts(client, crop, SEGMENT_METHOD) for crop in crops]
    out = []
    for contrast, crossing in itertools.product(CONTRASTS, CROSSINGS):
        profile = ProfileThresholds(contrast, crossing)
        rows = [segment_row(crop, masks, tray.px_per_cm, SEGMENT_METHOD, not_core, profile)
                for crop, (masks, not_core, _) in zip(crops, prompts, strict=True)]  # fmt: skip
        results = build_logs(rows, markers, list(label.runs), box.first_starts_in_box)
        for i, (run, res) in enumerate(zip(label.runs, results, strict=True)):
            if res.complete:
                err = res.rqd_pct - run.rqd_pct
                out.append(RunError(Path(label.image).stem, 100 * k + i, (contrast, crossing), err))
    if not out:
        raise RuntimeError(f"{box.label}: no complete run to learn from")
    return out


def curve_svg(series: list[tuple[str, str, Curve]], path: Path) -> None:
    """Held-out RQD MAE after n corrected runs of the site: one line per start."""
    w, h, left, right, top, bottom = 720, 400, 64, 210, 64, 56
    n_max = max(n for _, _, c in series for n, _, _ in c)
    y_max = max(5.0, 1.15 * max(v for _, _, c in series for _, d, f in c for v in (d, f)))

    def xy(n: float, v: float) -> tuple[float, float]:
        x = left + n / max(n_max, 1) * (w - left - right)
        return x, h - bottom - v / y_max * (h - top - bottom)

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif"'
         ' font-size="12">', f'<rect width="{w}" height="{h}" fill="#fff"/>',
         f'<text x="{left}" y="26" font-size="15" font-weight="600">After n corrected runs,'
         " the RQD error on boxes the fit never saw</text>",
         f'<text x="{left}" y="45" fill="#666">Nevada U12G: fit on one photo, scored on the other.'
         " Public boxes only; our labels play the geologist.</text>"]  # fmt: skip
    step = 5 if y_max > 12 else 2
    for v in range(0, int(y_max) + 1, step):
        _, y = xy(0, v)
        p.append(f'<line x1="{left}" x2="{w - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#eee"/>')
        p.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="#666">{v}</text>')
    for n in range(n_max + 1):
        x, _ = xy(n, 0)
        p.append(f'<text x="{x:.1f}" y="{h - bottom + 18}" text-anchor="middle" fill="#666">{n}'
                 "</text>")  # fmt: skip
    p.append(f'<text x="{(left + w - right) / 2}" y="{h - 14}" text-anchor="middle">'
             "corrected runs of the site used to fit the thresholds</text>")  # fmt: skip
    p.append(f'<text x="18" y="{h / 2 + 70}" transform="rotate(-90 18 {h / 2 + 70})">'
             "held-out RQD MAE (points)</text>")  # fmt: skip
    labels = []
    for name, colour, curve in series:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(n, f) for n, _, f in curve))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2.4"/>')
        for n, _, f in curve:
            x, y = xy(n, f)
            p.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{colour}"/>')
        labels.append([*xy(curve[-1][0], curve[-1][2]), name, colour, curve])
    labels.sort(key=lambda lab: lab[1])
    for above, below in itertools.pairwise(labels):  # two lines end close: spread the labels
        if below[1] - above[1] < 34:
            mid = (above[1] + below[1]) / 2
            above[1], below[1] = mid - 17, mid + 17
    for x, y, name, colour, curve in labels:
        p.append(f'<text x="{x + 10:.1f}" y="{y - 2:.1f}" fill="{colour}">{name}</text>')
        p.append(f'<text x="{x + 10:.1f}" y="{y + 13:.1f}" fill="{colour}">'
                 f"{curve[0][2]:.1f} to {curve[-1][2]:.1f} points</text>")  # fmt: skip
    p.append("</svg>")
    path.write_text("\n".join(p) + "\n", encoding="utf-8")


def curves_from(by_site: dict[str, list[RunError]], start: tuple[float, float]) -> dict:
    """Learning curves of the sites with two photos or more (one photo: no held-out score)."""
    curves = {site: learning_curve(errs, start) for site, errs in by_site.items()}
    return {site: c for site, c in curves.items() if c}


def table(curves: dict[str, Curve]) -> list[str]:
    lines = ["| n | " + " | ".join(curves) + " |", "|---|" + "---|" * len(curves)]
    n_max = max(n for c in curves.values() for n, _, _ in c)
    for n in range(n_max + 1):
        cells = [f"{c[min(n, len(c) - 1)][2]:.1f}" for c in curves.values()]
        lines.append(f"| {n} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    client = MetaClient()
    by_site: dict[str, list[RunError]] = {}
    for k, b in enumerate(BOXES):
        by_site.setdefault(b.site, []).extend(box_errors(b, client, k))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "learning.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site", "box", "run", "min_contrast", "min_crossing", "rqd_err"])
        for site, errs in by_site.items():
            for e in errs:
                w.writerow([site, e.box, e.run, *e.candidate, round(e.error, 2)])

    lines = ["# Learning loop: corrections tune the profile thresholds (point F)", "",
             "Our hand labels of the public boxes stand in for the geologist's corrections."
             " The Kaggle set (NC) is not used. Segmentation: production method"
             f" `{SEGMENT_METHOD}`, SAM masks from the cache. Default thresholds"
             f" (min_contrast, min_crossing) = {DEFAULT}. Candidates: {len(CONTRASTS)} contrasts"
             f" x {len(CROSSINGS)} crossings (contrast 9.99 = no profile cut).", "",
             "## Leave one photo out, from the default", "",
             "Onkalo boxes 5 and 6 are two trays of one photo: one photo, no held-out score."
             " Nevada boxes 1 and 3 are two photos.", "",
             "| Site | Held-out photo | Fitted on the other photo | Train runs | Test runs |"
             " RQD MAE default | RQD MAE fitted |", "|---|---|---|---|---|---|---|"]  # fmt: skip
    for site, errs in by_site.items():
        for fo in leave_one_box_out(errs, DEFAULT):
            lines.append(f"| {site} | {fo.held_out} | {fo.fitted} | {fo.train_runs} | "
                         f"{fo.test_runs} | {fo.mae_default:.1f} | {fo.mae_fitted:.1f} |")
    from_default, from_poor = curves_from(by_site, DEFAULT), curves_from(by_site, POOR_START)
    lines += ["", "## Learning curve from the default", "",
              "Held-out RQD MAE (points) after n corrected runs of the site; n = 0 is the"
              " default.", "", *table(from_default), "",
              f"## Learning curve from a poorly set site {POOR_START}", "",
              "The same photos, as if the site started with thresholds nobody had tuned"
              " (it cuts at faint lines). A scenario, not a real site.", "",
              *table(from_poor), "",
              "## Fitted on every corrected run of the site (in-sample: not evidence)",
              ""]  # fmt: skip
    for site, errs in by_site.items():
        keys = {(e.box, e.run) for e in errs}
        for start in (DEFAULT, POOR_START):
            best = fit(errs, None, start)
            lines.append(f"- {site}, from {start}: fits {best}, RQD MAE"
                         f" {mae_of(errs, start, keys):.1f} to {mae_of(errs, best, keys):.1f}")
    site = "nevada"
    a, b = from_default[site][0][2], from_default[site][-1][2]
    c, d = from_poor[site][0][2], from_poor[site][-1][2]
    n = from_poor[site][-1][0]
    lines += ["", "## Result", "",
              f"- From the hand-set default, Nevada: the held-out RQD MAE goes from {a:.1f} to"
              f" {b:.1f} points after {n} corrected runs. Nothing to learn in these two"
              " thresholds on these photos: the default was already the best.",
              f"- From a poorly set site, Nevada: from {c:.1f} to {d:.1f} points after {n}"
              " corrected runs, on a photo the fit never saw. The loop finds its way back when a"
              " site's thresholds are wrong.",
              "- What the thresholds cannot fix: the largest Nevada errors (box 1 run 3, box 3"
              " run 3) do not move with any candidate: they come from a layer before the"
              " profile (the pieces SAM and the fill rules give).",
              "- Two photos with held-out runs, five Nevada runs: far too few for a confidence"
              " interval. Ready to learn: each approved box of a site adds its corrected runs."]
    (OUT / "learning.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    curve_svg([("from the default", "#16181c", from_default[site]),
               (f"from a poor start {POOR_START}", "#d9822b", from_poor[site])],
              OUT / "learning.svg")  # fmt: skip
    print("\n".join(lines))


if __name__ == "__main__":
    main()
