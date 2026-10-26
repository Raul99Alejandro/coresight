"""Pydantic contracts.

Every model output is parsed into one of these classes before the rest of the
pipeline is allowed to use it. Hand-made labels use the same contracts.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnomalyType(StrEnum):
    LOW_RECOVERY = "low_recovery"
    INTENSE_FRACTURING = "intense_fracturing"
    VISIBLE_SULFIDES = "visible_sulfides"
    OTHER = "other"


class Anomaly(_Strict):
    type: AnomalyType
    explanation: str = Field(min_length=1)


class GeologyDescription(_Strict):
    """What Muse Spark writes for one interval (day 6)."""

    lithology: str = Field(min_length=1)
    alteration: str
    mineralization: str
    anomalies: list[Anomaly] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


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
    natural_fractures: int = Field(ge=0)


class BoxLabel(_Strict):
    hole_id: str = Field(min_length=1)
    box_number: int = Field(ge=1)
    image: str = Field(min_length=1)
    runs: list[LabelRun] = Field(min_length=1)
