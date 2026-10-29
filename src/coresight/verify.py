"""Deterministic check of every area draft before a person sees it."""

from __future__ import annotations

import math
import re

from coresight.agents import Prices, Toolbox
from coresight.schemas import (
    AreaKey,
    BoxReview,
    Check,
    Draft,
    HoleFinding,
    HoleTrend,
    Routing,
    RoutingSignals,
)

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


_FIGURE_WORDS = {
    "rqd_pct": ("RQD", " %"),
    "tcr_pct": ("recovery", " %"),
    "fracture_frequency_per_m": ("fracture frequency", " per metre"),
    "natural_fractures": ("natural fractures", ""),
}


def _figure_value(metric: str, value: float) -> str:
    if metric == "natural_fractures" and float(value).is_integer():
        return str(int(value))
    return str(value)


def _check_figures(draft: Draft, box: BoxReview) -> Check:
    if not draft.figures:
        return Check(name="figures", ok=True)
    problems: list[str] = []
    for fig in draft.figures:
        if not 1 <= fig.run <= len(box.runs):
            problems.append(
                f"Run {fig.run} does not exist: this box has runs 1 to {len(box.runs)}"
            )
            continue
        expected = getattr(box.runs[fig.run - 1].log, fig.metric)
        if abs(expected - fig.value) <= _tol(_decimals_from_float(fig.value)):
            continue
        label, unit = _FIGURE_WORDS[fig.metric]
        want = f"{_figure_value(fig.metric, expected)}{unit}"
        got = f"{_figure_value(fig.metric, fig.value)}{unit}"
        problems.append(f"Run {fig.run} {label} is {want}, the draft says {got}")
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


def _trend_numbers(trends: list[HoleTrend]) -> list[float]:
    nums: list[float] = []
    for t in trends:
        nums += [t.from_m, t.to_m]
        nums += [float(n) for n in t.boxes]
        for v in (t.rqd_before_pct, t.rqd_after_pct, t.rqd_pct, t.min_rqd_pct):
            if v is not None:
                nums.append(float(v))
    return nums


def _candidates(draft: Draft, box: BoxReview, prices: Prices,
                history: list[BoxReview], trends: list[HoleTrend] = ()) -> list[float]:
    cands = _run_numbers(box)
    for b in history:
        cands += _run_numbers(b)
        cands.append(float(b.box_number))
    cands += [float(box.box_number), float(len(box.runs))]
    cands += [float(i) for i in range(1, len(box.runs) + 1)]  # runs named from one
    cands += _trend_numbers(list(trends))
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
                   history: list[BoxReview], trends: list[HoleTrend] = ()) -> Check:
    text = f"{draft.title} {draft.body}".replace(box.hole_id, " ")
    found = _extract_numbers(text)
    if not found:
        return Check(name="numbers", ok=True)
    cands = _candidates(draft, box, prices, history, list(trends))
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
           history: list[BoxReview] = (), trends: list[HoleTrend] = ()) -> list[Check]:
    return [
        _check_intervals(draft, box),
        _check_figures(draft, box),
        _check_numbers(draft, box, prices, history, trends),
        _check_prices(area, draft, prices),
        _role_over_fields(draft.title, draft.body),
    ]


# --- Milestones before the area agents write (point E) ------------------------

_TREND_WORDS = {
    "rqd_drop": "an RQD drop",
    "weak_zone": "a weak zone",
    "lithology_change": "a change of rock",
    "sulfides_appear": "sulfides appearing",
    "sulfides_gone": "sulfides ending",
}


def _check_finding_trends(finding: HoleFinding, trends: list[HoleTrend]) -> Check:
    found = {t.kind for t in trends}
    unknown = list(dict.fromkeys(k for k in finding.trends if k not in found))
    if not unknown:
        return Check(name="trends", ok=True)
    parts = [f"Code did not find {_TREND_WORDS[k]} along the hole." for k in unknown]
    return Check(name="trends", ok=False, detail=" ".join(parts))


