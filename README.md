# CoreSight

**Automated drill-core logging from core box photos.**
Built by AnaliZac, an AI consultancy in Zacatecas, Mexico's leading silver-producing state, for the Meta Global AI Developer Hackathon (Startup track, theme *Push the Frontier*).

After every drill hole, geologists log core boxes by hand: they measure RQD, count fractures, estimate recovery and describe lithology, alteration and mineralization. It is slow and subjective, and it becomes the bottleneck between drilling and the resource model.

CoreSight takes an ordinary photo of a core box and returns a structured geotechnical and geological log per interval. A geologist reviews and approves it.

## How it works

The pipeline is neurosymbolic: Meta's models perceive and describe, and a deterministic engine does the math. Every number in the log can be traced back to the piece lengths that produced it.

| Stage | Module | Technology |
|---|---|---|
| 1. Calibration: box edges, scale markers, px to cm, row split | `pipeline.calibrate` | OpenCV |
| 2. Segmentation: intact pieces and fractures per row | `pipeline.segment`, `meta_client` | SAM 3.1 (Meta Model API) |
| 3. Geometry: piece lengths, RQD, fracture frequency, recovery | `geometry.py` | Deterministic Python, no LLM |
| 4. Description: lithology, alteration, mineralization, anomaly flags | `pipeline.describe`, `meta_client` | Muse Spark, Pydantic-validated JSON |
| 5. Review: geologist corrects breaks, pieces and descriptions by typing or by voice; numbers are recalculated by the geometry engine; corrections are kept next to the original; CSV export | `api.py`, `review.py`, `web/index.html` | FastAPI, Muse Voice Transcribe |
| 6. Area agents: an orchestrator routes each approved box to the lab, safety and geotechnics, the processing plant and finance; each agent drafts, a human approves | `pipeline.draft_handoffs` | Muse Wonder (orchestrator), Muse Spark with tools |

Stage 4 can also run on Muse Glimmer on the mine's own hardware (offline mode), with the same validated output.

## Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # add your Meta Model API key
pytest
uvicorn coresight.api:app        # review page at http://127.0.0.1:8000
```

## Evaluation

RQD and TCR per drilling run, compared with logs made by people. Only runs seen whole in one photo are scored.

**Headline: RQD mean absolute error 9.9 points over 39 runs** (`sam+fill+profile`, no help from the geologist's paint marks).
TCR mean absolute error: 5.3 points.

| Method | RQD MAE (bias) | TCR MAE (bias) |
|---|---|---|
| `sam`: SAM 3.1 pieces only | 10.9 (-5.3) | 8.6 (+1.3) |
| `sam+fill`: plus geotechnical rules for gaps | 11.5 (-3.2) | 5.3 (+5.1) |
| `sam+fill+profile`: plus an intensity profile along the core axis | **9.9 (-6.1)** | 5.3 (+5.1) |
| `sam+fill+profile+marks`: plus the red break marks the geologist painted on the core | 8.6 (-4.2) | 5.3 (+5.1) |

What the numbers rest on:
- 34 runs from the [Mining Core Sampling Dataset](https://www.kaggle.com/datasets/imoore/mining-core-sampling-dataset) (Kaggle, CC BY-NC-SA 4.0). The reference is the RQD and recovery the mine geologist wrote on each box lid. These photos and reference values are not in the repo or the demo (non-commercial license); only our errors are published.
- 5 runs from two public Onkalo boxes (Commons, CC BY-SA 4.0), labelled by us on the same photo. They are a small sample and should not be read as a separate result.
- The `+marks` variant reads marks the geologist already made, so it is not the headline.
- The negative RQD bias means CoreSight tends to see more breaks than the geologist, the conservative direction for ground support.

Files: [`outputs/eval/report.md`](outputs/eval/report.md) (per site, plus the largest errors) and [`outputs/eval/runs.csv`](outputs/eval/runs.csv) (error per run and method). Reproduce with `python scripts/eval_logs.py` once the Kaggle set is in `data/raw/`.

Descriptions: the same 14 public crops (Onkalo, Potter Mine and Warren County, all from Commons) described by Muse Spark (API), Muse Spark Open on Baseten and Muse Glimmer on our own machine with llama.cpp, all 14/14 valid against the same Pydantic contract. Side by side with time and cost in [`outputs/describe/compare.md`](outputs/describe/compare.md); raw outputs in `outputs/describe/<backend>/`.

Still to come: confidence intervals, Bland-Altman and comparison with the spread between geologists reported in the literature.

## Built before the hackathon

The hackathon kicked off on Oct 26, 2026 at 12:00 PM ET. These four commits were made on Oct 25, before kickoff. Everything after commit `013503a` was built during the hackathon.

| Commit | What existed before kickoff |
|---|---|
| `1d32fde` | Project scaffold: `pyproject.toml`, Pydantic contracts (`schemas.py`), the deterministic geometry engine (`geometry.py`: RQD, TCR, fracture frequency, mechanical break merging) with its tests, pipeline stubs (`pipeline.py`), CI workflow, day-by-day plan (`docs/PLAN.md`) |
| `fb53c33` | CI switched to manual runs |
| `3a7c613` | Survey of public core photo sources and their licenses (`data/labels/SOURCES.md`) |
| `013503a` | Script that downloads the public photos (`scripts/fetch_public_images.py`); `meta_client.py` written from the public Meta Model API docs (not yet run against the API); day 1 smoke test script (`scripts/smoke_day1.py`); SAM response parser tests |

Not built before kickoff: calibration, SAM segmentation of rows into pieces, wiring the geometry engine to real photos, Muse Spark descriptions and anomaly flags, the review UI and CSV export, the lab and safety hand-offs, the evaluation, and the demo.

## Built with Muse Code

`src/coresight/verify.py`, the deterministic check every area draft must pass before a person can approve it, was written by Muse Code 1.4.13 against a spec of 20 tests (`tests/test_verify.py`) that we wrote first.

- Two headless runs: `muse exec --contributor-mode off --disable-approval --json`, sandbox on.
- Round 1 (session `bbc6432a-3cb8-407d-8572-921d33527e31`): the full verifier from the first 15 tests.
- Round 2 (session `88fc39bc-b75a-47b0-8d5f-466e68048e0a`): a ruff fix and 5 new tests (budget left after earlier boxes, numbers from the hole history, runs named from one).
- Muse's Windows sandbox could not start PowerShell on this machine, so it could not run the tests itself. We ran pytest and ruff outside it after each round and sent the results back. We did not edit its code.
- Traces of both runs (prompt, every tool step, final answer, token usage) are in [`docs/muse-code/`](docs/muse-code/).

## Status

Working end to end: calibration, SAM 3.1 segmentation, geometry, Muse Spark descriptions on three backends, the review page with voice corrections and CSV export. Live demo at https://coresight.analizac.com.
In progress: the area agents (stage 6): orchestrator, four drafting agents and the verifier are built and tested with a simulated API. Day-by-day plan in `docs/PLAN.md`.

## License

Apache License 2.0, see [`LICENSE`](LICENSE). Public images keep their own licenses, listed in `data/labels/SOURCES.md`.
