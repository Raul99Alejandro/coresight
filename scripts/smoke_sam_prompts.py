"""Smoke test: SAM 3.1 box and point prompts on a real core row (prepares days B and C).

Docs: https://dev.meta.ai/docs/sam/segmenting, "Prompt with boxes and points"
(read 2026-10-27). One row of the Nevada U12G sample (U.S. DOE, public domain)
goes to SAM three times through meta_client:

1. the concept prompt the pipeline uses today ("stone"), as the baseline;
2. a box prompt on one piece found in 1;
3. a positive point on another piece and a negative point on the gap next to it.

Done when 2 and 3 come back under our object ids with a mask and a confidence.
Prints what came back and writes outputs/smoke/sam_prompts.json and a picture.
Needs META_API_KEY in .env; answers are cached like every SAM call.

    .venv\\Scripts\\python scripts\\smoke_sam_prompts.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from coresight.calibration import find_trays
from coresight.meta_client import MetaClient, parse_sam_text, sam_masks
from coresight.segmentation import PROMPT

ROOT = Path(__file__).resolve().parents[1]
PHOTO = ROOT / "data" / "raw" / "commons_nts_u12g_1.jpg"
OUT_DIR = ROOT / "outputs" / "smoke"
ROW = 0  # first row; "stone" finds nothing in the second (that is what B fixes)


def box_token(x1: int, y1: int, x2: int, y2: int, w: int, h: int) -> str:
    return f"<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}|>"


def point_token(x: int, y: int, w: int, h: int, negative: bool = False) -> str:
    return f"{'-' if negative else ''}<|point;x={x};y={y};w={w};h={h}|>"


def run(client: MetaClient, png: bytes, prompt: str) -> dict:
    t = time.perf_counter()
    text = client.segment_row_raw(png, prompt)
    seconds = time.perf_counter() - t
    records = parse_sam_text(text)
    masks = sam_masks(text)
    return {
        "prompt": prompt,
        "seconds": round(seconds, 2),  # near 0 when the answer came from the cache
        "records": [
            {"id": r["id"], "box": r["box"], "mask_marker": r["mask"].split(",")[-1][:1]}
            for r in records
        ],
        "confidences": [m["confidence"] for m in masks],
        "_masks": masks,
    }


def main() -> None:
    image = cv2.imread(str(PHOTO))
    if image is None:
        raise SystemExit(f"{PHOTO} is missing (run scripts/fetch_public_images.py first)")
    [tray] = find_trays(image, 66.0, n_rows=4, max_trays=1)
    crop = tray.row_crops(image)[ROW]
    h, w = crop.shape[:2]
    png = cv2.imencode(".png", crop)[1].tobytes()
    client = MetaClient()

    concept = run(client, png, PROMPT)
    pieces = sorted(concept["records"], key=lambda r: r["box"]["x1"])
    if len(pieces) < 3:
        raise SystemExit(f"the concept prompt found {len(pieces)} pieces; need 3 to go on")
    a, b, c = pieces[0]["box"], pieces[1]["box"], pieces[2]["box"]
    box_prompt = "<0f>1" + box_token(int(a["x1"]), int(a["y1"]), int(a["x2"]), int(a["y2"]), w, h)
    mid_y = int((b["y1"] + b["y2"]) / 2)
    inside = int((b["x1"] + b["x2"]) / 2)
    gap = min(int((b["x2"] + c["x1"]) / 2), w - 1)  # between two pieces: not core
    point_prompt = "<0f>2" + point_token(inside, mid_y, w, h) + point_token(gap, mid_y, w, h, True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = {"photo": PHOTO.name, "row": ROW, "crop_px": [w, h]}
    for name, prompt in [("concept", PROMPT), ("box", box_prompt), ("point", point_prompt)]:
        r = concept if name == "concept" else run(client, png, prompt)
        results[name] = {k: v for k, v in r.items() if k != "_masks"}
        print(f"{name}: {len(r['records'])} records, ids {[x['id'] for x in r['records']]}, "
              f"confidence {r['confidences']}, {r['seconds']} s")  # fmt: skip

        if name != "concept":
            view = crop.copy()
            for m in r["_masks"]:
                left, top, right, bottom = m["bounds"]
                part = m["mask"][: bottom - top, : right - left]
                region = view[top : top + part.shape[0], left : left + part.shape[1]]
                part = part.astype(bool)
                region[part] = np.clip(0.5 * region[part] + [90, 40, 200], 0, 255).astype(np.uint8)
            cv2.imwrite(str(OUT_DIR / f"sam_prompt_{name}.jpg"), view)

    (OUT_DIR / "sam_prompts.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
