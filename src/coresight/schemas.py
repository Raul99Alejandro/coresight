"""Pydantic contracts.

Every model output is parsed into one of these classes before the rest of the
pipeline is allowed to use it. Hand-made labels use the same contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnomalyType(StrEnum):
    LOW_RECOVERY = "low_recovery"
    INTENSE_FRACTURING = "intense_fracturing"
    VISIBLE_SULFIDES = "visible_sulfides"
    OTHER = "other"


class AnomalySource(StrEnum):
    RULE = "rule"  # from geometry.py numbers (coresight.anomalies)
    MODEL = "model"  # seen by the vision model


class Anomaly(_Strict):
    type: AnomalyType
    explanation: str = Field(min_length=1)
    source: AnomalySource = AnomalySource.MODEL


class GeologyDescription(_Strict):
    """Description of one interval: what the model saw plus the rule-based anomalies."""

    lithology: str = Field(min_length=1)
    alteration: str
    mineralization: str
    anomalies: list[Anomaly] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ModelAnomaly(_Strict):
    # low_recovery and intense_fracturing are measured, never guessed by a model
    type: Literal["visible_sulfides", "other"]
    explanation: str = Field(min_length=1)


class ModelDescription(_Strict):
    """What a describe backend (Muse Spark or Glimmer) must return, as JSON schema."""

    lithology: str = Field(min_length=1)
    alteration: str
    mineralization: str
    anomalies: list[ModelAnomaly] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    def to_geology(self) -> GeologyDescription:
        return GeologyDescription(
            lithology=self.lithology,
            alteration=self.alteration,
            mineralization=self.mineralization,
            anomalies=[
                Anomaly(type=a.type, explanation=a.explanation, source=AnomalySource.MODEL)
                for a in self.anomalies
            ],
            confidence=self.confidence,
        )


class Interval(_Strict):
    from_m: float = Field(ge=0)
    to_m: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> Interval:
        if self.to_m <= self.from_m:
            raise ValueError("to_m must be greater than from_m")
        return self


class LabelRun(Interval):
    """One manually logged run (see data/labels/README.md)."""

    rqd_pct: float = Field(ge=0, le=100)
    tcr_pct: float = Field(ge=0, le=100)
    # None: the source did not log fractures (e.g. RQD and CR read from a box lid).
    natural_fractures: int | None = Field(default=None, ge=0)


class IntervalResult(Interval):
    """What the pipeline reports for one run, every number from geometry.py."""

    rqd_pct: float = Field(ge=0, le=100)
    tcr_pct: float = Field(ge=0, le=100)
    natural_fractures: int = Field(ge=0)
    fracture_frequency_per_m: float = Field(ge=0)
    uncertain_breaks: int = Field(ge=0)  # counted as natural, flagged for the geologist
    mechanical_breaks: int = Field(ge=0)  # rejoined: the core was intact in situ
    rock_quality: Literal["very poor", "poor", "fair", "good", "excellent"]
    complete: bool  # the whole run is in this photo (else it continues in another box)


class BoxLabel(_Strict):
    hole_id: str = Field(min_length=1)
    box_number: int = Field(ge=1)
    image: str = Field(min_length=1)
    runs: list[LabelRun] = Field(min_length=1)


class IntervalDescription(Interval):
    """One run's description, as pipeline.describe returns it."""

    backend: str = Field(min_length=1)  # model that wrote it, e.g. muse-spark-1.3
    description: GeologyDescription


class Transcript(BaseModel):
    """Muse Voice Transcribe buffered JSON answer (docs: voice/schemas, Transcribe Response)."""

    sessionId: str  # field names as the API sends them
    transcript: str
    audioDurationMs: int = Field(ge=0)
    turns: list[dict] = Field(default_factory=list)


# Input gate: is this photo a core tray CoreSight can measure?

GateSignal = Literal["spark", "calibration", "segmentation"]


class TrayCheck(_Strict):
    """Muse Spark's answer for the whole photo: is it a core tray at all?"""

    is_core_tray: bool
    what_it_shows: str = Field(min_length=1, max_length=120)  # a few words
    confidence: float = Field(ge=0, le=1)


class GateReason(_Strict):
    """One signal that says the photo should not be measured."""

    signal: GateSignal
    value: float  # the confidence that failed
    detail: str = Field(min_length=1)


class GateResult(_Strict):
    """gate.check_input: measure the photo (ok) or refuse it with reasons."""

    ok: bool
    reasons: list[GateReason] = Field(default_factory=list)
    message: str = ""  # what the person reads; empty when ok


# Localization (point B): Muse Spark marks what is core in a row, SAM 3.1 cuts it.

LocatedKind = Literal["core", "run_block", "card", "waxed_sample", "other"]


