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
| 2. Segmentation: intact pieces and fractures per row; where "stone" finds nothing, Muse Spark boxes the core and SAM cuts it with those boxes | `pipeline.segment`, `segmentation.located_masks`, `meta_client` | SAM 3.1 and Muse Spark grounding (Meta Model API) |
| 3. Geometry: piece lengths, RQD, fracture frequency, recovery | `geometry.py` | Deterministic Python, no LLM |
| 4. Description: lithology, alteration, mineralization, anomaly flags | `pipeline.describe`, `meta_client` | Muse Spark, Pydantic-validated JSON |
| 5. Review: geologist corrects breaks, pieces and descriptions by typing, by voice or by tapping the photo (SAM 3.1 point prompts); numbers are recalculated by the geometry engine; corrections are kept next to the original; CSV export | `api.py`, `review.py`, `web/index.html` | FastAPI, Muse Voice Transcribe, SAM 3.1 |
| 6. Hole view: the approved boxes of one drill hole joined by depth; RQD, TCR, fracture frequency and Deere class by run and by 1 m interval; gaps and overlaps between boxes; weak zones; a 3D of the hole | `hole.py`, `geometry.log_hole`, `web/index.html` | Deterministic Python, three.js |
| 7. Agents: a hole agent reads the trends between boxes and proposes an action; an orchestrator routes each approved box to the lab, safety and geotechnics, the processing plant and finance; each area agent drafts; every step is verified by code and by Muse Spark as a judge; a human approves | `agents.py`, `verify.py`, `hole.hole_trends` | Muse Wonder (orchestrator), Muse Spark with tools and as a judge |

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

Spark localizes, SAM cuts (point B). Instead of the phrase "stone", Muse Spark boxes every core piece and every object that is not core (run blocks, cards) in tiles of each row, and those boxes go to SAM 3.1 as box prompts; what is not core is taken out of the length. Wax-sealed samples count as core: they were taken for testing but are recovered core, as in our labels. `fallback+` uses "stone" and turns to Spark only for a row where "stone" finds nothing.

