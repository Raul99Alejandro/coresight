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

**Headline: RQD mean absolute error 11.2 points, 95% CI 6.1 to 18.9, over 34 runs in 11 boxes**, against the mine geologist's own log, with no help from the geologist's paint marks (`sam+fill+profile`).
The interval is a bootstrap that resamples whole boxes, since runs of one box share a photo and a calibration.

| Measure (`sam+fill+profile`, mine geologist as reference, n=34) | Result |
|---|---|
| RQD MAE [95% CI] | 11.2 [6.1, 18.9] points |
| RQD bias | -6.9 points (CoreSight sees more breaks: the conservative side for ground support) |
| Bland-Altman 95% limits of agreement | -40.2 to +26.3 points |
| Same Deere class / same or next class | 71% / 88% |
| TCR MAE [95% CI] | 6.1 [3.1, 9.8] points |

Ablation, same 34 runs:

| Method | RQD MAE [95% CI] | TCR MAE [95% CI] |
|---|---|---|
| `sam`: SAM 3.1 pieces only | 11.5 [6.4, 19.0] | 8.9 [3.7, 16.3] |
| `sam+fill`: plus geotechnical rules for gaps | 13.1 [6.7, 22.5] | 6.1 [3.1, 9.8] |
| `sam+fill+profile`: plus an intensity profile along the core axis | **11.2 [6.1, 18.9]** | 6.1 [3.1, 9.8] |
| `sam+fill+profile+marks`: plus the red break marks the geologist painted on the core | 9.7 [5.8, 15.4] | 6.1 [3.1, 9.8] |

The intervals overlap: with 11 boxes, no step of the ablation is a proven gain on its own.

Public boxes, labelled by us on the same photo (small, not an independent result):

| Boxes | Runs | RQD MAE | What it shows |
|---|---|---|---|
| Onkalo, dry (2 boxes) | 5 | 1.1 | Sound crystalline rock is easy |
| Onkalo, the same boxes wet | 5 | 12.3 | Wet dark core: SAM splits one intact piece into many (photo below) |
| Nevada U12G (1 box) | 3 | 23.6 | Broken core, with run cards and wax-sealed samples in the tray |

Failure cases, public photos only, with the breaks CoreSight found drawn on the tray: [`failures/ONK-DTPH5.1_box05_wet.jpg`](outputs/eval/failures/ONK-DTPH5.1_box05_wet.jpg) (RQD error -49 on one wet run) and [`failures/U12G-GF-GT2_box01.jpg`](outputs/eval/failures/U12G-GF-GT2_box01.jpg).
The worst Kaggle runs (errors down to -49) are listed by depth in the report, without photos.

How this compares with people: we found no study that gives, in RQD points, how much two geologists differ on the same drill core.
[Pells et al. (2017)](https://doi.org/10.1139/cgj-2016-0012) had professionals assess RQD on the same rock and found differences large enough to change RMR and Q ratings, so a single geologist's log is itself an uncertain reference.
We do not claim CoreSight is within human variability. The error is why a geologist reviews every value before it is used.

What the numbers rest on:
- 34 runs from the [Mining Core Sampling Dataset](https://www.kaggle.com/datasets/imoore/mining-core-sampling-dataset) (Kaggle, CC BY-NC-SA 4.0). The reference is the RQD and recovery the mine geologist wrote on each box lid. These photos and reference values are not in the repo or the demo (non-commercial license); only our errors are published, and the Bland-Altman plot of these runs stays private because its x axis would reveal the reference.
- Onkalo (Commons, CC BY-SA 4.0) and Nevada U12G (U.S. DOE, public domain), labelled by us.
- The `+marks` variant reads marks the geologist already made, so it is not the headline.

Time and cost per tray (5 rows, 2 runs): about 40 s and under US$0.05 with the hosted models (SAM 3.1 at US$2.50 per 1,000 images, Muse Spark Open at US$0.0125 per run), against at least an hour of a geologist by hand. Sources and the breakdown in [`docs/IMPACT.md`](docs/IMPACT.md).

Files: [`outputs/eval/report.md`](outputs/eval/report.md) (every table, per site and method, Deere confusion matrix, dry against wet per run), [`outputs/eval/runs.csv`](outputs/eval/runs.csv) (error per run and method) and [`outputs/eval/bland_altman_public.svg`](outputs/eval/bland_altman_public.svg). Statistics in [`evaluation.py`](src/coresight/evaluation.py), with tests. Reproduce with `python scripts/eval_logs.py` once the Kaggle set is in `data/raw/`.

Descriptions: the same 14 public crops (Onkalo, Potter Mine and Warren County, all from Commons) described by Muse Spark (API), Muse Spark Open on Baseten and Muse Glimmer on our own machine with llama.cpp, all 14/14 valid against the same Pydantic contract. Side by side with time and cost in [`outputs/describe/compare.md`](outputs/describe/compare.md); raw outputs in `outputs/describe/<backend>/`.

## Open weights and provenance

Muse Glimmer runs on our laptop from Meta's official GGUF files; our SHA-256 of both files matches the hashes Hugging Face publishes for [`meta-models/Muse-Glimmer-30B-GGUF`](https://huggingface.co/meta-models/Muse-Glimmer-30B-GGUF). Muse Spark Open runs on Baseten.
Weights, licenses, llama.cpp build, hardware, exact command, token counts and the hash of every published answer: [`docs/PROVENANCE.md`](docs/PROVENANCE.md) and [`outputs/describe/provenance.json`](outputs/describe/provenance.json).
`scripts/offline_glimmer.py` refuses to run unless the network is off, then describes a public photo with Glimmer.

## Why it matters

Mexico is the world's largest silver producer (20.4% in 2025) and Zacatecas makes 41.8% of Mexico's silver ([Camimex 2026](https://www.camimex.org.mx/application/files/5717/8665/5408/InfoCamimex2026.pdf)).
A geologist logs at most about 5 m of mineralised core per hour ([Marjoribanks](http://rogermarjoribanks.info/diamond-drill-core-log-sheets/)), and geotechnical fields add 10 to 20% ([SRK](https://cdn-web-content.srk.com/upload/user/image/MDiGiovinazzo_GeotechnicalDataCollection_May202120210429005204340.pdf)).
Every number, its source and what we could not find: [`docs/IMPACT.md`](docs/IMPACT.md).

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
