"""Day 9: provenance manifest of the open-weight runs (Muse Glimmer, Muse Spark Open).

Reads what is on disk and writes outputs/describe/provenance.json:

- Glimmer weights: file name, size, SHA-256 and the GGUF header (architecture,
  size label, file type) of the model and of the vision projector.
- The same hashes as published by Meta on Hugging Face (``--check-hf``): the
  LFS object ID of a file there is its SHA-256.
- Runtime: the llama.cpp build (``llama-server --version``) and the timings
  llama-server logged for every call (prompt and generated tokens, speed).
- Every description in outputs/describe/<backend>/: seconds, cost and the
  SHA-256 of the saved answer, so a published output can be checked.
- Muse Spark Open: the Baseten model ID, endpoint and prices from
  coresight.baseten_client.

Nothing here calls a model. Hashing the 17 GB file takes about a minute.

    .venv\\Scripts\\python scripts\\provenance.py --weights D:\\models\\glimmer
        --llama-server D:\\models\\llama.cpp\\llama-server.exe
        --server-log D:\\models\\llama-server.log
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import struct
import subprocess
from pathlib import Path

import httpx

from coresight import baseten_client, glimmer_client

ROOT = Path(__file__).resolve().parents[1]
DESCRIBE = ROOT / "outputs" / "describe"
GGUF_TYPES = {
    0: "B",
    1: "b",
    2: "H",
    3: "h",
    4: "I",
    5: "i",
    6: "f",
    7: "?",
    10: "Q",
    11: "q",
    12: "d",
}
GGUF_KEYS = (
    "general.architecture",
    "general.name",
    "general.size_label",
    "general.file_type",
    "general.quantization_version",
    "general.license",
    "general.url",
)
HF_REPO = "meta-models/Muse-Glimmer-30B-GGUF"  # dev.meta.ai/docs/muse-glimmer/get-the-model
TIMING = re.compile(r"(prompt eval|eval) time =\s+([\d.]+) ms /\s+(\d+) tokens")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 24):
            h.update(chunk)
    return h.hexdigest()


def gguf_header(path: Path) -> dict:
    """The scalar and string keys of a GGUF v3 header that say what the file is."""

    def read(f, fmt):
        return struct.unpack("<" + fmt, f.read(struct.calcsize("<" + fmt)))[0]

    def string(f):
        return f.read(read(f, "Q")).decode("utf-8", "replace")

    def value(f, t):
        if t == 8:
            return string(f)
        if t == 9:
            et, n = read(f, "I"), read(f, "Q")
            return [value(f, et) for _ in range(n)]
        return read(f, GGUF_TYPES[t])

    out = {}
    with path.open("rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError(f"{path} is not a GGUF file")
        out["gguf_version"] = read(f, "I")
        out["tensors"] = read(f, "Q")
        for _ in range(read(f, "Q")):
            key, t = string(f), read(f, "I")
            v = value(f, t)
            if key in GGUF_KEYS:
                out[key] = v
    return out


def hf_files() -> tuple[str, dict[str, str]]:
    """Revision of the official GGUF repo and the SHA-256 of each file in it."""
    api = f"https://huggingface.co/api/models/{HF_REPO}"
    revision = httpx.get(api, timeout=30).raise_for_status().json()["sha"]
    tree = httpx.get(f"{api}/tree/{revision}", timeout=30).raise_for_status().json()
    return revision, {f["path"]: f["lfs"]["oid"] for f in tree if "lfs" in f}


def server_timings(log: Path) -> dict:
    prompt, gen = [], []
    for kind, ms, tokens in TIMING.findall(log.read_text("utf-8", errors="replace")):
        (prompt if kind == "prompt eval" else gen).append((float(ms), int(tokens)))
    return {
        "calls": len(gen),
        "prompt_tokens": sum(t for _, t in prompt),
        "generated_tokens": sum(t for _, t in gen),
        "prompt_tokens_per_s": round(
            sum(t for _, t in prompt) / sum(ms for ms, _ in prompt) * 1e3, 1
        ),
        "generated_tokens_per_s": round(sum(t for _, t in gen) / sum(ms for ms, _ in gen) * 1e3, 2),
    }


def outputs(backend: str) -> list[dict]:
    items = []
    for path in sorted((DESCRIBE / backend).glob("*.json")):
        data = json.loads(path.read_text("utf-8"))
        items.append(
            {
                "item": path.stem,
                "valid": data.get("error") is None,
                "seconds": round(data["seconds"], 1),
                "cost_usd": data.get("cost_usd"),
                "output_sha256": sha256(path),
            }
        )
    return items


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, required=True, help="folder with the Glimmer GGUF files")
    p.add_argument("--llama-server", type=Path, required=True)
    p.add_argument("--server-log", type=Path, required=True)
    p.add_argument("--check-hf", action="store_true", help="compare hashes with Hugging Face")
    args = p.parse_args()

    version = subprocess.run(
        [str(args.llama_server), "--version"], capture_output=True, text=True, check=True
    )
    weights = []
    for path in sorted(args.weights.glob("*.gguf")):
        print(f"hashing {path.name}")
        weights.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "header": gguf_header(path),
            }
        )
    source: dict = {"hugging_face": f"https://huggingface.co/{HF_REPO}"}
    if args.check_hf:
        revision, published = hf_files()
        source["revision"] = revision
        for w in weights:
            w["matches_hugging_face"] = published.get(w["file"]) == w["sha256"]
    manifest = {
        "about": "Provenance of the open-weight description runs. See docs/PROVENANCE.md.",
        "muse_glimmer": {
            "source": source,
            "license": "Apache-2.0 (dev.meta.ai/docs/muse-glimmer)",
            "served_as": glimmer_client.GLIMMER_MODEL_ID,
            "weights": weights,
            "runtime": {
                "llama_cpp": " ".join((version.stdout + version.stderr).split()),
                "os": platform.platform(),
            },
            "server_log": server_timings(args.server_log),
            "outputs": outputs("glimmer"),
        },
        "muse_spark_open": {
            "provider": "Baseten Model APIs",
            "license": "Muse Model License (dev.meta.ai/docs/muse-spark-open)",
            "model_id": baseten_client.MUSE_SPARK_OPEN_MODEL_ID,
            "endpoint": baseten_client.DEFAULT_BASE_URL + "/chat/completions",
            "usd_per_million_tokens": {
                "input": baseten_client.PRICE_INPUT_PER_M,
                "output": baseten_client.PRICE_OUTPUT_PER_M,
            },
            "outputs": outputs("baseten"),
        },
    }
    out = DESCRIBE / "provenance.json"
    out.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
