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
  CORESIGHT_MAX_HANDOFFS_PER_HOUR, CORESIGHT_MAX_SAM_POINTS_PER_HOUR: caps for
  the public demo, so a stranger cannot spend the API credits.

A tap on the photo (POST /api/boxes/{id}/runs/{i}/sam-point) sends the
geologist's points to SAM 3.1 for that row and makes the piece it cuts one
piece of the run (review.sam_point_mask and review.sam_piece).

Approving a box starts the area agents in the background (coresight.agents);
the page polls the box and shows the decision log and the drafts. A draft is
approved one by one and is never sent.

GET /api/holes/{hole_id} joins the approved boxes of one drill hole by depth
(coresight.hole, numbers from geometry.log_hole): the hole view and its 3D.
- CORESIGHT_OPS_TOKEN: opens GET /api/ops/usage and the /ops page (the credit
  watch: calls, cache hits, tokens and 429s per model, what is left of each cap).
  Unset, both answer 404.
- CORESIGHT_SESSION_SECRET: signs the visitor cookie. Unset, a random one is made
  at start, so a restart only forgets who owned which box.

Every box belongs to the browser that made it (a signed, HttpOnly cookie): an
upload, a sample copy from "Try a sample box", the tour's refused screenshot.
Only that browser lists it, opens it or its images, corrects or approves it;
anybody else gets 404, so a stranger cannot even tell it exists. The home page,
the tour and the public hole use pinned boxes: read-only samples nobody can
change (403), picked once from the samples approved before visitors had owners
(pin_legacy_samples) or by us with POST /api/ops/pin/{id}.
- META_API_KEY in .env, read by meta_client.

The samples are public photos only (Onkalo, CC BY-SA 4.0, and Nevada Test Site,
public domain, both from Wikimedia Commons);
the Kaggle set (NC) is never served here.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import os
import secrets
import threading
import time
import uuid
from collections import Counter, deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import cv2
from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from coresight import agents, hole, review
from coresight.describe import EXAMPLES_KEY
from coresight.labeling import PieceSheet, sheet_markers
from coresight.meta_client import DEFAULT_CACHE_DIR, UsageLog, usage_summary
from coresight.pipeline import export_csv
from coresight.review import Analysis, ReviewError, ReviewStore
from coresight.schemas import (
    BoxLabel,
    BoxReview,
    BreakKind,
    DescriptionField,
    GateResult,
    Handoffs,
    HoleView,
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
    first_starts_in_box: bool = True  # False: the first run started in the previous box
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
            name="nevada-u12g-box3",
            title="Nevada Test Site U12G-GF-GT#2, box 3 (19.0-26.3 ft)",
            photo="data/raw/commons_nts_u12g_2.jpg",
            label="data/labels/U12G-GF-GT2_box03.json",
            sheet="data/labels/pieces/U12G-GF-GT2_box03.json",
            tray_index=0,
            box_length_cm=68.0,  # from the depths on the wax-sealed samples
            n_rows=4,
            first_starts_in_box=False,  # run 4 started in box 2 (not public)
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
            title="Onkalo ONK-DTPH5.1, box 6 (22.60-27.20 m)",
            photo="data/raw/commons_onkalo_1.jpg",
            label="data/labels/ONK-DTPH5.1_box06.json",
            sheet="data/labels/pieces/ONK-DTPH5.1_box06.json",
            tray_index=1,
            credit="Photo: Kallerna, Wikimedia Commons, CC BY-SA 4.0",
        ),
    ]
}


SHOWCASE = "nevada-u12g-box3"  # the dramatic sample: poor rock, wax, cards (home and tour)
NOT_A_BOX = ROOT / "data" / "demo" / "not_a_core_box.jpg"  # ours: the icon sheet of the page
VISITOR_COOKIE = "cs_visitor"
VISITOR_DAYS = 30
NO_BOX = "This box does not exist (or was removed)."
READ_ONLY = ("This sample is read-only: everybody sees it. Use Try a sample box for your own"
             " copy to correct and approve.")  # fmt: skip


