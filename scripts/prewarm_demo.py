"""Warm the demo before a judge arrives (point G), and check that it is complete.

    .venv\\Scripts\\python scripts/prewarm_demo.py https://coresight.analizac.com

Runs every public sample once through the real server, so each SAM and Muse
Spark answer is in the cache volume and a sample opens in seconds without
paying again; then the tour's refused screenshot. It reports, per sample, how
many model calls were live and how many came from the cache: a second run must
show 0 live calls. Last, it checks /api/showcase: the home page and the tour
need a Nevada box 3, an approved box whose agents finished and its hole, all
pinned (read-only for every visitor). The sample boxes this script opens are its
own copies (one cookie for the whole run): nobody else sees them.
The agents are never started here (approving is the geologist's step).
"""

from __future__ import annotations

import sys
import time

import httpx


def wait_box(http: httpx.Client, box_id: str, timeout_s: float = 600) -> dict:
    t0 = time.time()
    while True:
        box = http.get(f"/api/boxes/{box_id}").raise_for_status().json()
        if box["status"] != "processing" or time.time() - t0 > timeout_s:
            return box
        time.sleep(2)


def main(base: str) -> int:
    http = httpx.Client(base_url=base.rstrip("/"), timeout=60)
    ok = True
    for sample in http.get("/api/samples").raise_for_status().json():
        t0 = time.time()
        started = http.post(f"/api/samples/{sample['name']}").raise_for_status().json()
        box = wait_box(http, started["id"])
        live = sum(s["calls"] for s in box["stages"])
        cached = sum(s["cached"] for s in box["stages"])
        print(f"{sample['name']:<18} {box['status']:<9} {time.time() - t0:5.1f} s  "
              f"live calls {live:>2}, from cache {cached:>2}")  # fmt: skip
        ok &= box["status"] == "ready"
    refused = wait_box(http, http.post("/api/tour/not-a-box").raise_for_status().json()["id"])
    gate = refused.get("gate") or {}
    print(f"{'not-a-box':<18} {refused['status']:<9} gate ok={gate.get('ok')}")
    ok &= refused["status"] == "failed" and gate.get("ok") is False
    show = http.get("/api/showcase").raise_for_status().json()
    print(f"showcase           {show}")
    missing = [k for k, v in show.items() if not v]
    for key in ("box", "agents_box"):
        if show.get(key) and not http.get(f"/api/boxes/{show[key]}").json().get("pinned"):
            missing.append(f"{key} pinned")
    if missing:
        print(f"Missing for the home page and the tour: {', '.join(missing)}. Approve a"
              " Nevada box 3 (after box 1) in the app, as a geologist would, pin it with"
              " POST /api/ops/pin/{id} and the ops token, then rerun.")
    return 0 if ok and not missing else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"))