def _check_finding_action(finding: HoleFinding, trends: list[HoleTrend]) -> Check:
    action = finding.action
    if action == "none":
        return Check(name="action", ok=True)
    if not trends:
        return Check(name="action", ok=False,
                     detail="With no changes along the hole, only doing nothing is allowed")
    cited = set(finding.trends)
    if action in ("oriented_core", "warn_geotech"):
        if cited & {"rqd_drop", "weak_zone"}:
            return Check(name="action", ok=True)
        if action == "oriented_core":
            detail = "Oriented core needs an RQD drop or a weak zone along the hole"
        else:
            detail = "Warning geotechnics needs an RQD drop or a weak zone along the hole"
        return Check(name="action", ok=False, detail=detail)
    if cited & {"lithology_change", "sulfides_appear", "sulfides_gone"}:
        return Check(name="action", ok=True)
    detail = ("Sampling the contact needs a change of rock, sulfides appearing or "
              "sulfides ending along the hole")
    return Check(name="action", ok=False, detail=detail)


_PERCENT_WORD = re.compile(r"(?:per\s+cent|percent(?:age)?|pct)\b", re.IGNORECASE)


def _extract_numbers_pct(text: str) -> list[tuple[str, float, int, bool]]:
    out: list[tuple[str, float, int, bool]] = []
    for m in _NUMBER.finditer(text):
        raw = m.group(0)
        norm = raw.replace(",", "")
        decimals = len(norm.split(".")[1]) if "." in norm else 0
        try:
            val = float(norm)
        except ValueError:
            continue
        start = m.start()
        if start > 0 and text[start - 1] == "-" and (start < 2 or not text[start - 2].isdigit()):
            raw = "-" + raw
            val = -val
        after = text[m.end():].lstrip()
        is_pct = after.startswith("%") or bool(_PERCENT_WORD.match(after))
        out.append((raw, val, decimals, is_pct))
    return out


def _percent_numbers(box: BoxReview, history: list[BoxReview],
                     trends: list[HoleTrend]) -> list[float]:
    pct: list[float] = []
    for b in [box, *history]:
        for r in b.runs:
            pct += [r.log.rqd_pct, r.log.tcr_pct]
    for t in trends:
        for v in (t.rqd_before_pct, t.rqd_after_pct, t.rqd_pct, t.min_rqd_pct):
            if v is not None:
                pct.append(float(v))
    return pct


def _finding_candidates(box: BoxReview, history: list[BoxReview],
                        trends: list[HoleTrend]) -> list[float]:
    cands = _run_numbers(box)
    for b in history:
        cands += _run_numbers(b)
        cands.append(float(b.box_number))
    cands += [float(box.box_number), float(len(box.runs))]
    cands += [float(i) for i in range(1, len(box.runs) + 1)]
    cands += _trend_numbers(list(trends))
    return cands


def _check_finding_numbers(finding: HoleFinding, trends: list[HoleTrend], box: BoxReview,
                           history: list[BoxReview]) -> Check:
    text = f"{finding.title} {finding.body}".replace(box.hole_id, " ")
    found = _extract_numbers_pct(text)
    if not found:
        return Check(name="numbers", ok=True)
    cands = _finding_candidates(box, list(history), list(trends))
    pct = _percent_numbers(box, list(history), list(trends))
    bad = [raw for raw, val, dec, is_pct in found
           if not any(abs(val - c) <= _tol(dec) for c in (pct if is_pct else cands))]
    if not bad:
        return Check(name="numbers", ok=True)
    uniq = list(dict.fromkeys(bad))
    return Check(name="numbers", ok=False, detail=f"numbers not from any tool: {', '.join(uniq)}")