def sign_visitor(secret: bytes, visitor: str) -> str:
    return f"{visitor}.{hmac.new(secret, visitor.encode(), hashlib.sha256).hexdigest()[:32]}"


def read_visitor(secret: bytes, cookie: str | None) -> str | None:
    """The visitor id in a cookie we signed, or None (missing, forged, or an old secret)."""
    visitor = (cookie or "").partition(".")[0]
    if not visitor.isalnum() or not hmac.compare_digest(sign_visitor(secret, visitor), cookie):
        return None
    return visitor


def pin_legacy_samples(store: ReviewStore) -> list[str]:
    """Pin, once, what the home page, the tour and the holes showed before boxes had owners.

    Only sample boxes nobody owns: the newest showcase box with pieces, the newest
    approved one whose agents finished (one with a hole finding first) and, per hole,
    the approved box of each number that the hole log used. Uploads are never pinned.
    """
    boxes = store.all()
    if any(b.pinned for b in boxes):
        return []
    samples = [b for b in boxes
               if b.owner is None and b.source != "upload" and b.status != "failed"]  # fmt: skip
    title = SAMPLES[SHOWCASE].title
    chosen = {}
    shown = [b for b in samples if b.source.startswith(title) and b.runs]
    if shown:
        chosen[shown[0].id] = shown[0]
    finished = [b for b in samples if b.status == "approved" and b.handoffs
                and b.handoffs.status == "done"]  # fmt: skip
    finished.sort(key=lambda b: bool(b.handoffs.hole and b.handoffs.hole.finding), reverse=True)
    agents_box = finished[0] if finished else None
    for hole_id in sorted({b.hole_id for b in samples}):
        for b in hole.logged_boxes(samples, hole_id):
            if not (agents_box and b.hole_id == agents_box.hole_id
                    and b.box_number == agents_box.box_number):  # fmt: skip
                chosen[b.id] = b
    if agents_box:
        chosen[agents_box.id] = agents_box
    for b in chosen.values():
        b.pinned = True
        store.save(b)
    return list(chosen)


class Job(BaseModel):
    """What the background analysis needs (photo bytes are passed alongside)."""

    box_length_cm: float = Field(gt=0, le=300)
    runs: list[Interval] = Field(min_length=1, max_length=30)
    first_starts_in_box: bool
    tray_index: int = Field(ge=0, le=3)
    n_rows: int = Field(5, ge=2, le=8)
    sample: str | None = None  # use the sample's hand-measured run markers
    context: dict = Field(default_factory=dict)


class DraftApproval(BaseModel):
    """A person approving a draft; override only for one that failed verification 3 times."""

    override: bool = False


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


def meta_sam_client():
    """SAM 3.1 through meta_client, for the taps on the photo."""
    from coresight.meta_client import MetaClient

    try:
        return MetaClient()
    except RuntimeError as exc:
        raise ReviewError("The server has no Meta Model API key configured.") from exc


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

    def gate(self, result: GateResult) -> None:
        self.box.gate = result
        self.store.save(self.box)