| Method | Mine geologist, 34 runs: RQD MAE [95% CI] | Our labels, Nevada (3 runs): RQD MAE | Our labels, Onkalo dry (5 runs) |
|---|---|---|---|
| `sam+fill+profile` ("stone") | 11.2 [6.1, 18.9] | 23.6 | 1.1 |
| `spark+sam+fill+profile` (Spark's boxes on every row) | 12.0 [6.7, 19.9] | 1.2 | 1.6 |
| `fallback+sam+fill+profile` (Spark only where "stone" finds nothing) | 11.2 [6.1, 18.9] | 15.9 | 1.1 |

Paired by run, Spark's boxes on every row change the Kaggle RQD error by +0.7 points [-1.1, +2.9]: no gain against the independent reference. On Nevada they fix the photo "stone" cannot read, but we tuned the tiling on that photo and labelled it ourselves, so it is not an independent result. **Decision: `fallback+sam+fill+profile` is the method of the demo**: identical to "stone" where it works (all 34 Kaggle runs), Spark and SAM together where it fails, and one Spark call per tile only for those rows. Full tables in [`outputs/eval/report.md`](outputs/eval/report.md).

Public boxes, labelled by us on the same photo (small, not an independent result):

| Boxes | Runs | RQD MAE | What it shows |
|---|---|---|---|
| Onkalo, dry (2 boxes) | 5 | 1.1 | Sound crystalline rock is easy |
| Onkalo, the same boxes wet | 5 | 12.3 | Wet dark core: SAM splits one intact piece into many (photo below) |
| Nevada U12G (1 box) | 3 | 23.6 (15.9 with `fallback+`, 1.2 with Spark on every row) | Broken core, with run cards and wax-sealed samples in the tray; "stone" finds nothing in row 2 |

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

## Agents

When the geologist approves a box, three kinds of agents run, each with a closed list of read-only tools. None of them can send or change anything.

1. **Hole agent** (Muse Spark). Code first finds the trends along the hole that reach this box (`hole.hole_trends`): an RQD drop from the box above, a weak zone of the hole log, a change of rock at the contact, sulfides that appear or end. Every number comes from `geometry.py`. The agent reads them with its tools and proposes one action from a closed list: ask for oriented core, warn geotechnics before the next run, sample across the contact, or none.
2. **Orchestrator** (Muse Wonder, Muse Spark as plan B). It reads the box, the hole and the hole agent's finding and decides which areas should hear about the box, and why. Its prompt says what each area does and holds no routing rules.
3. **Area agents** (Muse Spark): lab, safety and geotechnics, plant and finance write drafts with their own tools.

How it is verified, in the words of Meta's Agents 102 workshop:

- **Mandatory verification inside the submit step.** Verification is not a tool the agent may call. Every submission (`submit_finding`, `route_box`, `submit_draft`) goes through it before anyone sees the result.
- **Verify at milestones.** The hole agent's finding is checked before the orchestrator reads it. The routing is checked before any area agent writes (`verify.check_routing`): the areas chosen must agree with what code knows about the box. Safety must apply when a drop or a weak zone reaches the box and cannot apply on good rock with no trend; lab must apply when the approved description shows sulfides; finance applies exactly when lab does. Everything the record leaves open is the orchestrator's call. Every draft is checked before a person sees it.
- **Deterministic checks plus LLM as a judge.** First `verify.py`: intervals inside the box, figures equal to `geometry.py`, every number in the text traceable to a tool or a trend, prices from the table. Then, only if those pass, Muse Spark as a judge checks every text claim against the record the geologist approved ("visible sulfides" only if the description shows them), with a Pydantic-validated verdict per claim. The judge never runs on, and so never passes, what `verify.py` rejected.
- **Max three attempts, then escalate to a human.** A failure goes back to the agent with the reasons of both layers. After three attempts the draft reaches the person marked "Needs review" with why; the routing stops and nobody drafts.
- **Final human sign-off.** Even a verified draft waits for the geologist's approval, and approving only marks it in CoreSight: there is no outbound channel. A draft that failed three times can only be approved explicitly, and the log says so.
- **Closed tool list.** Each agent sees only its own read-only tools; any other tool name is refused.
- **The cost of verifying, shown.** The decision log says, in sentences, how many attempts and model turns each step took and how many seconds went to writing and to verifying (code and judge).

Meta's Agents Rule of Two: the agents read model output about the photo and private mine data, and hold no tool that changes state or communicates outside.

## Built with Muse Code

Five pieces were written by Muse Code (1.4.13, and 1.4.14 from Oct 28) against tests we wrote first. We did not edit its code.

- `src/coresight/verify.py`, the deterministic check every area draft must pass before a person can approve it. Spec: `tests/test_verify.py`.
  - Round 1 (session `bbc6432a-3cb8-407d-8572-921d33527e31`): the full verifier from the first 15 tests.
  - Round 2 (session `88fc39bc-b75a-47b0-8d5f-466e68048e0a`): a ruff fix and 5 new tests (budget left after earlier boxes, numbers from the hole history, runs named from one).
  - Round 3 (session `01a17f99-9b2b-7bd3-91e8-c08bf9dd5502`): runs numbered from 1 and failed checks explained in words.
- `src/coresight/gate.py`, the input gate that refuses a photo that is not a core tray before anything is measured (session `01a17f99-8f2a-7be0-9d5a-d4e1efe7b717`). Spec: `tests/test_gate.py`.
- `sam_prompt` and `grid_box_to_pixels` in `src/coresight/meta_client.py`, the builder of SAM 3.1 box and point prompts: our boxes and the geologist's taps become `<|box;...|>` and `<|point;...|>` tokens, with `w` and `h` of the image sent, at most 16 objects and whole pixels inside the image; Muse Spark's 0 to 1000 grid becomes an inclusive pixel box (session `01a17fc6-f402-7be3-981a-3577dbf7c4c5`). Spec: `tests/test_sam_prompts.py`, from the examples of the SAM docs and our smoke test.
- `pieces_at_depth` and `log_hole` in `src/coresight/geometry.py`, the drill hole by depth: boxes joined, gaps and overlaps, runs split between two boxes joined, RQD, TCR and fractures by run and by fixed interval, weak zones. Spec: `tests/test_hole.py`. The first piece with a builder and a reviewer, as Meta's Agents 102 workshop recommends:
  - Builder, round 1 (session `01a183d3-a60a-74c3-b5ab-dd720838a11d`): all 29 tests green.
  - Reviewer (session `01a183db-f694-7060-b8de-67eb8f826b4e`), a second Muse Code session with `--disable-write`: found real errors the tests missed (a natural break exactly on an interval boundary was lost; a box inside another gave a false gap; slivers at the edge lost core; overlapping runs of one box went through). We turned them into 13 new tests; we did not fix them by hand.
  - Builder, round 2 (session `01a183e5-86e3-7391-89d7-257f02ae3408`): all 41 tests green. Fractures and recovered core now add up the same by run and by interval.
  - Second reviewer (session `01a183ee-17c2-7872-965a-26e7a5a56b8d`): four more (rounding overlaps between runs of one box crashed, a gap inside a box got an interval with RQD 0, lost core between rejoined pieces counted as core, a break on a `3 * 0.3` boundary fell one interval low). Four new tests.
  - Builder, round 3 (session `01a183f8-64f7-76f3-9315-8faf5fe87a2d`): all 46 tests green. Traces `hole-1` to `hole-3` and `hole-review-1` and `-2`.
- Every run is headless: `muse exec --contributor-mode off --disable-approval --json`, sandbox on, never `--yolo`. Reviewers also run with `--disable-write`.
- Muse's Windows sandbox could not start PowerShell on this machine, so it could not run the tests itself. We ran pytest and ruff outside it after each round.
- Traces (prompt, every tool step, final answer, token usage) are in [`docs/muse-code/`](docs/muse-code/).
- About `"model": "muse-spark-1.3-contributor"` in `verify-1.json` and `verify-2.json`: that is the model id Muse Code picks by default on this account when no `--model` is given. It is a catalog model, not the contributor mode: `--contributor-mode off` was set on every run and is a separate setting. We checked it with `muse model-profile show` and two one-line runs, one without `--model` (reports `muse-spark-1.3-contributor`) and one with `--model muse-spark-1.3` (reports `muse-spark-1.3`). From the gate on, every run passes `--model muse-spark-1.3`, and the traces say so.

## Status

Before measuring anything, an input gate checks three signals: how clearly calibration found the tray slats, Muse Spark's look at the whole photo (`is_core_tray`, validated with Pydantic) and the SAM 3.1 confidence. A screenshot, a selfie or core without a tray is refused with a clear message instead of getting an RQD.

The models work together. Where SAM 3.1 finds nothing with the phrase "stone", Muse Spark boxes the core pieces of the row and SAM cuts them with those boxes. In the review, the geologist taps a piece on the photo: the tap goes to SAM 3.1 as a point prompt (a second tap marked "Not the piece" is a negative point), the piece is measured on the mask SAM returns, `geometry.py` recomputes the run, and the correction is kept with the source `sam-point` in the history and the CSV. It takes 3 to 4 s per tap; Split by hand stays as the fallback.

The unit is a drill hole, not a photo. Approved boxes of the same hole join into one log by depth (`geometry.log_hole`): RQD, TCR, fracture frequency and Deere class by run and by 1 m interval, gaps and overlaps between boxes flagged, and weak zones (two or more consecutive 1 m intervals below RQD 50) marked. The hole view shows it as a depth column and in 3D. No public hole has a downhole survey, so the 3D uses an example orientation and says so on screen. Demo holes: Onkalo ONK-DTPH5.1 boxes 5 and 6, and Nevada U12G-GF-GT#2 boxes 1 and 3 (box 2 is not public and shows as a gap). A read-only `hole_log` tool gives the agents the hole by depth.

Working end to end: calibration, SAM 3.1 segmentation, geometry, Muse Spark descriptions on three backends, the review page with voice corrections and CSV export. Live demo at https://coresight.analizac.com.
The agents look at the hole, not only the box: approving a box that sits under better rock gives a trend alert from the hole agent, a verified routing and a safety draft verified in two layers (see Agents). Day-by-day plan in `docs/PLAN.md`.

## License

Apache License 2.0, see [`LICENSE`](LICENSE). Public images keep their own licenses, listed in `data/labels/SOURCES.md`.