class LocatedObject(_Strict):
    """One thing Muse Spark found in a row crop, as a box in its 0 to 1000 grid.

    (0, 0) is the top left of the crop and (1000, 1000) its bottom right; the
    model may answer slightly out of range, so a little slack is allowed and
    meta_client.grid_box_to_pixels clamps.
    """

    kind: LocatedKind
    x_min: int = Field(ge=-50, le=1050)
    y_min: int = Field(ge=-50, le=1050)
    x_max: int = Field(ge=-50, le=1050)
    y_max: int = Field(ge=-50, le=1050)


class RowLocation(_Strict):
    """Muse Spark's answer for one row: every core piece and everything that is not core."""

    objects: list[LocatedObject] = Field(max_length=80)


# Review (day 7): what the geologist sees, corrects and approves.

BreakKind = Literal["natural", "uncertain", "possible_mechanical", "mechanical"]
DescriptionField = Literal["lithology", "alteration", "mineralization", "comment"]


class ReviewPiece(_Strict):
    """One piece of a run as laid in the photo: row of the tray and cm from the row start."""

    row: int = Field(ge=0)
    start_cm: float
    end_cm: float
    break_after: BreakKind

    @model_validator(mode="after")
    def _ordered(self) -> ReviewPiece:
        if self.end_cm <= self.start_cm:
            raise ValueError("end_cm must be greater than start_cm")
        return self


class Correction(_Strict):
    """One change by the geologist, with the value it replaced (kept for evaluation)."""

    at: datetime
    target: str  # "break 3", "piece 2" or a description field
    original: str
    corrected: str
    source: Literal["typed", "voice", "sam-point"] = "typed"
    transcript: str | None = None  # what Muse Voice Transcribe heard, before any edit
    # sam-point: the run's pieces before the click, so a refining click can replace it
    pieces_before: list[ReviewPiece] | None = None


class Measure(_Strict):
    """The sums behind a run's RQD and TCR, from geometry.IntervalLog (shown as the working)."""

    run_length_cm: float = Field(gt=0)
    recovered_cm: float = Field(ge=0)
    rqd_cm: float = Field(ge=0)
    intact_lengths_cm: list[float]  # after mechanical breaks are rejoined


class RunReview(Interval):
    pieces: list[ReviewPiece]
    measure: Measure | None = None  # of the current pieces
    machine_log: IntervalResult  # as the pipeline produced it, never changed
    log: IntervalResult  # recomputed by geometry.py after every piece correction
    machine_description: GeologyDescription | None = None
    description: GeologyDescription | None = None
    description_backend: str | None = None
    description_error: str | None = None
    description_seconds: float | None = None
    comment: str = ""
    corrections: list[Correction] = Field(default_factory=list)


class TrayView(_Strict):
    """Straightened tray the overlay is drawn on."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    px_per_cm: float = Field(gt=0)
    rows: list[tuple[float, float]]  # y1, y2 of every row
    markers: list[tuple[int, float]]  # run markers: row, cm from the row start


StageKey = Literal["calibration", "segmentation", "geometry", "description"]


class Stage(_Strict):
    """One step of the analysis, as the page shows it live and in the model ledger."""

    key: StageKey
    name: str  # what ran it, e.g. "SAM 3.1" or "geometry.py"
    actor: Literal["model", "code"]
    status: Literal["waiting", "working", "done", "failed"] = "waiting"
    detail: str = ""
    progress: float = Field(default=0, ge=0, le=1)
    current: int | None = None  # row or run being processed (0-based)
    seconds: float | None = None
    calls: int = Field(default=0, ge=0)  # requests sent to the model
    cached: int = Field(default=0, ge=0)  # answers read from data/cache instead
    cost_usd: float | None = None  # None: not priced (free credits) or not a paid step


class VoiceUsage(_Strict):
    dictations: int = Field(default=0, ge=0)
    audio_ms: int = Field(default=0, ge=0)
    seconds: float = Field(default=0, ge=0)

    @property
    def cost_usd(self) -> float:  # Muse Voice Transcribe: $0.18 per hour of audio (docs)
        return self.audio_ms / 3_600_000 * 0.18


def default_stages() -> list[Stage]:
    return [
        Stage(key="calibration", name="OpenCV", actor="code"),
        Stage(key="segmentation", name="SAM 3.1", actor="model"),
        Stage(key="geometry", name="geometry.py", actor="code"),
        Stage(key="description", name="Muse Spark 1.3", actor="model"),
    ]


AreaKey = Literal["lab", "safety", "plant", "finance"]


class AreaRoute(_Strict):
    """The orchestrator's call for one area of the mine: does this box concern it, and why."""

    area: AreaKey
    applies: bool
    reason: str = Field(min_length=1)
    runs: list[int] = Field(default_factory=list)  # 0-based runs that triggered it


class Routing(_Strict):
    """What the orchestrator (Muse Wonder, plan B Muse Spark) submits for an approved box."""

    routes: list[AreaRoute] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_per_area(self) -> Routing:
        areas = [r.area for r in self.routes]
        if len(set(areas)) != len(areas):
            raise ValueError("one route per area")
        return self