class RateLimit:
    """At most ``limit`` events in the last hour, shared by all visitors."""

    def __init__(self, limit: int, window_s: float = 3600) -> None:
        self.limit, self.window_s = limit, window_s
        self.events, self._lock = deque(), threading.Lock()

    def _drop_old(self, now: float) -> None:
        while self.events and now - self.events[0] > self.window_s:
            self.events.popleft()

    def left(self) -> int:
        with self._lock:
            self._drop_old(time.monotonic())
            return self.limit - len(self.events)

    def take(self, what: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._drop_old(now)
            if len(self.events) >= self.limit:
                msg = f"The demo allows {self.limit} {what} per hour. Retry later."
                raise HTTPException(429, msg)
            self.events.append(now)


class VisitorLimit:
    """At most ``limit`` uploads per visitor (client address) in ten minutes.

    The hourly cap protects the credits; this one keeps one visitor who clicks
    "Analyze" many times in a row from using the whole hour for everybody.
    """

    WINDOW_S = 600

    def __init__(self, limit: int) -> None:
        self.limit, self.events, self._lock = limit, {}, threading.Lock()

    def take(self, visitor: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in list(self.events):  # forget visitors gone quiet
                kept = [t for t in self.events[key] if now - t <= self.WINDOW_S]
                if kept:
                    self.events[key] = kept
                else:
                    del self.events[key]
            mine = self.events.setdefault(visitor, [])
            if len(mine) >= self.limit:
                wait = int(self.WINDOW_S - (now - mine[0])) // 60 + 1
                raise HTTPException(
                    429,
                    f"You started {self.limit} analyses in 10 minutes. Wait {wait} min, or open a"
                    " sample box meanwhile (they are already analysed).",
                )
            mine.append(now)


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


class PointIn(BaseModel):
    x: float  # px of the straightened tray (tray.jpg)
    y: float
    positive: bool = True  # False: "this is not the piece"


class SamPointIn(BaseModel):
    points: list[PointIn] = Field(min_length=1, max_length=review.MAX_POINTS)
    refine: bool = False  # the same piece again: replaces the last SAM correction


class SamPointOut(BaseModel):
    box: BoxReview
    changed: bool
    row: int
    start_cm: float
    end_cm: float
    confidence: float | None
    seconds: float
    mask: str  # data URL of the mask over the row, as masks/{row}.png


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
    sam_client: Callable[[], object] = meta_sam_client,
    usage_path: Path = DEFAULT_CACHE_DIR / "usage.jsonl",
) -> FastAPI:
    store = store or ReviewStore(Path(os.getenv("CORESIGHT_DATA_DIR", ROOT / "data" / "reviews")))
    analyses = RateLimit(int(os.getenv("CORESIGHT_MAX_ANALYSES_PER_HOUR", "30")))
    dictations = RateLimit(int(os.getenv("CORESIGHT_MAX_DICTATIONS_PER_HOUR", "120")))
    handoff_runs = RateLimit(int(os.getenv("CORESIGHT_MAX_HANDOFFS_PER_HOUR", "30")))
    sam_points = RateLimit(int(os.getenv("CORESIGHT_MAX_SAM_POINTS_PER_HOUR", "300")))
    sample_runs = RateLimit(int(os.getenv("CORESIGHT_MAX_SAMPLES_PER_HOUR", "200")))
    visitors = VisitorLimit(int(os.getenv("CORESIGHT_MAX_ANALYSES_PER_VISITOR", "5")))
    pool = ThreadPoolExecutor(max_workers=2)
    edit_lock = threading.Lock()
    secret = (os.getenv("CORESIGHT_SESSION_SECRET") or secrets.token_hex(32)).encode()

    for box in store.all():  # a restart interrupts any analysis in flight
        if box.status == "processing":
            box.status, box.error = "failed", "The server restarted during the analysis. Retry."
            store.save(box)
        if box.handoffs and box.handoffs.status == "working":
            box.handoffs.status = "failed"
            box.handoffs.error = "The server restarted while the agents worked. Retry."
            store.save(box)
    pin_legacy_samples(store)

    app = FastAPI(title="CoreSight review API", version="0.1.0")

    @app.middleware("http")
    async def visitor_cookie(request: Request, call_next):
        """Who owns the boxes: a random id per browser, signed so it cannot be made up."""
        visitor = read_visitor(secret, request.cookies.get(VISITOR_COOKIE))
        fresh = visitor is None
        request.state.visitor = visitor or uuid.uuid4().hex
        response = await call_next(request)
        if fresh:
            https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
            response.set_cookie(
                VISITOR_COOKIE, sign_visitor(secret, request.state.visitor),
                max_age=VISITOR_DAYS * 86400, httponly=True, samesite="lax", secure=https,
            )  # fmt: skip
        return response

    def visible(box: BoxReview, visitor: str) -> bool:
        return box.pinned or (box.owner is not None and box.owner == visitor)

    def seen_by(visitor: str) -> list[BoxReview]:
        """The boxes one visitor may see: the pinned samples and their own."""
        return [b for b in store.all() if visible(b, visitor)]

    @app.exception_handler(ReviewError)
    async def review_error(_: Request, exc: ReviewError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RequestValidationError)
    async def bad_field(_: Request, exc: RequestValidationError) -> JSONResponse:
        """'box_number: Input should be greater than or equal to 1', one sentence per field."""
        parts = [f"{e['loc'][-1]}: {e['msg']}" for e in exc.errors()]
        return JSONResponse({"detail": ". ".join(parts) + "."}, status_code=422)

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

    def start(
        photo: bytes,
        job: Job,
        hole_id: str,
        box_number: int,
        source: str,
        visitor: str | None,
        owner: str,
    ) -> BoxReview:
        """``visitor`` None: a sample (cached answers, its own cap). ``owner``: the cookie's id."""
        review.decode_photo(photo)  # a bad photo fails now, not in the background
        if visitor is None:
            sample_runs.take("sample analyses")
        else:
            visitors.take(visitor)
            analyses.take("analyses")
        box = BoxReview(
            id=uuid.uuid4().hex[:12],
            hole_id=hole_id,
            box_number=box_number,
            source=source,
            status="processing",
            created_at=datetime.now(UTC),
            owner=owner,
        )
        store.save(box)
        if background:
            pool.submit(run_job, box.id, photo, job)
        else:
            run_job(box.id, photo, job)
            box = store.get(box.id)
        return box

    def get_box(box_id: str, request: Request | None = None) -> BoxReview:
        """``request``: the box must be pinned or the visitor's own; 404 otherwise, never 403."""
        try:
            box = store.get(box_id)
        except KeyError:
            raise HTTPException(404, NO_BOX) from None
        if request is not None and not visible(box, request.state.visitor):
            raise HTTPException(404, NO_BOX)
        return box

    def own_box(box_id: str, request: Request) -> BoxReview:
        """A box the visitor may change: their own, never a pinned sample."""
        box = get_box(box_id, request)
        if box.pinned:
            raise HTTPException(403, READ_ONLY)
        return box

    def edit(
        box_id: str, change: Callable[[BoxReview], object], request: Request | None = None
    ) -> BoxReview:
        """``request`` None: the server's own jobs (analysis, agents), no owner to check."""
        with edit_lock:
            box = own_box(box_id, request) if request is not None else get_box(box_id)
            change(box)
            store.save(box)
            return box

    @app.get("/api/ops/usage")
    def ops_usage(x_ops_token: Annotated[str | None, Header()] = None) -> dict:
        """The credit watch, for us and not for the judges: CORESIGHT_OPS_TOKEN in the header.

        Without the setting the route does not exist (404), so nobody finds it by trying.
        """
        token = os.getenv("CORESIGHT_OPS_TOKEN")
        if not token:
            raise HTTPException(404, "Not Found")
        if not x_ops_token or not hmac.compare_digest(x_ops_token.encode(), token.encode()):
            raise HTTPException(403, "Wrong token.")
        boxes = store.all()
        caps = {"analyses": analyses, "sample analyses": sample_runs, "dictations": dictations,
                "agent runs": handoff_runs, "SAM taps": sam_points}  # fmt: skip
        return {
            "usage": usage_summary(UsageLog(usage_path).entries()),
            "limits": {k: {"per_hour": v.limit, "left": v.left()} for k, v in caps.items()},
            "boxes": dict(Counter(b.status for b in boxes)),
            "uploads": sum(b.source == "upload" for b in boxes),
            "pinned": [b.id for b in boxes if b.pinned],
        }

    @app.post("/api/ops/pin/{box_id}")
    def ops_pin(
        box_id: str, pinned: bool = True, x_ops_token: Annotated[str | None, Header()] = None
    ) -> dict:
        """Pin a sample box for everybody (home, tour, public hole), or unpin it: us only."""
        token = os.getenv("CORESIGHT_OPS_TOKEN")
        if not token:
            raise HTTPException(404, "Not Found")
        if not x_ops_token or not hmac.compare_digest(x_ops_token.encode(), token.encode()):
            raise HTTPException(403, "Wrong token.")
        box = get_box(box_id)
        if box.source == "upload":
            raise HTTPException(400, "An upload is never pinned: it is a visitor's photo.")

        def change(b: BoxReview) -> None:
            b.pinned = pinned
            if pinned:
                b.owner = None  # nobody's: read-only for everybody

        edit(box.id, change)
        return {"id": box.id, "pinned": pinned}

    @app.get("/ops")
    def ops_page() -> FileResponse:
        return FileResponse(WEB_DIR / "ops.html", headers={"X-Robots-Tag": "noindex"})

    @app.get("/api/showcase")
    def showcase() -> dict:
        """What the home page and the 60-second tour show: real boxes, never made up.

        Only pinned boxes, the same for every visitor whatever they approve:
        box: the newest pinned box of the showcase sample with pieces (any status but failed);
        agents_box: the newest pinned approved box whose agents finished, one with a hole
        finding first; hole_id: its hole. Uploads are never shown to other visitors.
        """
        title = SAMPLES[SHOWCASE].title
        samples = [b for b in store.all()
                   if b.pinned and b.source != "upload" and b.status != "failed"]  # fmt: skip
        mine = [b for b in samples if b.source.startswith(title) and b.runs]
        finished = [b for b in samples if b.status == "approved" and b.handoffs
                    and b.handoffs.status == "done"]  # fmt: skip
        finished.sort(key=lambda b: bool(b.handoffs.hole and b.handoffs.hole.finding), reverse=True)
        agents_box = finished[0] if finished else None
        return {
            "box": mine[0].id if mine else None,
            "agents_box": agents_box.id if agents_box else None,
            "hole_id": agents_box.hole_id if agents_box else None,
        }

    @app.post("/api/tour/not-a-box", status_code=202)
    def tour_not_a_box(request: Request) -> BoxReview:
        """The tour's first step: CoreSight refuses a screenshot, live (calibration, no model)."""
        job = Job(box_length_cm=100, runs=[Interval(from_m=1, to_m=2)], first_starts_in_box=True,
                  tray_index=0)  # fmt: skip
        source = "Tour: a screenshot of CoreSight's own icon sheet, not a core box"
        visitor = request.state.visitor
        return start(NOT_A_BOX.read_bytes(), job, "NOT-A-CORE-BOX", 1, source, None, visitor)

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
    def analyze_sample(name: str, request: Request) -> BoxReview:
        """The visitor's own copy of a sample, from the cache: theirs to correct and approve."""
        s = SAMPLES.get(name)
        if s is None or not (ROOT / s.photo).exists():
            raise HTTPException(404, "Unknown sample.")
        label = BoxLabel.model_validate_json((ROOT / s.label).read_text(encoding="utf-8"))
        job = Job(
            box_length_cm=s.box_length_cm,
            runs=[Interval(from_m=r.from_m, to_m=r.to_m) for r in label.runs],
            first_starts_in_box=s.first_starts_in_box,
            tray_index=s.tray_index,
            n_rows=s.n_rows,
            sample=s.name,
            context={"hole_id": label.hole_id, "box": label.box_number},
        )
        photo = (ROOT / s.photo).read_bytes()
        source, visitor = f"{s.title}. {s.credit}", request.state.visitor
        return start(photo, job, label.hole_id, label.box_number, source, None, visitor)

    @app.post("/api/boxes", status_code=202)
    async def analyze_upload(
        request: Request,
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
        # point F: few-shot, no training; only boxes this visitor may see
        examples = review.fewshot_examples(seen_by(request.state.visitor), hole_id)
        if examples:
            job.context[EXAMPLES_KEY] = examples
        # nginx sets X-Real-IP to the address it saw (X-Forwarded-For can be forged)
        visitor = request.headers.get("x-real-ip") or (request.client and request.client.host)
        visitor = visitor or "unknown"
        return start(data, job, hole_id, box_number, "upload", visitor, request.state.visitor)

    @app.get("/api/boxes")
    def list_boxes(request: Request) -> list[dict]:
        """The visitor's own boxes, never anybody else's (the samples are on the home page)."""
        return [
            {"id": b.id, "hole_id": b.hole_id, "box_number": b.box_number, "status": b.status}
            for b in store.all()
            if b.owner is not None and b.owner == request.state.visitor and not b.pinned
        ]

    @app.get("/api/holes")
    def list_holes(request: Request) -> list[dict]:
        """Holes with at least one approved box: pinned ones and the visitor's own."""
        return hole.hole_summaries(seen_by(request.state.visitor))

    @app.get("/api/holes/{hole_id}")
    def read_hole(hole_id: str, request: Request) -> HoleView:
        """The approved boxes of one hole joined by depth (geometry.log_hole).

        The pinned boxes for everybody; a visitor's own approvals only for them.
        """
        view = hole.hole_view(seen_by(request.state.visitor), hole_id)
        if not view.boxes:
            raise HTTPException(404, "No box of this hole.")
        return view

    @app.get("/api/boxes/{box_id}")
    def read_box(box_id: str, request: Request) -> BoxReview:
        return get_box(box_id, request)

    @app.get("/api/boxes/{box_id}/tray.jpg")
    def tray_image(box_id: str, request: Request) -> FileResponse:
        get_box(box_id, request)
        path = store.tray_path(box_id)
        if not path.exists():
            raise HTTPException(404, "The tray image is not ready.")
        return FileResponse(path, media_type="image/jpeg")

    def box_file(box_id: str, name: str, media_type: str, request: Request) -> FileResponse:
        get_box(box_id, request)
        path = store.file_path(box_id, name)
        if not path.exists():
            raise HTTPException(404, "This image is not ready.")
        return FileResponse(path, media_type=media_type)

    @app.get("/api/boxes/{box_id}/masks/{row}.png")
    def mask_image(box_id: str, row: int, request: Request) -> FileResponse:
        """What SAM 3.1 returned for one row of the tray, drawn as coloured masks."""
        return box_file(box_id, f"masks{row}.png", "image/png", request)

    @app.get("/api/boxes/{box_id}/runs/{i}/crop.jpg")
    def run_image(box_id: str, i: int, request: Request) -> FileResponse:
        """The picture of one run that the describe model saw."""
        return box_file(box_id, f"run{i}.jpg", "image/jpeg", request)

    @app.post("/api/boxes/{box_id}/runs/{i}/breaks/{j}")
    def change_break(box_id: str, i: int, j: int, body: BreakIn, request: Request) -> BoxReview:
        return edit(box_id, lambda b: review.set_break(b, i, j, body.kind), request)

    @app.delete("/api/boxes/{box_id}/runs/{i}/pieces/{j}")
    def delete_piece(box_id: str, i: int, j: int, request: Request) -> BoxReview:
        return edit(box_id, lambda b: review.remove_piece(b, i, j), request)

    @app.post("/api/boxes/{box_id}/runs/{i}/pieces/{j}/split")
    def split_piece(box_id: str, i: int, j: int, body: SplitIn, request: Request) -> BoxReview:
        return edit(box_id, lambda b: review.split_piece(b, i, j, body.at_cm, body.kind), request)

    @app.post("/api/boxes/{box_id}/runs/{i}/sam-point")
    def sam_point(box_id: str, i: int, body: SamPointIn, request: Request) -> SamPointOut:
        """SAM 3.1 cuts the piece under the geologist's points; geometry.py recomputes."""
        box = own_box(box_id, request)
        review.sam_piece_ready(box, i)
        image = cv2.imread(str(store.tray_path(box_id)))
        if image is None or box.tray is None:
            raise ReviewError("The tray image is not ready.")
        sam_points.take("taps on the photo")
        points = [(p.x, p.y, p.positive) for p in body.points]
        cut = review.sam_point_mask(sam_client(), image, box.tray, points)  # 3 to 4 s, unlocked
        changed = []
        box = edit(
            box_id,
            lambda b: changed.append(review.sam_piece(b, i, cut, len(points), body.refine)[1]),
            request,
        )
        return SamPointOut(
            box=box,
            changed=changed[0],
            row=cut.row,
            start_cm=round(cut.start_cm, 2),
            end_cm=round(cut.end_cm, 2),
            confidence=cut.confidence,
            seconds=cut.seconds,
            mask="data:image/png;base64," + base64.b64encode(cut.overlay).decode("ascii"),
        )

    @app.put("/api/boxes/{box_id}/runs/{i}/description")
    def change_description(
        box_id: str, i: int, body: DescriptionIn, request: Request
    ) -> BoxReview:
        return edit(
            box_id,
            lambda b: review.set_description(
                b, i, body.field, body.value, body.source, body.transcript
            ),
            request,
        )

    def run_handoffs(box_id: str) -> None:
        box = store.get(box_id)
        history = [
            b for b in store.all()
            if (b.pinned or b.owner == box.owner) and b.status == "approved"
            and b.hole_id == box.hole_id and b.box_number < box.box_number
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

    def start_handoffs(box_id: str, request: Request) -> BoxReview:
        handoff_runs.take("agent runs")
        box = edit(box_id, lambda b: setattr(b, "handoffs", Handoffs()), request)
        if background:
            pool.submit(run_handoffs, box_id)
            return box
        run_handoffs(box_id)
        return get_box(box_id)

    @app.post("/api/boxes/{box_id}/approve")
    def approve(box_id: str, request: Request) -> BoxReview:
        edit(box_id, review.approve, request)
        return start_handoffs(box_id, request)

    @app.post("/api/boxes/{box_id}/handoffs", status_code=202)
    def retry_handoffs(box_id: str, request: Request) -> BoxReview:
        box = own_box(box_id, request)
        if box.status != "approved":
            raise HTTPException(400, "Approve the box first: the agents only see approved logs.")
        if box.handoffs and box.handoffs.status == "working":
            raise HTTPException(409, "The agents are still working on this box.")
        return start_handoffs(box_id, request)

    @app.post("/api/boxes/{box_id}/drafts/{area}/approve")
    def approve_draft(
        box_id: str,
        area: Literal["lab", "safety", "plant", "finance"],
        request: Request,
        body: DraftApproval | None = None,
    ) -> BoxReview:
        override = bool(body and body.override)

        def change(b: BoxReview) -> None:
            try:
                agents.approve_draft(b, area, override=override)
            except ValueError as exc:
                raise ReviewError(str(exc)) from None

        return edit(box_id, change, request)

    def csv_response(text: str, name: str) -> PlainTextResponse:
        return PlainTextResponse(
            text,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/boxes/{box_id}/log.csv")
    def log_csv(box_id: str, request: Request) -> PlainTextResponse:
        box = get_box(box_id, request)
        if box.status not in ("ready", "approved"):
            raise HTTPException(409, "The box has no log yet.")
        return csv_response(export_csv(box), f"{box.hole_id}_box{box.box_number:02d}.csv")

    @app.get("/api/boxes/{box_id}/corrections.csv")
    def corrections_csv(box_id: str, request: Request) -> PlainTextResponse:
        """Every correction next to the value it replaced, for the evaluation."""
        box = get_box(box_id, request)
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
        request: Request,
        audio: Annotated[UploadFile, File()],
        box_id: Annotated[str | None, Form()] = None,
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
                edit(box_id, count, request)
            except HTTPException:
                pass
        return {"transcript": text, "duration_ms": ms}

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
