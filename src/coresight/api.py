"""Stage 5, the review API (FastAPI) and the page that uses it.

    .venv\\Scripts\\python -m uvicorn coresight.api:app --reload

A photo is analysed in the background (SAM and Muse Spark take a minute):
POST /api/boxes answers at once with the box id, and the page polls
GET /api/boxes/{id} until the status is ``ready`` or ``failed``. Every
answer is a schemas.BoxReview; every error is ``{"detail": "..."}`` with a
message the geologist can act on.

Settings (environment):
- CORESIGHT_DATA_DIR: where reviewed boxes are kept (default data/reviews).
- CORESIGHT_MAX_ANALYSES_PER_HOUR, CORESIGHT_MAX_DICTATIONS_PER_HOUR,
  CORESIGHT_MAX_HANDOFFS_PER_HOUR: caps for the public demo, so a stranger
  cannot spend the API credits.

Approving a box starts the area agents in the background (coresight.agents);
the page polls the box and shows the decision log and the drafts. A draft is
approved one by one and is never sent.
- META_API_KEY in .env, read by meta_client.

The samples are public photos only (Onkalo, Wikimedia Commons, CC BY-SA 4.0);
the Kaggle set (NC) is never served here.
"""

from __future__ import annotations

import csv
import io
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from coresight import agents, review
from coresight.labeling import PieceSheet, sheet_markers
from coresight.pipeline import export_csv
from coresight.review import Analysis, ReviewError, ReviewStore
from coresight.schemas import (
    BoxLabel,
    BoxReview,
    BreakKind,
    DescriptionField,
    Handoffs,
    Interval,
    Stage,
    TrayView,
)

ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_PHOTO_MB = 20
MAX_AUDIO_MB = 10  # the API takes 32 MB; a dictation is seconds long
# Hints for Muse Voice Transcribe, in both languages: an English term alone
# pulls a Spanish dictation to English ("pirita" came back as "pyrite").
VOICE_KEYWORDS = [
    "RQD", "granite", "gneiss", "pegmatite", "chlorite", "sericite", "pyrite", "chalcopyrite",
    "pyrrhotite", "sphalerite", "galena", "fault gouge", "granito", "gneis", "pegmatita",
    "clorítica", "sericítica", "silicificada", "pirita", "calcopirita", "pirrotita", "esfalerita",
]  # fmt: skip


class Sample(BaseModel):
    name: str
    title: str
    photo: str  # relative to the repo root
    label: str  # BoxLabel: runs of the box
    sheet: str  # hand-measured piece sheet: the run markers (wooden blocks)
    tray_index: int
    box_length_cm: float = 100.0
    n_rows: int = 5
    credit: str


SAMPLES = {
    s.name: s
    for s in [
        Sample(
            name="nevada-u12g",
            title="Nevada Test Site U12G-GF-GT#2, box 1 (0.0-11.2 ft)",
            photo="data/raw/commons_nts_u12g_1.jpg",
            label="data/labels/U12G-GF-GT2_box01.json",
            sheet="data/labels/pieces/U12G-GF-GT2_box01.json",
            tray_index=0,
            box_length_cm=66.0,  # from the depths on the wax-sealed samples
            n_rows=4,
            credit="Photo: U.S. Department of Energy (NNSA), Wikimedia Commons, public domain",
        ),
        Sample(
            name="onkalo-box5",
            title="Onkalo ONK-DTPH5.1, box 5 (17.94-22.60 m)",
            photo="data/raw/commons_onkalo_1.jpg",
            label="data/labels/ONK-DTPH5.1_box05.json",
            sheet="data/labels/pieces/ONK-DTPH5.1_box05.json",
            tray_index=0,
            credit="Photo: Kallerna, Wikimedia Commons, CC BY-SA 4.0",
        ),
        Sample(
            name="onkalo-box6",
            title="Onkalo ONK-DTPH5.1, box 6",
            photo="data/raw/commons_onkalo_1.jpg",
            label="data/labels/ONK-DTPH5.1_box06.json",
            sheet="data/labels/pieces/ONK-DTPH5.1_box06.json",
            tray_index=1,
            credit="Photo: Kallerna, Wikimedia Commons, CC BY-SA 4.0",
        ),
    ]
}


