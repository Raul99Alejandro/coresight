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
    source: Literal["typed", "voice"] = "typed"
    transcript: str | None = None  # what Muse Voice Transcribe heard, before any edit


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
