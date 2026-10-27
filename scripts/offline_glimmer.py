"""Day 9: one Muse Glimmer description with the network off, for the offline clip.

1. Checks that the machine is offline: a TCP connection to dev.meta.ai,
   huggingface.co and 1.1.1.1 must fail. If one works, it stops.
2. Describes one public crop with Glimmer on the local llama-server, with the
   cache off, so the answer is computed now and not read from disk.
3. Prints the answer validated against ModelDescription and appends a record
   (time, image and answer SHA-256, seconds) to outputs/describe/offline_runs.jsonl.

Start llama-server first (docs/CLIP_GLIMMER.md), then:

    .venv\\Scripts\\python scripts\\offline_glimmer.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2

from coresight.describe import png_bytes
from coresight.glimmer_client import GlimmerClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "describe" / "offline_runs.jsonl"
PROBES = (("dev.meta.ai", 443), ("huggingface.co", 443), ("1.1.1.1", 53))


def online() -> list[str]:
    reached = []
    for host, port in PROBES:
        try:
            socket.create_connection((host, port), timeout=3).close()
            reached.append(f"{host}:{port}")
        except OSError:
            pass
    return reached


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image", default="data/raw/commons_potter_07.jpg")
    args = p.parse_args()

    reached = online()
    if reached:
        raise SystemExit(f"Not offline: reached {', '.join(reached)}. Turn the network off.")
    print("Network: off (dev.meta.ai, huggingface.co and 1.1.1.1 unreachable)")

    image_png = png_bytes(cv2.imread(str(ROOT / args.image)))
    client = GlimmerClient(cache_dir=None)
    print(f"Muse Glimmer on {client._http.base_url}, describing {args.image} ...")
    start = time.perf_counter()
    description = client.describe_interval(image_png, {"source": "public Commons photo"})
    seconds = time.perf_counter() - start
    answer = description.model_dump_json(indent=1)
    print(answer)
    print(f"Valid GeologyDescription in {seconds:.0f} s, no network.")

    record = {
        "utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "image": args.image,
        "image_sha256": hashlib.sha256(image_png).hexdigest(),
        "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
        "seconds": round(seconds, 1),
        "offline_probes": [f"{h}:{p}" for h, p in PROBES],
    }
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    print(f"Recorded in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