class Job(BaseModel):
    """What the background analysis needs (photo bytes are passed alongside)."""

    box_length_cm: float = Field(gt=0, le=300)
    runs: list[Interval] = Field(min_length=1, max_length=30)
    first_starts_in_box: bool
    tray_index: int = Field(ge=0, le=3)
    n_rows: int = Field(5, ge=2, le=8)
    sample: str | None = None  # use the sample's hand-measured run markers
    context: dict = Field(default_factory=dict)


Analyzer = Callable[[bytes, Job, review.Reporter], Analysis]
Transcriber = Callable[[bytes], tuple[str, int]]
HandoffRunner = Callable[[BoxReview, list[BoxReview], Callable[[Handoffs], None]], object]


def meta_handoffs(box: BoxReview, history: list[BoxReview], save) -> object:
    """The real agents: Muse Wonder and Muse Spark through meta_client, checked by verify.py."""
    from coresight.meta_client import MetaClient
    from coresight.verify import verify

    return agents.draft_handoffs(box, history, MetaClient(), verify, save=save)


def meta_analyzer(photo: bytes, job: Job, report: review.Reporter) -> Analysis:
    """The real pipeline: SAM 3.1 and Muse Spark through meta_client."""
    from coresight.meta_client import MetaClient

    try:
        client = MetaClient()
    except RuntimeError as exc:
        raise ReviewError("The server has no Meta Model API key configured.") from exc
    markers = None
    if job.sample:  # wooden run blocks the detector does not know: use the measured ones
        sheet = PieceSheet.model_validate_json((ROOT / SAMPLES[job.sample].sheet).read_text())

        def markers(tray):
            return sheet_markers(sheet, tray)

    return review.analyze(
        photo,
        job.box_length_cm,
        job.runs,
        job.first_starts_in_box,
        client,
        client,
        tray_index=job.tray_index,
        markers=markers,
        context=job.context,
        report=report,
        n_rows=job.n_rows,
    )


def meta_transcriber(wav: bytes) -> tuple[str, int]:
    from coresight.meta_client import MetaClient

    t = MetaClient().transcribe(wav, keywords=VOICE_KEYWORDS)
    return t.transcript, t.audioDurationMs


class StoreReporter(review.Reporter):
    """Saves every step of an analysis as it happens, so the page can follow it live."""

    def __init__(self, store: ReviewStore, box: BoxReview) -> None:
        self.store, self.box = store, box

    def stage(self, key: str, **fields) -> None:
        if fields.get("seconds") is not None:
            fields["seconds"] = round(fields["seconds"], 2)
        i = next(i for i, s in enumerate(self.box.stages) if s.key == key)
        self.box.stages[i] = Stage.model_validate({**self.box.stages[i].model_dump(), **fields})
        self.store.save(self.box)

    def tray(self, view: TrayView, jpg: bytes) -> None:
        self.store.save_tray(self.box.id, jpg)
        self.box.tray = view
        self.store.save(self.box)

    def masks(self, row: int, png: bytes) -> None:
        self.store.save_file(self.box.id, f"masks{row}.png", png)
        self.box.mask_rows.append(row)
        self.store.save(self.box)

    def crop(self, run: int, jpg: bytes) -> None:
        self.store.save_file(self.box.id, f"run{run}.jpg", jpg)


class RateLimit:
    """At most ``limit`` events in the last hour, shared by all visitors."""

    def __init__(self, limit: int) -> None:
        self.limit, self.events, self._lock = limit, deque(), threading.Lock()

    def take(self, what: str) -> None:
        now = time.monotonic()
        with self._lock:
            while self.events and now - self.events[0] > 3600:
                self.events.popleft()
            if len(self.events) >= self.limit:
                msg = f"The demo allows {self.limit} {what} per hour. Retry later."
                raise HTTPException(429, msg)
            self.events.append(now)


def parse_runs(text: str) -> list[Interval]:
    """'17.94-20.71, 20.71-22.60' (or one run per line) -> runs, in order."""
    out = []
    bad = "Run '{}' is not 'from-to' in metres, e.g. 17.94-20.71."
    for part in text.replace("\n", ",").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition("-")
        try:
            run = Interval(from_m=float(lo), to_m=float(hi))
        except (ValueError, ValidationError) as exc:
            raise ReviewError(bad.format(part)) from exc
        if not sep:
            raise ReviewError(bad.format(part))
        if out and abs(run.from_m - out[-1].to_m) > 1e-6:
            raise ReviewError(f"Run {part} does not start where the previous one ends.")
        out.append(run)
    if not out:
        raise ReviewError("Add the runs of the box, e.g. 17.94-20.71, 20.71-22.60.")
    return out