def check_finding(
    finding: HoleFinding,
    trends: list[HoleTrend],
    box: BoxReview,
    history: list[BoxReview] = (),
) -> list[Check]:
    """The hole agent's finding against the trends code found: cited trends, action, numbers."""
    return [
        _check_finding_trends(finding, list(trends)),
        _check_finding_action(finding, list(trends)),
        _check_finding_numbers(finding, list(trends), box, list(history)),
        _role_over_fields(finding.title, finding.body, finding.action_reason),
    ]


def _safety_trends(trends: list[HoleTrend]) -> list[HoleTrend]:
    return [t for t in trends if t.kind in ("rqd_drop", "weak_zone")]


def _sulfide_trends(trends: list[HoleTrend]) -> list[HoleTrend]:
    return [t for t in trends if t.kind in ("sulfides_appear", "sulfides_gone")]


def _check_lab(applies: bool, signals: RoutingSignals) -> Check:
    if signals.sulfides:
        if not applies:
            return Check(name="lab", ok=False,
                         detail="Lab must apply: the approved description shows sulfides")
        return Check(name="lab", ok=True)
    if not signals.lab_evidence and applies:
        return Check(name="lab", ok=False, detail=(
            "Lab cannot apply: the approved description shows no mineralization, "
            "alteration or veins"))
    return Check(name="lab", ok=True)


def _check_safety(applies: bool, signals: RoutingSignals) -> Check:
    poor = signals.min_rqd_pct < 25
    reached = _safety_trends(list(signals.trends))
    if (poor or reached) and not applies:
        reasons = [t.summary for t in reached]
        if poor:
            reasons.insert(0, f"the worst run is very poor rock (RQD {signals.min_rqd_pct} %)")
        return Check(name="safety", ok=False,
                     detail=f"Safety must apply: {'; '.join(reasons)}")
    good = signals.min_rqd_pct >= 75 and signals.min_tcr_pct >= 75 and not reached
    if good and applies:
        return Check(name="safety", ok=False, detail=(
            f"Safety cannot apply: the worst run has RQD {signals.min_rqd_pct} % and "
            f"recovery {signals.min_tcr_pct} %, and no drop or weak zone reaches the box"))
    return Check(name="safety", ok=True)


def _check_plant(applies: bool, signals: RoutingSignals) -> Check:
    sulfide = _sulfide_trends(list(signals.trends))
    if sulfide and not applies:
        return Check(name="plant", ok=False,
                     detail=f"Plant must apply: {'; '.join(t.summary for t in sulfide)}")
    has_rock = any(t.kind == "lithology_change" for t in signals.trends)
    if not has_rock and not sulfide and not signals.sulfides and applies:
        return Check(name="plant", ok=False, detail=(
            "Plant cannot apply: no change of rock or sulfides along the hole, "
            "and no sulfides in the box"))
    return Check(name="plant", ok=True)


def _check_finance(applies: bool, lab_applies: bool | None) -> Check:
    if lab_applies is None:
        lab_applies = False
    if lab_applies and not applies:
        return Check(name="finance", ok=False,
                     detail="Finance must apply: lab applies, and finance prices its request")
    if not lab_applies and applies:
        return Check(name="finance", ok=False, detail=(
            "Finance cannot apply: lab does not apply, so there is no request to price"))
    return Check(name="finance", ok=True)


def check_routing(routing: Routing, signals: RoutingSignals) -> list[Check]:
    """The orchestrator's routing against what code knows of the box: one check per area."""
    by_area = {r.area: r for r in routing.routes}
    lab = by_area.get("lab")
    lab_applies = lab.applies if lab is not None else None
    out: list[Check] = []
    for area in ("lab", "safety", "plant", "finance"):
        route = by_area.get(area)
        if route is None:
            out.append(Check(name=area, ok=False, detail=f"{area.capitalize()} has no route"))
            continue
        if area == "lab":
            out.append(_check_lab(route.applies, signals))
        elif area == "safety":
            out.append(_check_safety(route.applies, signals))
        elif area == "plant":
            out.append(_check_plant(route.applies, signals))
        else:
            out.append(_check_finance(route.applies, lab_applies))
    return out


