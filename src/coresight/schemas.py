"""Pydantic contracts.

Every model output is parsed into one of these classes before the rest of the
pipeline is allowed to use it. Hand-made labels use the same contracts.
"""

from __future__ import annotations

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