class BreakIn(BaseModel):
    kind: BreakKind


class SplitIn(BaseModel):
    at_cm: float  # cm from the start of the piece's row
    kind: BreakKind = "natural"


class DescriptionIn(BaseModel):
    field: DescriptionField
    value: str = Field(max_length=2000)
    source: Literal["typed", "voice"] = "typed"
    transcript: str | None = Field(default=None, max_length=4000)


def create_app(
    store: ReviewStore | None = None,
    analyzer: Analyzer = meta_analyzer,
    transcriber: Transcriber = meta_transcriber,
    handoff_runner: HandoffRunner = meta_handoffs,
    background: bool = True,
) -> FastAPI:
    store = store or ReviewStore(Path(os.getenv("CORESIGHT_DATA_DIR", ROOT / "data" / "reviews")))
    analyses = RateLimit(int(os.getenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "30")))
    dictations = RateLimit(int(os.getenv("CORESIGHT_MAX_DICTATIONS_PER_HOUR", "120")))
    handoff_runs = RateLimit(int(os.getenv("CORESIGHT_MAX_HANDOFFS_PER_HOUR", "30")))
    pool = ThreadPoolExecutor(max_workers=2)
    edit_lock = threading.Lock()

    for box in store.all():  # a restart interrupts any analysis in flight
        if box.status == "processing":
            box.status, box.error = "failed", "The server restarted during the analysis. Retry."
            store.save(box)
        if box.handoffs and box.handoffs.status == "working":
            box.handoffs.status = "failed"
            box.handoffs.error = "The server restarted while the agents worked. Retry."
            store.save(box)

    app = FastAPI(title="CoreSight review API", version="0.1.0")

    @app.exception_handler(ReviewError)
    async def review_error(_: Request, exc: ReviewError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def run_job(box_id: str, photo: bytes, job: Job) -> None:
        box = store.get(box_id)
        try:
            result = analyzer(photo, job, StoreReporter(store, box))
            store.save_tray(box_id, result.tray_jpg)
            box.tray, box.runs, box.status = result.tray, result.runs, "ready"
        except ReviewError as exc:
            box.status, box.error = "failed", str(exc)
        except Exception as exc:  # the API or the pipeline broke: say so, keep the box
            box.status = "failed"
            box.error = f"The analysis failed ({type(exc).__name__}: {str(exc)[:200]}). Retry."
        store.save(box)

    def start(photo: bytes, job: Job, hole_id: str, box_number: int, source: str) -> BoxReview:
        review.decode_photo(photo)  # a bad photo fails now, not in the background
        analyses.take("analyses")
        box = BoxReview(
            id=uuid.uuid4().hex[:12],
            hole_id=hole_id,
            box_number=box_number,
            source=source,
            status="processing",
            created_at=datetime.now(UTC),
        )
        store.save(box)
        if background:
            pool.submit(run_job, box.id, photo, job)
        else:
            run_job(box.id, photo, job)
            box = store.get(box.id)
        return box

    def get_box(box_id: str) -> BoxReview:
        try:
            return store.get(box_id)
        except KeyError:
            raise HTTPException(404, "This box does not exist (or was removed).") from None

    def edit(box_id: str, change: Callable[[BoxReview], object]) -> BoxReview:
        with edit_lock:
            box = get_box(box_id)
            change(box)
            store.save(box)
            return box

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/api/samples")
    def samples() -> list[dict]:
        return [
            {"name": s.name, "title": s.title, "credit": s.credit}
            for s in SAMPLES.values()
            if (ROOT / s.photo).exists()
        ]

    @app.post("/api/samples/{name}", status_code=202)
    def analyze_sample(name: str) -> BoxReview:
        s = SAMPLES.get(name)
        if s is None or not (ROOT / s.photo).exists():
            raise HTTPException(404, "Unknown sample.")
        label = BoxLabel.model_validate_json((ROOT / s.label).read_text(encoding="utf-8"))
        job = Job(
            box_length_cm=s.box_length_cm,
            runs=[Interval(from_m=r.from_m, to_m=r.to_m) for r in label.runs],
            first_starts_in_box=True,
            tray_index=s.tray_index,
            n_rows=s.n_rows,
            sample=s.name,
            context={"hole_id": label.hole_id, "box": label.box_number},
        )
        photo = (ROOT / s.photo).read_bytes()
        return start(photo, job, label.hole_id, label.box_number, f"{s.title}. {s.credit}")

    @app.post("/api/boxes", status_code=202)
    async def analyze_upload(
        photo: Annotated[UploadFile, File()],
        hole_id: str = Form(..., min_length=1, max_length=60),
        box_number: int = Form(..., ge=1),
        runs: str = Form(...),
        box_length_cm: float = Form(100.0, gt=0, le=300),
        first_starts_in_box: bool = Form(True),
        tray: int = Form(1, ge=1, le=4),
        n_rows: int = Form(5, ge=2, le=8),
    ) -> BoxReview:
        data = await photo.read(MAX_PHOTO_MB * 2**20 + 1)
        if len(data) > MAX_PHOTO_MB * 2**20:
            raise ReviewError(f"The photo is larger than {MAX_PHOTO_MB} MB.")
        job = Job(
            box_length_cm=box_length_cm,
            runs=parse_runs(runs),
            first_starts_in_box=first_starts_in_box,
            tray_index=tray - 1,
            n_rows=n_rows,
            context={"hole_id": hole_id, "box": box_number},
        )
        return start(data, job, hole_id, box_number, "upload")

    @app.get("/api/boxes")
    def list_boxes() -> list[dict]:
        return [
            {"id": b.id, "hole_id": b.hole_id, "box_number": b.box_number, "status": b.status}
            for b in store.all()
        ]

    @app.get("/api/boxes/{box_id}")
    def read_box(box_id: str) -> BoxReview:
        return get_box(box_id)

    @app.get("/api/boxes/{box_id}/tray.jpg")
    def tray_image(box_id: str) -> FileResponse:
        get_box(box_id)
        path = store.tray_path(box_id)
        if not path.exists():
            raise HTTPException(404, "The tray image is not ready.")
        return FileResponse(path, media_type="image/jpeg")

    def box_file(box_id: str, name: str, media_type: str) -> FileResponse:
        get_box(box_id)
        path = store.file_path(box_id, name)
        if not path.exists():
            raise HTTPException(404, "This image is not ready.")
        return FileResponse(path, media_type=media_type)

    @app.get("/api/boxes/{box_id}/masks/{row}.png")
    def mask_image(box_id: str, row: int) -> FileResponse:
        """What SAM 3.1 returned for one row of the tray, drawn as coloured masks."""
        return box_file(box_id, f"masks{row}.png", "image/png")

    @app.get("/api/boxes/{box_id}/runs/{i}/crop.jpg")
    def run_image(box_id: str, i: int) -> FileResponse:
        """The picture of one run that the describe model saw."""
        return box_file(box_id, f"run{i}.jpg", "image/jpeg")

    @app.post("/api/boxes/{box_id}/runs/{i}/breaks/{j}")
    def change_break(box_id: str, i: int, j: int, body: BreakIn) -> BoxReview:
        return edit(box_id, lambda b: review.set_break(b, i, j, body.kind))

    @app.delete("/api/boxes/{box_id}/runs/{i}/pieces/{j}")
    def delete_piece(box_id: str, i: int, j: int) -> BoxReview:
        return edit(box_id, lambda b: review.remove_piece(b, i, j))

    @app.post("/api/boxes/{box_id}/runs/{i}/pieces/{j}/split")
    def split_piece(box_id: str, i: int, j: int, body: SplitIn) -> BoxReview:
        return edit(box_id, lambda b: review.split_piece(b, i, j, body.at_cm, body.kind))

    @app.put("/api/boxes/{box_id}/runs/{i}/description")
    def change_description(box_id: str, i: int, body: DescriptionIn) -> BoxReview:
        return edit(
            box_id,
            lambda b: review.set_description(
                b, i, body.field, body.value, body.source, body.transcript
            ),
        )

    def run_handoffs(box_id: str) -> None:
        box = store.get(box_id)
        history = [
            b for b in store.all()
            if b.status == "approved" and b.hole_id == box.hole_id and b.box_number < box.box_number
        ]  # fmt: skip

        def save(handoffs: Handoffs) -> None:
            with edit_lock:
                current = store.get(box_id)
                current.handoffs = handoffs.model_copy(deep=True)
                store.save(current)

        try:
            handoff_runner(box, history, save)
        except Exception as exc:  # never leave the page waiting on a crashed job
            error = f"{type(exc).__name__}: {str(exc)[:200]}"

            def fail(b: BoxReview) -> None:
                b.handoffs = b.handoffs or Handoffs()
                b.handoffs.status, b.handoffs.error = "failed", error

            edit(box_id, fail)

    def start_handoffs(box_id: str) -> BoxReview:
        handoff_runs.take("agent runs")
        box = edit(box_id, lambda b: setattr(b, "handoffs", Handoffs()))
        if background:
            pool.submit(run_handoffs, box_id)
            return box
        run_handoffs(box_id)
        return get_box(box_id)

    @app.post("/api/boxes/{box_id}/approve")
    def approve(box_id: str) -> BoxReview:
        edit(box_id, review.approve)
        return start_handoffs(box_id)

    @app.post("/api/boxes/{box_id}/handoffs", status_code=202)
    def retry_handoffs(box_id: str) -> BoxReview:
        box = get_box(box_id)
        if box.status != "approved":
            raise HTTPException(400, "Approve the box first: the agents only see approved logs.")
        if box.handoffs and box.handoffs.status == "working":
            raise HTTPException(409, "The agents are still working on this box.")
        return start_handoffs(box_id)

    @app.post("/api/boxes/{box_id}/drafts/{area}/approve")
    def approve_draft(box_id: str, area: Literal["lab", "safety", "plant", "finance"]) -> BoxReview:
        def change(b: BoxReview) -> None:
            try:
                agents.approve_draft(b, area)
            except ValueError as exc:
                raise ReviewError(str(exc)) from None

        return edit(box_id, change)

    def csv_response(text: str, name: str) -> PlainTextResponse:
        return PlainTextResponse(
            text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/boxes/{box_id}/log.csv")
    def log_csv(box_id: str) -> PlainTextResponse:
        box = get_box(box_id)
        if box.status not in ("ready", "approved"):
            raise HTTPException(409, "The box has no log yet.")
        return csv_response(export_csv(box), f"{box.hole_id}_box{box.box_number:02d}.csv")

    @app.get("/api/boxes/{box_id}/corrections.csv")
    def corrections_csv(box_id: str) -> PlainTextResponse:
        """Every correction next to the value it replaced, for the evaluation."""
        box = get_box(box_id)
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["hole_id", "box", "from_m", "to_m", "at", "target", "original",
                    "corrected", "source", "transcript"])  # fmt: skip
        for run in box.runs:
            for c in run.corrections:
                w.writerow(
                    [box.hole_id, box.box_number, run.from_m, run.to_m, c.at.isoformat(),
                     c.target, c.original, c.corrected, c.source, c.transcript or ""]
                )  # fmt: skip
        name = f"{box.hole_id}_box{box.box_number:02d}_corrections.csv"
        return csv_response(out.getvalue(), name)

    @app.post("/api/transcribe")
    async def transcribe(
        audio: Annotated[UploadFile, File()], box_id: Annotated[str | None, Form()] = None
    ) -> dict:
        wav = await audio.read(MAX_AUDIO_MB * 2**20 + 1)
        if len(wav) > MAX_AUDIO_MB * 2**20:
            raise ReviewError("The recording is too long. Keep a dictation under a minute.")
        if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
            raise ReviewError("The recording is not a WAV file.")
        dictations.take("dictations")
        started = time.monotonic()
        try:
            text, ms = transcriber(wav)
        except Exception as exc:
            raise HTTPException(
                502, "Muse Voice Transcribe did not answer. Type the correction instead."
            ) from exc
        seconds = time.monotonic() - started
        if box_id:  # counted in the box's model ledger

            def count(b: BoxReview) -> None:
                v = b.voice
                b.voice = v.model_copy(
                    update={"dictations": v.dictations + 1, "audio_ms": v.audio_ms + ms,
                            "seconds": round(v.seconds + seconds, 2)}
                )  # fmt: skip

            try:
                edit(box_id, count)
            except HTTPException:
                pass
        return {"transcript": text, "duration_ms": ms}

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
