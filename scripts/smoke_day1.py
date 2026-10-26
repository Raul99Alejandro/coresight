"""Day 1 smoke test: one photo through SAM 3.1 and Muse Spark.

Done when SAM returns masks and Muse Spark returns JSON that passes
GeologyDescription. Needs META_API_KEY in .env and the photos from
scripts/fetch_public_images.py. Outputs go to outputs/smoke/.

    .venv\\Scripts\\python scripts\\smoke_day1.py
    .venv\\Scripts\\python scripts\\smoke_day1.py --sam-image data\\raw\\commons_onkalo_2.jpg

The SAM masks are decoded with meta_sam_parser (SAM License) and drawn on the photo.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from coresight.meta_client import MetaClient, parse_sam_text, sam_masks

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "smoke"
MAX_SIDE = 2048


def load_png(path: Path) -> tuple[np.ndarray, bytes]:
    image = cv2.imread(str(path))
    if image is None:
        raise FileNotFoundError(f"{path} (run scripts/fetch_public_images.py first)")
    scale = MAX_SIDE / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"could not encode {path}")
    return image, buf.tobytes()


def draw_masks(image: np.ndarray, raw: str, out_path: Path) -> None:
    """Each mask filled in its own color, pasted at its bounds, with its box."""
    overlay = image.copy()
    rng = np.random.default_rng(0)
    for obj in sam_masks(raw):
        left, top, right, bottom = obj["bounds"]
        region = overlay[top:bottom, left:right]
        region[obj["mask"][: region.shape[0], : region.shape[1]]] = rng.integers(60, 255, 3)
        cv2.rectangle(overlay, (left, top), (right, bottom), (0, 0, 255), 2)
    cv2.imwrite(str(out_path), cv2.addWeighted(image, 0.4, overlay, 0.6, 0))


def run_sam(client: MetaClient, path: Path, prompt: str) -> bool:
    print(f"\n[SAM 3.1] {path.name}, prompt={prompt!r}")
    image, png = load_png(path)
    start = time.perf_counter()
    raw = client.segment_row_raw(png, prompt)
    elapsed = time.perf_counter() - start
    (OUT_DIR / "sam_raw.txt").write_text(raw, encoding="utf-8")
    records = parse_sam_text(raw)
    print(f"  {len(records)} objects in {elapsed:.1f}s, raw text in outputs/smoke/sam_raw.txt")
    for record in records[:5]:
        print(f"  id={record['id']} box={record['box']}")
    if records:
        draw_masks(image, raw, OUT_DIR / "sam_overlay.png")
        print("  overlay in outputs/smoke/sam_overlay.png")
    return bool(records)


def run_muse(client: MetaClient, path: Path) -> bool:
    print(f"\n[Muse Spark] {path.name}")
    _, png = load_png(path)
    start = time.perf_counter()
    description = client.describe_interval(png, {"hole_id": "smoke", "from_m": 0, "to_m": 1})
    elapsed = time.perf_counter() - start
    payload = description.model_dump(mode="json")
    (OUT_DIR / "muse_description.json").write_text(json.dumps(payload, indent=2), "utf-8")
    print(f"  valid GeologyDescription in {elapsed:.1f}s")
    print("  " + json.dumps(payload, indent=2).replace("\n", "\n  "))
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sam-image", type=Path, default=ROOT / "data/raw/commons_onkalo_1.jpg")
    # Tried on Onkalo 1 (Oct 26): "stone" 16 objects (c 0.8-0.9), "rock" 14 (c ~0.55),
    # "cylinder" 28 incl. box frame; "drill core", "core sample", "wooden box" 0.
    parser.add_argument("--prompt", default="stone")
    parser.add_argument("--muse-image", type=Path, default=ROOT / "data/raw/commons_potter_27.jpg")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = MetaClient()
    results = {}
    for name, step in (
        ("sam", lambda: run_sam(client, args.sam_image, args.prompt)),
        ("muse", lambda: run_muse(client, args.muse_image)),
    ):
        try:
            results[name] = step()
        except Exception as exc:  # report every failure, keep going
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            results[name] = False
    print(f"\nSAM masks: {'ok' if results['sam'] else 'NO'}")
    print(f"Muse Spark JSON: {'ok' if results['muse'] else 'NO'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