# --- A draft proposes, it never decides for the operation (point 7) ----------------

_ROLE_DETAIL_TAIL = (
    ". A draft only proposes: check support, scale and inspect, review before "
    "the next run, warn geotechnics, ask for oriented core, sample the contact, "
    "send to the lab or ask the plant for a test. People in charge decide "
    "whether work stops."
)

_ROLE_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")

_ROLE_STOP_SINGLE = {
    "stop", "stops", "halt", "halts", "suspend", "suspends",
    "pause", "pauses", "cease", "ceases", "freeze", "freezes",
}
_ROLE_DOWN_FIRST = {"shut", "shuts", "stand", "stands"}
_ROLE_HOLD_FIRST = {"hold", "holds"}
_ROLE_OPERATION = {
    "drill", "drilling", "rig", "work", "works",
    "operation", "operations", "production", "advance",
}
_ROLE_SUBJECT = {
    "drill", "drilling", "rig", "work", "works",
    "operation", "operations", "production",
}
_ROLE_WAIT_HOLD = {"wait", "waits", "hold", "holds"}
_ROLE_NEG_SINGLE = {"cannot", "don't", "can't"}
_ROLE_NEG_PAIR = {
    ("do", "not"), ("must", "not"), ("should", "not"),
    ("no", "further"), ("not", "to"),
}
_ROLE_GOING_ON = {
    "drill", "drilling", "drills", "continue", "continues",
    "proceed", "proceeds", "advance", "advances",
    "resume", "resumes", "start", "starts",
}
_ROLE_CLEAR_SINGLE = {
    "clears", "cleared", "clearance", "approves", "approval", "released",
}
_ROLE_SIGN_FIRST = {"sign", "signs"}
_ROLE_OPENERS = {"\"", "'", "’", "‘", "“", "”", "(", "[", "{"}
_ROLE_LIST_SINGLE = {"-", "*", "•"}