class DraftFigure(_Strict):
    """A number the draft quotes, tied to the run and metric it comes from."""

    # Run number, 1 is the first. ge=0 only so boxes saved before day 10 still load;
    # verify.py refuses a run that does not exist.
    run: int = Field(ge=0, description="Run number in this box; 1 is the first run")
    metric: Literal["rqd_pct", "tcr_pct", "fracture_frequency_per_m", "natural_fractures"]
    value: float


class DraftLine(_Strict):
    """A priced line (finance): a test code from the example table, how many samples."""

    code: str = Field(min_length=1)
    samples: int = Field(ge=1)
    unit_usd: float = Field(ge=0)
    total_usd: float = Field(ge=0)


class Draft(_Strict):
    """What an area agent submits. A draft only: nothing is sent."""

    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    priority: Literal["low", "normal", "high"] = "normal"
    intervals: list[Interval] = Field(default_factory=list)
    figures: list[DraftFigure] = Field(default_factory=list)
    lines: list[DraftLine] = Field(default_factory=list)
    total_usd: float | None = None


class Check(_Strict):
    """One deterministic check of a draft (verify.py)."""

    name: str
    ok: bool
    detail: str = ""


class AgentEvent(_Strict):
    """One line of the decision log shown in the UI."""

    at: datetime
    actor: str  # "orchestrator", an area, "verifier" or "geologist"
    kind: Literal["model", "route", "tool", "draft", "check", "retry", "error", "approve"]
    text: str
    model: str | None = None


class AreaDraft(_Strict):
    area: AreaKey
    model: str
    draft: Draft | None = None
    checks: list[Check] = Field(default_factory=list)
    verified: bool = False
    status: Literal["working", "ready", "rejected", "failed", "approved"] = "working"
    error: str | None = None
    approved_at: datetime | None = None  # approved by a person; still not sent


class Handoffs(_Strict):
    status: Literal["working", "done", "failed"] = "working"
    orchestrator_model: str | None = None
    routing: Routing | None = None
    drafts: list[AreaDraft] = Field(default_factory=list)
    log: list[AgentEvent] = Field(default_factory=list)
    error: str | None = None


class BoxReview(_Strict):
    id: str = Field(min_length=1)
    hole_id: str = Field(min_length=1)
    box_number: int = Field(ge=1)
    source: str  # where the photo came from (sample name and license, or "upload")
    status: Literal["processing", "ready", "failed", "approved"]
    error: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    tray: TrayView | None = None
    runs: list[RunReview] = Field(default_factory=list)
    stages: list[Stage] = Field(default_factory=default_stages)
    mask_rows: list[int] = Field(default_factory=list)  # rows with a SAM mask image
    voice: VoiceUsage = Field(default_factory=VoiceUsage)
    handoffs: Handoffs | None = None  # area agents, after approval (day 8)
    gate: GateResult | None = None  # the input gate's last verdict (day 10)

# --- Drill hole view (point D) ------------------------------------------------

RockQuality = Literal["very poor", "poor", "fair", "good", "excellent"]


class HoleBox(_Strict):
    id: str
    box_number: int = Field(ge=1)
    from_m: float
    to_m: float
    status: Literal["processing", "ready", "failed", "approved"]
    source: str
    in_log: bool  # approved and used in the hole log


class HoleIssue(_Strict):
    kind: Literal["gap", "overlap"]
    from_m: float
    to_m: float
    box_before: int
    box_after: int


class HoleInterval(Interval):
    """One run or fixed interval of the hole, every number from geometry.log_hole."""

    rqd_pct: float = Field(ge=0, le=100)
    tcr_pct: float = Field(ge=0, le=100)
    natural_fractures: int = Field(ge=0)
    fracture_frequency_per_m: float = Field(ge=0)
    uncertain_breaks: int = Field(ge=0)
    rock_quality: RockQuality
    boxes: list[int]  # boxes the core of this interval comes from
    lithology: str | None = None  # of the reviewed run that covers most of it
    anomalies: list[AnomalyType] = Field(default_factory=list)


class HoleZone(Interval):
    rqd_pct: float = Field(ge=0, le=100)
    min_rqd_pct: float = Field(ge=0, le=100)
    intervals: int = Field(ge=1)
    rock_quality: RockQuality


class HoleTrace(_Strict):
    """Collar orientation for the 3D view. Without a survey it is an example and says so."""

    azimuth_deg: float = Field(ge=0, lt=360)
    dip_deg: float = Field(ge=-90, le=90)
    surveyed: bool
    note: str


class HoleView(_Strict):
    hole_id: str = Field(min_length=1)
    step_m: float = Field(gt=0)
    zone_max_rqd: float
    from_m: float | None = None
    to_m: float | None = None
    boxes: list[HoleBox]
    issues: list[HoleIssue] = Field(default_factory=list)
    runs: list[HoleInterval] = Field(default_factory=list)
    intervals: list[HoleInterval] = Field(default_factory=list)
    zones: list[HoleZone] = Field(default_factory=list)
    trace: HoleTrace
