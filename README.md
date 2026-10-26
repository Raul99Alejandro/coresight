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
| 5. Hand-offs: assay request for the lab, ground-condition alert for safety | `pipeline.draft_handoffs` | Agent drafts, human approval required |
| 6. Review UI: geologist corrects intervals, exports CSV | FastAPI app | FastAPI |

## Quickstart

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env             # add your Meta Model API key
pytest
```

## Evaluation

*To be filled on day 9: automatic RQD vs manually logged boxes (MAE), dataset description and failure cases.*

## Built before the hackathon

The hackathon kicked off on Oct 26, 2026 at 12:00 PM ET. These four commits were made on Oct 25, before kickoff. Everything after commit `013503a` was built during the hackathon.

| Commit | What existed before kickoff |
|---|---|
| `1d32fde` | Project scaffold: `pyproject.toml`, Pydantic contracts (`schemas.py`), the deterministic geometry engine (`geometry.py`: RQD, TCR, fracture frequency, mechanical break merging) with its tests, pipeline stubs (`pipeline.py`), CI workflow, day-by-day plan (`docs/PLAN.md`) |
| `fb53c33` | CI switched to manual runs |
| `3a7c613` | Survey of public core photo sources and their licenses (`data/labels/SOURCES.md`) |
| `013503a` | Script that downloads the public photos (`scripts/fetch_public_images.py`); `meta_client.py` written from the public Meta Model API docs (not yet run against the API); day 1 smoke test script (`scripts/smoke_day1.py`); SAM response parser tests |

Not built before kickoff: calibration, SAM segmentation of rows into pieces, wiring the geometry engine to real photos, Muse Spark descriptions and anomaly flags, the review UI and CSV export, the lab and safety hand-offs, the evaluation, and the demo.

## Status

Early scaffold. The geometry engine is implemented and tested; the model stages are being built day by day (see `docs/PLAN.md`).