def _role_tokens(text: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for m in _ROLE_WORD.finditer(text):
        raw = m.group(0)
        out.append((raw.lower().replace("’", "'"), m.start(), m.end()))
    return out


def _role_sentence_ids(text: str, starts: list[int]) -> list[int]:
    ends: list[int] = []
    for i, ch in enumerate(text):
        if ch in "\r\n":
            ends.append(i)
        elif ch in ".!?" and (i + 1 == len(text) or text[i + 1].isspace()):
            ends.append(i)
    ids: list[int] = []
    k = 0
    for s in starts:
        while k < len(ends) and ends[k] < s:
            k += 1
        ids.append(k)
    return ids


def _role_is_command(text: str, tokens: list[tuple[str, int, int]],
                     sent: list[int], idx: int) -> bool:
    if idx == 0 or sent[idx] != sent[idx - 1]:
        return True
    j = tokens[idx][1] - 1
    while j >= 0:
        ch = text[j]
        if ch.isspace() or ch in _ROLE_OPENERS or ch in _ROLE_LIST_SINGLE:
            j -= 1
            continue
        if ch == ".":
            k = j - 1
            while k >= 0 and text[k].isdigit():
                k -= 1
            if k < j - 1:
                j = k
                continue
        break
    if j < 0:
        return True
    return text[j] in ":;"


def _role_stops(norms: list[str], sent: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(norms):
        if i + 1 < len(norms) and sent[i] == sent[i + 1]:
            a, b = norms[i], norms[i + 1]
            if (a in _ROLE_DOWN_FIRST and b == "down"
                    or a in _ROLE_HOLD_FIRST and b == "off"):
                out.append((i, i + 1))
                i += 2
                continue
        if norms[i] in _ROLE_STOP_SINGLE:
            out.append((i, i))
        i += 1
    return out


def _role_operations(norms: list[str], sent: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(norms):
        if (i + 2 < len(norms) and norms[i] == "the"
                and norms[i + 1] == "next" and norms[i + 2] == "run"
                and sent[i] == sent[i + 2]):
            out.append((i, i + 2))
            i += 3
            continue
        if norms[i] in _ROLE_OPERATION:
            out.append((i, i))
        i += 1
    return out


def _role_negations(norms: list[str], sent: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(norms):
        if (i + 1 < len(norms) and sent[i] == sent[i + 1]
                and (norms[i], norms[i + 1]) in _ROLE_NEG_PAIR):
            out.append((i, i + 1))
            i += 2
            continue
        if norms[i] in _ROLE_NEG_SINGLE:
            out.append((i, i))
        i += 1
    return out


def _role_clearances(norms: list[str], sent: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(norms):
        if (i + 1 < len(norms) and norms[i] in _ROLE_SIGN_FIRST
                and norms[i + 1] == "off" and sent[i] == sent[i + 1]):
            out.append((i, i + 1))
            i += 2
            continue
        if norms[i] in _ROLE_CLEAR_SINGLE:
            out.append((i, i))
        i += 1
    return out


def check_role(text: str) -> Check:
    """Fails when the text tells the operation to stop, hold or not go on.

    The rules are in the docstring of tests/test_verify_role.py.
    """
    tokens = _role_tokens(text)
    if not tokens:
        return Check(name="role", ok=True)
    norms = [t[0] for t in tokens]
    sent = _role_sentence_ids(text, [t[1] for t in tokens])
    stops = _role_stops(norms, sent)
    operations = _role_operations(norms, sent)
    matches: list[tuple[int, int]] = []
    for s, e in stops:
        op_after: tuple[int, int] | None = None
        for o_s, o_e in operations:
            if o_s > e:
                if sent[e] == sent[o_s] and o_s - e - 1 <= 4:
                    op_after = (o_s, o_e)
                break
        if op_after is not None or _role_is_command(text, tokens, sent, s):
            end = tokens[op_after[1]][2] if op_after else tokens[e][2]
            matches.append((tokens[s][1], end))
    verbs = list(stops)
    multi_starts = {s for s, e in stops if e > s}
    for i, n in enumerate(norms):
        if n in _ROLE_WAIT_HOLD and i not in multi_starts:
            verbs.append((i, i))
    verbs.sort()
    for i, n in enumerate(norms):
        if n not in _ROLE_SUBJECT:
            continue
        for v_s, v_e in verbs:
            if v_s > i:
                if sent[i] == sent[v_e] and v_s - i - 1 <= 4:
                    matches.append((tokens[i][1], tokens[v_e][2]))
                break
    go_at = [i for i, n in enumerate(norms) if n in _ROLE_GOING_ON]
    for n_s, n_e in _role_negations(norms, sent):
        for g in go_at:
            if g > n_e:
                if sent[n_e] == sent[g] and g - n_e - 1 <= 3:
                    matches.append((tokens[n_s][1], tokens[g][2]))
                break
    until_at = [i for i, n in enumerate(norms) if n == "until"]
    clearances = _role_clearances(norms, sent)
    for o_s, o_e in operations:
        want = sent[o_e]
        for u in until_at:
            if u <= o_e:
                continue
            if sent[u] != want:
                if sent[u] > want:
                    break
                continue
            found: tuple[int, int] | None = None
            for c_s, c_e in clearances:
                if c_s <= u:
                    continue
                if sent[c_s] != want:
                    if sent[c_s] > want:
                        break
                    continue
                found = (c_s, c_e)
                break
            if found is not None and found[0] - u - 1 <= 6:
                matches.append((tokens[o_s][1], tokens[found[1]][2]))
                break
    if not matches:
        return Check(name="role", ok=True)
    start, end = min(matches)
    quote = text[start:end]
    detail = f'The draft tells the operation to stop ("{quote}"){_ROLE_DETAIL_TAIL}'
    return Check(name="role", ok=False, detail=detail)


def _role_over_fields(*texts: str) -> Check:
    for text in texts:
        found = check_role(text)
        if not found.ok:
            return found
    return Check(name="role", ok=True)
