"""Deterministic check of every area draft before a person sees it."""

from __future__ import annotations

import math
import re

from coresight.agents import Prices, Toolbox
from coresight.schemas import AreaKey, BoxReview, Check, Draft

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_EPS = 1e-9


def _tol(decimals: int) -> float:
    return 0.5 * (10**-decimals) + _EPS


def _decimals_from_float(value: float) -> int:
    s = repr(float(value))
    if "e" in s or "E" in s:
        s = f"{value:.10f}".rstrip("0").rstrip(".")
    if "." not in s:
        return 0
    return len(s.split(".")[1])


def _check_intervals(draft: Draft, box: BoxReview) -> Check:
    if not draft.intervals:
        return Check(name="intervals", ok=True)
    if not box.runs:
        return Check(name="intervals", ok=False, detail="the box has no runs")
    lo = min(r.from_m for r in box.runs)
    hi = max(r.to_m for r in box.runs)
    bad = [i for i in draft.intervals if i.from_m < lo - _EPS or i.to_m > hi + _EPS]
    if not bad:
        return Check(name="intervals", ok=True)
    detail = "; ".join(f"interval {i.from_m}-{i.to_m} m is outside the box ({lo}-{hi} m)"
                       for i in bad)
    return Check(name="intervals", ok=False, detail=detail)


def _check_figures(draft: Draft, box: BoxReview) -> Check:
    if not draft.figures:
        return Check(name="figures", ok=True)
    problems: list[str] = []
    for fig in draft.figures:
        if not 0 <= fig.run < len(box.runs):
            problems.append(f"run {fig.run} does not exist (box has {len(box.runs)} runs)")
            continue
        expected = getattr(box.runs[fig.run].log, fig.metric)
        if abs(expected - fig.value) <= _tol(_decimals_from_float(fig.value)):
            continue
        problems.append(f"run {fig.run} {fig.metric} is {expected}, draft says {fig.value}")
    if problems:
        return Check(name="figures", ok=False, detail="; ".join(problems))
    return Check(name="figures", ok=True)


def _extract_numbers(text: str) -> list[tuple[str, float, int]]:
    out: list[tuple[str, float, int]] = []
    for m in _NUMBER.finditer(text):
        raw = m.group(0)
        norm = raw.replace(",", "")
        decimals = len(norm.split(".")[1]) if "." in norm else 0
        try:
            out.append((raw, float(norm), decimals))
        except ValueError:
            continue
    return out


def _run_numbers(box: BoxReview) -> list[float]:
    nums: list[float] = []
    for r in box.runs:
        log = r.log
        nums += [log.from_m, log.to_m, log.rqd_pct, log.tcr_pct,
                 log.fracture_frequency_per_m, float(log.natural_fractures),
                 float(log.uncertain_breaks), float(log.mechanical_breaks)]
    return nums


def _candidates(draft: Draft, box: BoxReview, prices: Prices,
                history: list[BoxReview]) -> list[float]:
    cands = _run_numbers(box)
    for b in history:
        cands += _run_numbers(b)
        cands.append(float(b.box_number))
    cands += [float(box.box_number), float(len(box.runs))]
    cands += [float(i) for i in range(1, len(box.runs) + 1)]  # runs named from one
    cands += [prices.hole_assay_budget_usd, prices.sample_length_m]
    cands += [t.unit_usd for t in prices.tests]
    for line in draft.lines:
        cands += [float(line.samples), line.unit_usd, line.total_usd]
    spent = Toolbox(box, list(history), prices).spent_usd()
    cands.append(spent)
    if draft.total_usd is not None:
        cands.append(draft.total_usd)
        left = round(prices.hole_assay_budget_usd - spent - draft.total_usd, 2)
        cands.append(left)
    for iv in draft.intervals:
        cands += [iv.from_m, iv.to_m]
        n = max(1, math.ceil(round((iv.to_m - iv.from_m) / prices.sample_length_m, 6)))
        cands.append(float(n))
    return cands


def _check_numbers(draft: Draft, box: BoxReview, prices: Prices,
                   history: list[BoxReview]) -> Check:
    text = f"{draft.title} {draft.body}".replace(box.hole_id, " ")
    found = _extract_numbers(text)
    if not found:
        return Check(name="numbers", ok=True)
    cands = _candidates(draft, box, prices, history)
    bad = [raw for raw, val, dec in found
           if not any(abs(val - c) <= _tol(dec) for c in cands)]
    if not bad:
        return Check(name="numbers", ok=True)
    uniq = list(dict.fromkeys(bad))
    return Check(name="numbers", ok=False, detail=f"numbers not from any tool: {', '.join(uniq)}")


def _check_prices(area: AreaKey, draft: Draft, prices: Prices) -> Check:
    if not draft.lines:
        if area == "finance":
            return Check(name="prices", ok=False,
                         detail="finance draft must include priced lines")
        return Check(name="prices", ok=True)
    problems: list[str] = []
    for line in draft.lines:
        table = prices.unit(line.code)
        if table is None:
            problems.append(f"unknown code {line.code}")
            continue
        if abs(line.unit_usd - table) > _EPS:
            problems.append(
                f"{line.code} unit ${line.unit_usd:.2f} differs from table ${table:.2f}")
        want = round(line.samples * line.unit_usd, 2)
        if abs(line.total_usd - want) > _EPS:
            problems.append(f"{line.code} total ${line.total_usd:.2f} should be ${want:.2f}")
    if draft.total_usd is None:
        problems.append("missing total_usd")
    else:
        want_total = round(sum(line.total_usd for line in draft.lines), 2)
        if abs(draft.total_usd - want_total) > _EPS:
            problems.append(f"total ${draft.total_usd:.2f} should be ${want_total:.2f}")
    if problems:
        return Check(name="prices", ok=False, detail="; ".join(problems))
    return Check(name="prices", ok=True)


def verify(area: AreaKey, draft: Draft, box: BoxReview, prices: Prices,
           history: list[BoxReview] = ()) -> list[Check]:
    return [
        _check_intervals(draft, box),
        _check_figures(draft, box),
        _check_numbers(draft, box, prices, history),
        _check_prices(area, draft, prices),
    ]
