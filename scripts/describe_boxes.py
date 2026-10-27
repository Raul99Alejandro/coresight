"""Day 6: describe the public boxes with one backend, to compare the describe backends.

Only public images (Commons, see data/labels/SOURCES.md); the Kaggle set is
never sent to a model here.

- Onkalo 1 (boxes 5 and 6): one description per run. Runs, markers and logs
  come from the piece sheets and the cached SAM masks, as in eval_logs.py, so
  the rule anomalies use the real TCR and FF.
- Onkalo 2 (same boxes, wet): one description per tray. Its run blocks are not
  measured, so there are no run crops and no rule anomalies.
- Potter and Warren close-ups: one description per photo.

The context sent to the model holds only the hole and depths, never the
Commons title, so the title can serve as a reference in compare.md.

    .venv\\Scripts\\python scripts\\describe_boxes.py --backend spark
    .venv\\Scripts\\python scripts\\describe_boxes.py --backend glimmer
    .venv\\Scripts\\python scripts\\describe_boxes.py --backend baseten

Backends: spark (Muse Spark, Meta Model API), glimmer (Muse Glimmer on
llama.cpp, local) and baseten (Muse Spark Open on Baseten Model APIs). Cost
is measured from the token usage where the price is known (Baseten); Glimmer
runs on our own hardware; Muse Spark runs on free credits and is not priced.

Writes outputs/describe/<backend>/<item>.json and outputs/describe/compare.md
(side by side, for every backend run so far). Answers are cached in
data/cache/describe/, so a second run costs nothing (and records no cost).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
from eval_logs import sheet_markers

from coresight.baseten_client import BasetenClient, cost_usd
from coresight.calibration import find_trays
from coresight.describe import Describer, png_bytes
from coresight.glimmer_client import GlimmerClient
from coresight.labeling import PieceSheet
from coresight.meta_client import MetaClient
from coresight.pipeline import build_logs, describe_photo, describe_runs, segment
from coresight.schemas import BoxLabel

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
LABELS = ROOT / "data" / "labels"
OUT_DIR = ROOT / "outputs" / "describe"
ONKALO_BOX_CM = 100.0

ONKALO_REF = "Olkiluoto, Finland, crystalline bedrock (no published log for these boxes)"
CLOSE_UPS = {
    "commons_potter_07": "Polymetallic massive sulfide, Potter Mine (Commons title)",
    "commons_potter_27": "Polymetallic massive sulfide, Potter Mine (Commons title)",
    "commons_potter_28": "Polymetallic massive sulfide, Potter Mine (Commons title)",
    "commons_potter_30": "Polymetallic massive sulfide, Potter Mine (Commons title)",
    "commons_potter_32": "Polymetallic massive sulfide, Potter Mine (Commons title)",
    "commons_potter_argillite_2": "Sulfidic argillite and polymetallic massive sulfide (title)",
    "commons_warren_dolostone_1": "Dolostone, Knox Dolomite, Warren County core (Commons title)",
}


BACKENDS = {"spark": MetaClient, "glimmer": GlimmerClient, "baseten": BasetenClient}


def timed(describer: Describer, fn, *args) -> tuple[object, dict]:
    """(result, {"seconds", "error", "cost_usd"}) of one call; errors do not stop the sample."""
    paid = len(getattr(describer, "usage", []))
    start = time.perf_counter()
    result, error = None, None
    try:
        result = fn(*args)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]
    meta = {"seconds": time.perf_counter() - start, "error": error, "cost_usd": None}
    if isinstance(describer, GlimmerClient):
        meta["cost_usd"] = 0.0
    elif hasattr(describer, "usage"):
        meta["cost_usd"] = sum(cost_usd(u) for u in describer.usage[paid:])
    return result, meta


def onkalo_runs(describer: Describer, sam: MetaClient) -> dict[str, dict]:
    out = {}
    image = cv2.imread(str(RAW / "commons_onkalo_1.jpg"))
    for tray_index, name in enumerate(["ONK-DTPH5.1_box05", "ONK-DTPH5.1_box06"]):
        label = BoxLabel.model_validate_json((LABELS / f"{name}.json").read_text("utf-8"))
        sheet = PieceSheet.model_validate_json((LABELS / "pieces" / f"{name}.json").read_text())
        tray = find_trays(image, ONKALO_BOX_CM, max_trays=tray_index + 1)[tray_index]
        markers = sheet_markers(sheet, tray)
        rows, _ = segment(image, tray, sam)
        logs = build_logs(rows, markers, list(label.runs), first_starts_in_box=True)
        context = {"hole_id": label.hole_id, "box": label.box_number}
        result, meta = timed(
            describer, describe_runs, image, tray, markers, logs, describer, context
        )
        for i, log in enumerate(logs):
            item = {"reference": ONKALO_REF, **meta, "seconds": meta["seconds"] / len(logs)}
            if meta["cost_usd"] is not None:
                item["cost_usd"] = meta["cost_usd"] / len(logs)
            item["log"] = log.model_dump()
            if result:
                item["description"] = result[i].description.model_dump(mode="json")
            out[f"onkalo1_{name}_run{i + 1}"] = item
    return out


def onkalo_wet_trays(describer: Describer) -> dict[str, dict]:
    out = {}
    image = cv2.imread(str(RAW / "commons_onkalo_2.jpg"))
    for i, tray in enumerate(find_trays(image, ONKALO_BOX_CM, max_trays=2)):
        png = png_bytes(tray.straighten(image))
        result, meta = timed(
            describer, describer.describe_interval, png, {"hole_id": "ONK-DTPH5.1"}
        )
        item = {"reference": ONKALO_REF + ", wet", **meta}
        if result:
            item["description"] = result.model_dump(mode="json")
        out[f"onkalo2_tray{i + 1}"] = item
    return out


def close_ups(describer: Describer) -> dict[str, dict]:
    out = {}
    for stem, reference in CLOSE_UPS.items():
        path = RAW / f"{stem}.jpg"
        result, meta = timed(describer, describe_photo, path, describer, {})
        item = {"reference": reference, **meta}
        if result:
            item["description"] = result.model_dump(mode="json")
        out[stem] = item
    return out


def cell(item: dict | None, key: str) -> str:
    if item is None:
        return "(not run)"
    if item.get("error"):
        return "error: " + item["error"][:80] if key == "lithology" else ""
    d = item["description"]
    if key == "anomalies":
        text = "; ".join(f"{a['type']} ({a['source']}): {a['explanation']}" for a in d[key])
        return text or "none"
    return str(d[key])


def money(usd: float | None) -> str:
    return "not priced" if usd is None else f"${usd:.4f}"


def write_compare() -> Path:
    results = {}
    for folder in sorted(p for p in OUT_DIR.iterdir() if p.is_dir()):
        results[folder.name] = {
            f.stem: json.loads(f.read_text(encoding="utf-8")) for f in folder.glob("*.json")
        }
    backends = list(results)
    items = sorted({k for r in results.values() for k in r})
    lines = ["# Descriptions: " + " vs ".join(backends), ""]
    lines.append("Reference is what the source says, not a geologist's log of these crops.")
    lines += ["", "| Backend | Valid | Seconds per item | Total cost |", "|---|---|---|---|"]
    for b in backends:
        done = [i for i in results[b].values() if not i.get("error")]
        secs = sum(i["seconds"] for i in results[b].values()) / max(len(results[b]), 1)
        known = [i["cost_usd"] for i in results[b].values() if i.get("cost_usd") is not None]
        total = money(sum(known)) if known else money(None)
        lines.append(f"| {b} | {len(done)}/{len(results[b])} | {secs:.1f} | {total} |")
    for name in items:
        any_item = next(r[name] for r in results.values() if name in r)
        lines += ["", f"## {name}", "", f"Reference: {any_item['reference']}"]
        if "log" in any_item:
            log = any_item["log"]
            lines.append(
                f"Run {log['from_m']}-{log['to_m']} m: RQD {log['rqd_pct']}, TCR {log['tcr_pct']},"
                f" FF {log['fracture_frequency_per_m']}/m (geometry.py)"
            )
        lines += ["", "| | " + " | ".join(backends) + " |", "|---" * (len(backends) + 1) + "|"]
        for key in ("lithology", "alteration", "mineralization", "anomalies", "confidence"):
            row = [cell(results[b].get(name), key).replace("|", "/") for b in backends]
            lines.append(f"| {key} | " + " | ".join(row) + " |")
        seconds = [
            f"{results[b][name]['seconds']:.1f}" if name in results[b] else "" for b in backends
        ]
        lines.append("| seconds | " + " | ".join(seconds) + " |")
        costs = [
            money(results[b][name].get("cost_usd")) if name in results[b] else "" for b in backends
        ]
        lines.append("| cost | " + " | ".join(costs) + " |")
    path = OUT_DIR / "compare.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=list(BACKENDS), required=True)
    args = parser.parse_args()
    describer = BACKENDS[args.backend]()
    sam = describer if isinstance(describer, MetaClient) else MetaClient()  # cached SAM only
    out_dir = OUT_DIR / args.backend
    out_dir.mkdir(parents=True, exist_ok=True)
    items = {**onkalo_runs(describer, sam), **onkalo_wet_trays(describer), **close_ups(describer)}
    for name, item in items.items():
        (out_dir / f"{name}.json").write_text(json.dumps(item, indent=1), encoding="utf-8")
        status = item["error"] or item["description"]["lithology"][:70]
        print(f"{name:40s} {item['seconds']:6.1f}s  {status}")
    print(f"wrote {write_compare()}")


if __name__ == "__main__":
    main()
