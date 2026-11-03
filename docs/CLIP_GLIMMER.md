# Muse Glimmer in a container with no network

How the no-network run in the video was made, and how to repeat it.
Its log: [`outputs/describe/offline_run.log`](../outputs/describe/offline_run.log). Its record, with the hashes: [`outputs/describe/offline_runs.jsonl`](../outputs/describe/offline_runs.jsonl).

The model server runs in a container with `--network none`. The client joins that container's network, so it only sees `lo`, and `scripts/offline_glimmer.py` stops if it can reach dev.meta.ai, huggingface.co or 1.1.1.1. Only `src`, `scripts`, the photo and `outputs/describe` are mounted. `.env` is not.

This is a container with no network, not an air-gapped machine: the laptop itself stayed online.
It is one description. It took 863 s, against 327 s per item in the earlier 14 crops, which ran on another llama.cpp build, outside Docker.

```powershell
docker build -t coresight-offline-client -f deploy/offline-client.Dockerfile deploy

docker run --name glimmer-offline --network none --gpus all -v D:/models/glimmer:/models:ro ghcr.io/ggml-org/llama.cpp:server-cuda -m /models/Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf --mmproj /models/mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -a muse-glimmer -c 16384 --host 127.0.0.1 --port 8080

docker inspect glimmer-offline --format "Network mode: {{.HostConfig.NetworkMode}}"

docker run --rm --network container:glimmer-offline -e PYTHONUNBUFFERED=1 -v D:/Repos/coresight/src:/app/src:ro -v D:/Repos/coresight/scripts:/app/scripts:ro -v D:/Repos/coresight/data/raw/commons_potter_07.jpg:/app/data/raw/commons_potter_07.jpg:ro -v D:/Repos/coresight/outputs/describe:/app/outputs/describe coresight-offline-client python scripts/offline_glimmer.py
```

Run the server in its own terminal and leave it up. The photo is `data/raw/commons_potter_07.jpg` (Wikimedia Commons, listed in `data/labels/SOURCES.md`).
The video replays lines of this log with the wait sped up. It is not a screen recording.
