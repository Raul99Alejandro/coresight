"""Anomalies that come from the numbers, not from a model.

``low_recovery`` and ``intense_fracturing`` are read off the run's TCR and
fracture frequency, both computed by geometry.py. This module only compares
them with thresholds; a vision model is never allowed to report these two
(see schemas.ModelAnomaly). ``visible_sulfides`` is the model's call.

Only runs seen whole in the photo are judged: the TCR of a run that goes on
in another box says nothing about its recovery.
"""

from __future__ import annotations

from coresight.schemas import (
    Anomaly,
    AnomalySource,
    AnomalyType,
    GeologyDescription,
    IntervalResult,
)

LOW_RECOVERY_TCR_PCT = 85.0  # below this the run lost core worth checking
INTENSE_FRACTURING_PER_M = 10.0  # above this the rock is broken, whatever the RQD

RULE_TYPES = {AnomalyType.LOW_RECOVERY, AnomalyType.INTENSE_FRACTURING}


def rule_anomalies(
    result: IntervalResult,
    low_recovery_tcr_pct: float = LOW_RECOVERY_TCR_PCT,
    intense_fracturing_per_m: float = INTENSE_FRACTURING_PER_M,
) -> list[Anomaly]:
    if not result.complete:
        return []
    out = []
    if result.tcr_pct < low_recovery_tcr_pct:
        out.append(
            Anomaly(
                type=AnomalyType.LOW_RECOVERY,
                explanation=f"TCR {result.tcr_pct:.0f}% is below {low_recovery_tcr_pct:.0f}%.",
                source=AnomalySource.RULE,
            )
        )
    if result.fracture_frequency_per_m > intense_fracturing_per_m:
        out.append(
            Anomaly(
                type=AnomalyType.INTENSE_FRACTURING,
                explanation=(
                    f"{result.fracture_frequency_per_m:.1f} natural fractures per metre,"
                    f" above {intense_fracturing_per_m:.0f}."
                ),
                source=AnomalySource.RULE,
            )
        )
    return out


def with_rule_anomalies(
    description: GeologyDescription, result: IntervalResult
) -> GeologyDescription:
    """The model's description with the rule anomalies of its run added.

    Rule-type anomalies already in the description are replaced, so a model
    can never add them and applying this twice changes nothing.
    """
    kept = [a for a in description.anomalies if a.type not in RULE_TYPES]
    return description.model_copy(update={"anomalies": rule_anomalies(result) + kept})
