# Provenance of the open-weight models

CoreSight describes core (lithology, alteration, mineralization, anomaly flags) with three backends behind one Pydantic contract (`schemas.ModelDescription`).
Two of them are Meta open-weight models. This page says where their weights come from, how they were run and how to check every published output.
The machine-readable version is [`outputs/describe/provenance.json`](../outputs/describe/provenance.json), written by `scripts/provenance.py` from what is on disk.

| | Muse Glimmer | Muse Spark Open |
|---|---|---|
| Where it runs | Our own laptop, llama.cpp, no network needed | Baseten Model APIs (hosted) |
| Weights | [`meta-models/Muse-Glimmer-30B-GGUF`](https://huggingface.co/meta-models/Muse-Glimmer-30B-GGUF), revision `b44f1072cf75e918a1b82a3a17b45c4389b076e7` | [`meta-models/Muse-Spark-Open-816B-A42B`](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B), served by Baseten |
| License | Apache 2.0 ([dev.meta.ai/docs/muse-glimmer](https://dev.meta.ai/docs/muse-glimmer/)) | Muse Model License ([dev.meta.ai/docs/muse-spark-open](https://dev.meta.ai/docs/muse-spark-open/)) |
| Model ID in our code | `muse-glimmer` (alias given to llama-server) | `meta-models/muse-spark-open-1026` |
| Client | [`glimmer_client.py`](../src/coresight/glimmer_client.py) | [`baseten_client.py`](../src/coresight/baseten_client.py) |
| Same 14 public crops | 14/14 valid, 327 s per item | 14/14 valid, 14.8 s per item |
| Cost of the 14 | $0 (our hardware; electricity not counted) | $0.1755 from token usage |

## Muse Glimmer

### Weights

Downloaded from Meta's official repo, as [dev.meta.ai/docs/muse-glimmer/get-the-model](https://dev.meta.ai/docs/muse-glimmer/get-the-model) says. The repo is not gated.

| File | Bytes | SHA-256 | Same as Hugging Face |
|---|---|---|---|
| `Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf` (text model) | 16,756,683,904 | `4cc57c0f51040a226e5a72cc47b7613f7772950e460a665f7083de89f183f60e` | yes |
| `mmproj-Muse-Glimmer-30B-Q4_K_M.gguf` (vision projector) | 1,400,328,928 | `f48b452316f9b213758e8659444029b961a24a07f99a1abb2a9f88b06f7c00c6` | yes |

The hashes were computed on our copy and compared with the LFS object IDs Hugging Face publishes for that revision (an LFS object ID is the file's SHA-256).
The GGUF headers say: architecture `muse-glimmer`, size label 28B, file type 15 (Q4_K_M); projector architecture `clip`, 1.9B.

### Runtime

- llama.cpp build 11913 (commit `7aca0d2ea`), Windows x86_64 binaries with CUDA 12.4.
- Laptop: Intel Core i7-12700H, 64 GB RAM, NVIDIA RTX 3070 Ti Laptop GPU with 8 GB. The 17 GB model does not fit in 8 GB, so llama.cpp keeps part of it on the CPU (`-ngl auto` with `--fit on`, the defaults).
- Command:

```
llama-server -m Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -a muse-glimmer -c 16384 --host 127.0.0.1 --port 8080
```

- Request: OpenAI-compatible `/v1/chat/completions`, image as a base64 PNG, `response_format` json_schema (llama.cpp turns it into a grammar), temperature 0.2. The server listens on 127.0.0.1 only.

### What the run logged

From llama-server's own log for the 14 calls: 16,596 prompt tokens at 105 tokens/s and 8,671 generated tokens at 1.96 tokens/s.
That is why one description takes about 5 minutes on this laptop. Meta's docs say this file fits under 24 GB of VRAM; we have not measured the speed on such a GPU.

### Offline

`scripts/offline_glimmer.py` first checks that dev.meta.ai, huggingface.co and 1.1.1.1 cannot be reached, then describes a public photo with the cache off and logs the hashes of the image and the answer in `outputs/describe/offline_runs.jsonl`.
The screen recording of that run is the offline evidence (see [`CLIP_GLIMMER.md`](CLIP_GLIMMER.md)).

## Muse Spark Open

- Served by [Baseten Model APIs](https://www.baseten.co/library/muse-spark-open/) at `https://inference.baseten.co/v1/chat/completions`.
- Model ID `meta-models/muse-spark-open-1026`: the ID Baseten enabled for our key (mail of 27 Oct), not the `meta-models/muse-spark-open` in their docs.
- Price used for the cost column: $1.25 input and $4.25 output per million tokens (baseten.co/pricing, 27 Oct 2026). Reasoning tokens are billed as output.
- Same prompt, image and schema as the other backends. Only the answer (`content`) is parsed; the reasoning is not kept.
- The weights are not on our machine, so there is no hash of them. What can be checked is each answer.

## Checking a published answer

Every answer is in `outputs/describe/<backend>/<item>.json`, and `provenance.json` lists the SHA-256 of each file with its time and cost.
The side-by-side comparison with Muse Spark (API) is in [`outputs/describe/compare.md`](../outputs/describe/compare.md).

Reproduce:

```
.venv\Scripts\python scripts\describe_boxes.py --backend glimmer
.venv\Scripts\python scripts\describe_boxes.py --backend baseten
.venv\Scripts\python scripts\provenance.py --weights D:\models\glimmer --llama-server D:\models\llama.cpp\llama-server.exe --server-log D:\models\llama-server.log --check-hf
```

Only public photos (Wikimedia Commons, listed in `data/labels/SOURCES.md`) were sent to either backend.
