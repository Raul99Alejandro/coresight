"""Stage 6: the orchestrator and the four area agents (lab, safety, plant, finance).

When the geologist approves a box, the orchestrator (Muse Wonder; plan B Muse
Spark 1.3 when Wonder fails) looks at the box through tools and decides which
areas of the mine it concerns and why. Each area agent (Muse Spark 1.3) then
writes a draft with its own tools. Every draft goes through verify.py, a
deterministic check, and a failed draft gets one retry with the failures as
feedback. Every step lands in a decision log the page shows.

Autonomy and its limits (Meta's "Agents Rule of Two": an agent should hold at
most two of [A] untrusted input, [B] private data or sensitive systems,
[C] changing state or communicating outside):
- The agents read model output about the photo [A] and the hole's history and
  price list [B]. They have no tool that sends, writes or changes anything [C]:
  a draft only reaches another area after a person approves it, and even then
  CoreSight only marks it approved; sending stays outside this program.
- Numbers come from tools backed by geometry.py and the example price table;
  the models never compute them, and verify.py rejects any that do not match.
- Tool arguments and submissions are validated with Pydantic before use.

All Meta calls go through meta_client.MetaClient.respond.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError

from coresight.geometry import rock_quality_class
from coresight.meta_client import MUSE_SPARK_MODEL_ID, MUSE_WONDER_MODEL_ID
from coresight.schemas import (
    AgentEvent,
    AreaDraft,
    AreaKey,
    BoxReview,
    Check,
    Draft,
    Handoffs,
    Routing,
)

PRICES_PATH = Path(__file__).resolve().parents[2] / "data" / "prices_example.json"
AREAS: tuple[AreaKey, ...] = ("lab", "safety", "plant", "finance")
MAX_TURNS = 8
T = TypeVar("T", bound=BaseModel)


class AgentError(RuntimeError):
    """An agent could not produce a valid submission."""


class PriceTest(BaseModel):
    code: str
    name: str
    unit_usd: float = Field(ge=0)


class Prices(BaseModel):
    """The price table. In the demo it is an example, and says so."""

    example: bool
    notice: str
    currency: str
    hole_assay_budget_usd: float = Field(ge=0)
    sample_length_m: float = Field(gt=0)
    tests: list[PriceTest]

    def unit(self, code: str) -> float | None:
        return next((t.unit_usd for t in self.tests if t.code == code), None)


def load_prices(path: Path = PRICES_PATH) -> Prices:
    return Prices.model_validate_json(path.read_text(encoding="utf-8"))


# --- Tools -----------------------------------------------------------------


class RunArg(BaseModel):
    run: int = Field(ge=0, description="0-based run index in this box")


class IntervalArg(BaseModel):
    from_m: float = Field(ge=0)
    to_m: float = Field(gt=0)


class QuoteLine(BaseModel):
    code: str
    samples: int = Field(ge=1)


class QuoteArg(BaseModel):
    lines: list[QuoteLine] = Field(min_length=1)


class NoArg(BaseModel):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[BaseModel], object]

    def definition(self) -> dict:
        schema = self.args.model_json_schema()
        schema.pop("title", None)
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": schema,
        }


class Toolbox:
    """What the agents can look at. Read-only: no tool changes or sends anything."""

    def __init__(self, box: BoxReview, history: list[BoxReview], prices: Prices) -> None:
        self.box, self.history, self.prices = box, history, prices
        self.lab_draft: Draft | None = None  # handed to finance once verified

    def _run(self, i: int):
        if not 0 <= i < len(self.box.runs):
            raise ValueError(f"run {i} does not exist; this box has {len(self.box.runs)} runs")
        return self.box.runs[i]

    def run_metrics(self, a: RunArg) -> dict:
        log = self._run(a.run).log
        return {
            "run": a.run,
            "from_m": log.from_m,
            "to_m": log.to_m,
            "rqd_pct": round(log.rqd_pct, 1),
            "tcr_pct": round(log.tcr_pct, 1),
            "fracture_frequency_per_m": round(log.fracture_frequency_per_m, 1),
            "natural_fractures": log.natural_fractures,
            "uncertain_breaks": log.uncertain_breaks,
            "rock_quality_deere": rock_quality_class(log.rqd_pct),
            "whole_run_in_photo": log.complete,
            "source": "geometry.py (deterministic), after the geologist's corrections",
        }

    def box_summary(self, _: NoArg) -> dict:
        runs = []
        for i, r in enumerate(self.box.runs):
            d = r.description
            runs.append(
                {
                    **self.run_metrics(RunArg(run=i)),
                    "lithology": d.lithology if d else None,
                    "alteration": d.alteration if d else None,
                    "mineralization": d.mineralization if d else None,
                    "anomalies": [a.type.value for a in d.anomalies] if d else [],
                    "geologist_comment": r.comment,
                }
            )
        return {"hole_id": self.box.hole_id, "box_number": self.box.box_number, "runs": runs}

    def hole_history(self, _: NoArg) -> dict:
        boxes = []
        for b in sorted(self.history, key=lambda b: b.box_number):
            boxes.append(
                {
                    "box_number": b.box_number,
                    "runs": [
                        {
                            "from_m": r.log.from_m,
                            "to_m": r.log.to_m,
                            "rqd_pct": round(r.log.rqd_pct, 1),
                            "rock_quality_deere": r.log.rock_quality,
                            "lithology": r.description.lithology if r.description else None,
                            "mineralization": (
                                r.description.mineralization if r.description else None
                            ),
                        }
                        for r in b.runs
                    ],
                }
            )
        note = "" if boxes else "No earlier approved box of this hole."
        return {"hole_id": self.box.hole_id, "earlier_boxes": boxes, "note": note}

    def count_samples(self, a: IntervalArg) -> dict:
        n = max(1, math.ceil(round((a.to_m - a.from_m) / self.prices.sample_length_m, 6)))
        return {"from_m": a.from_m, "to_m": a.to_m, "samples": n,
                "sample_length_m": self.prices.sample_length_m}  # fmt: skip

    def price_list(self, _: NoArg) -> dict:
        return self.prices.model_dump()

    def spent_usd(self) -> float:
        total = 0.0
        for b in self.history:
            for d in b.handoffs.drafts if b.handoffs else []:
                if d.area == "finance" and d.status == "approved" and d.draft:
                    total += d.draft.total_usd or 0.0
        return round(total, 2)

    def quote(self, a: QuoteArg) -> dict:
        lines, unknown = [], []
        for line in a.lines:
            unit = self.prices.unit(line.code)
            if unit is None:
                unknown.append(line.code)
                continue
            lines.append({"code": line.code, "samples": line.samples, "unit_usd": unit,
                          "total_usd": round(unit * line.samples, 2)})  # fmt: skip
        total = round(sum(x["total_usd"] for x in lines), 2)
        spent = self.spent_usd()
        budget = self.prices.hole_assay_budget_usd
        return {
            "lines": lines,
            "unknown_codes": unknown,
            "total_usd": total,
            "hole_budget_usd": budget,
            "spent_before_usd": spent,
            "remaining_after_usd": round(budget - spent - total, 2),
            "notice": self.prices.notice,
        }

    def lab_request(self, _: NoArg) -> dict:
        if self.lab_draft is None:
            return {"note": "No verified lab request for this box."}
        return self.lab_draft.model_dump()

    def tools(self) -> dict[str, Tool]:
        t = [
            Tool("box_summary", "Every run of the approved box: depths, RQD, TCR, fracture "
                 "frequency and Deere class from geometry.py, plus the geologist-reviewed "
                 "description and anomaly flags.", NoArg, self.box_summary),
            Tool("run_metrics", "Geotechnical numbers of one run, from geometry.py.",
                 RunArg, self.run_metrics),
            Tool("hole_history", "Earlier approved boxes of the same drill hole.",
                 NoArg, self.hole_history),
            Tool("count_samples", "How many assay samples an interval makes at the "
                 "standard sample length.", IntervalArg, self.count_samples),
            Tool("price_list", "The assay price table (an EXAMPLE table in this demo) and "
                 "the hole's assay budget.", NoArg, self.price_list),
            Tool("quote", "Price assay lines with the table and show the effect on the "
                 "hole's budget. Unknown codes are refused.", QuoteArg, self.quote),
            Tool("lab_request", "The lab's verified assay request for this box.",
                 NoArg, self.lab_request),
        ]  # fmt: skip
        return {x.name: x for x in t}


# --- Roles -----------------------------------------------------------------

COMMON = (
    "You work for CoreSight, a drill-core logging system at a mine. A geologist just "
    "approved the log of one core box. Every number you use must come from a tool; "
    "never compute RQD, TCR, fracture counts or prices yourself. Quote numbers exactly "
    "as the tools return them. Write in clear, short English. You only write a draft: "
    "nothing you write is sent until a person approves it."
)

ORCHESTRATOR = (
    "You are the orchestrator. Decide which areas of the mine this box concerns, and "
    "why, after looking at it with your tools. Areas:\n"
    "- lab: intervals worth assaying (visible sulfides, strong alteration, veins).\n"
    "- safety: ground conditions for the geotechnical and safety team (poor or very "
    "poor rock, intense fracturing, low recovery).\n"
    "- plant: a change in rock type or mineralization compared with earlier boxes of "
    "the hole that the processing plant should hear about.\n"
    "- finance: the cost of an assay request against the hole's budget; it applies "
    "only if lab applies.\n"
    "Give one route per area, applies true or false, with a reason that cites the "
    "runs and the numbers you read. Then call route_box."
)

AREA_ROLES: dict[AreaKey, str] = {
    "lab": "You are the lab agent. Draft an assay request: which intervals to sample, "
           "the tests (codes from price_list) and the priority. Use count_samples for "
           "the number of samples of each interval. Put each interval in intervals.",
    "safety": "You are the geotechnical and safety agent. Draft a ground-condition alert "
              "for the runs with poor or very poor rock or intense fracturing: Deere "
              "class, RQD, fracture frequency and what to check (support, scaling). Put "
              "every number you quote in figures and every run in intervals.",
    "plant": "You are the processing plant agent. Draft a short notice on the ore type "
             "coming (rock type, sulfides) and how it differs from earlier boxes of the "
             "hole. Put the intervals you mention in intervals.",
    "finance": "You are the finance agent. Read the lab request, price it with quote "
               "and draft the cost and its effect on the hole's assay budget. Copy the "
               "lines and total from quote into lines and total_usd. Say the prices are "
               "an example table.",
}  # fmt: skip

AREA_TOOLS: dict[AreaKey, tuple[str, ...]] = {
    "lab": ("box_summary", "run_metrics", "count_samples", "price_list"),
    "safety": ("box_summary", "run_metrics", "hole_history"),
    "plant": ("box_summary", "hole_history"),
    "finance": ("lab_request", "quote", "price_list"),
}
ORCHESTRATOR_TOOLS = ("box_summary", "run_metrics", "hole_history")

AREA_NAMES = {"lab": "Lab", "safety": "Safety & geotechnics", "plant": "Plant",
              "finance": "Finance"}  # fmt: skip


# --- The loop --------------------------------------------------------------


class Log:
    def __init__(self, handoffs: Handoffs, save: Callable[[], None]) -> None:
        self.handoffs, self._save = handoffs, save

    def __call__(self, actor: str, kind: str, text: str, model: str | None = None) -> None:
        self.handoffs.log.append(
            AgentEvent(at=datetime.now(UTC), actor=actor, kind=kind, text=text, model=model)
        )
        self._save()


def _brief(value: object, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def run_agent(
    client,
    model: str,
    prompt: str,
    tools: list[Tool],
    submit_name: str,
    submit_description: str,
    submit: type[T],
    log: Log,
    actor: str,
) -> T:
    """Tool loop until the agent calls its submit tool with valid arguments."""
    defs = [t.definition() for t in tools]
    schema = submit.model_json_schema()
    schema.pop("title", None)
    defs.append({"type": "function", "name": submit_name, "description": submit_description,
                 "parameters": schema})  # fmt: skip
    by_name = {t.name: t for t in tools}
    history: list[dict] = [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}
    ]
    for _ in range(MAX_TURNS):
        response = client.respond({"model": model, "input": history, "tools": defs})
        output = response.get("output", [])
        calls = [o for o in output if o.get("type") == "function_call"]
        history += output
        if not calls:
            history.append({"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": f"Call {submit_name} to finish."}]})  # fmt: skip
            continue
        for call in calls:
            name = call.get("name")
            try:
                args = json.loads(call.get("arguments") or "{}")
                if name == submit_name:
                    return submit.model_validate(args)
                tool = by_name[name]
                result = tool.run(tool.args.model_validate(args))
                log(actor, "tool", f"{name}({_brief(args, 80)}) → {_brief(result)}", model)
            except KeyError:
                result = {"error": f"unknown tool {name}"}
            except (ValueError, ValidationError) as exc:  # bad arguments: tell the model
                result = {"error": str(exc)[:400]}
                log(actor, "retry", f"{name}: {str(exc)[:160]}", model)
            history.append({"type": "function_call_output", "call_id": call["call_id"],
                            "output": json.dumps(result)})  # fmt: skip
    raise AgentError(f"{actor}: no valid {submit_name} after {MAX_TURNS} turns")


Verifier = Callable[[AreaKey, Draft, BoxReview, Prices, list[BoxReview]], list[Check]]


def route(client, toolbox: Toolbox, log: Log) -> tuple[Routing, str]:
    """Muse Wonder decides; if it fails, Muse Spark 1.3 does the same job."""
    tools = [toolbox.tools()[n] for n in ORCHESTRATOR_TOOLS]
    prompt = f"{COMMON}\n\n{ORCHESTRATOR}"
    for model in (MUSE_WONDER_MODEL_ID, MUSE_SPARK_MODEL_ID):
        log("orchestrator", "model", f"{model} is reading the box", model)
        try:
            routing = run_agent(client, model, prompt, tools, "route_box",
                                "Submit the decision for every area.", Routing, log,
                                "orchestrator")  # fmt: skip
        except Exception as exc:  # Wonder is in preview: fall back, say so
            log("orchestrator", "error", f"{model} failed: {str(exc)[:200]}", model)
            continue
        missing = set(AREAS) - {r.area for r in routing.routes}
        if missing:
            log("orchestrator", "error", f"{model} skipped {sorted(missing)}", model)
            continue
        return routing, model
    raise AgentError("Neither Muse Wonder nor Muse Spark produced a routing.")


def write_draft(
    client, area: AreaKey, toolbox: Toolbox, reason: str, verifier: Verifier, log: Log,
    slot: AreaDraft, save: Callable[[], None],
) -> None:  # fmt: skip
    """One area agent: draft, verify, and one retry with the failed checks."""
    tools = [toolbox.tools()[n] for n in AREA_TOOLS[area]]
    base = f"{COMMON}\n\n{AREA_ROLES[area]}\n\nWhy the orchestrator sent you this box: {reason}"
    prompt = base
    for attempt in (1, 2):
        draft = run_agent(client, slot.model, prompt, tools, "submit_draft",
                          "Submit your draft.", Draft, log, area)  # fmt: skip
        checks = verifier(area, draft, toolbox.box, toolbox.prices, toolbox.history)
        failed = [c for c in checks if not c.ok]
        slot.draft, slot.checks, slot.verified = draft, checks, bool(checks) and not failed
        log(area, "draft", f"“{draft.title}”", slot.model)
        log("verifier", "check", f"{area}: {len(checks) - len(failed)} of {len(checks)} checks"
            " passed" + (": " + "; ".join(c.detail for c in failed) if failed else ""))  # fmt: skip
        if slot.verified or attempt == 2:
            break
        log(area, "retry", "sent back with the failed checks", slot.model)
        notes = "\n".join(f"- {c.name}: {c.detail}" for c in failed)
        prompt = f"{base}\n\nYour previous draft failed these checks. Fix them:\n{notes}"
    slot.status = "ready" if slot.verified else "rejected"
    save()


def draft_handoffs(
    box: BoxReview,
    history: list[BoxReview],
    client,
    verifier: Verifier,
    prices: Prices | None = None,
    save: Callable[[Handoffs], None] = lambda h: None,
) -> Handoffs:
    """Route an approved box and write the drafts. Saves after every step."""
    handoffs = Handoffs()
    persist = lambda: save(handoffs)  # noqa: E731
    log = Log(handoffs, persist)
    toolbox = Toolbox(box, history, prices or load_prices())
    try:
        handoffs.routing, handoffs.orchestrator_model = route(client, toolbox, log)
        for r in handoffs.routing.routes:
            verdict = "applies" if r.applies else "does not apply"
            log("orchestrator", "route", f"{AREA_NAMES[r.area]} {verdict}: {r.reason}",
                handoffs.orchestrator_model)  # fmt: skip
        applies = {r.area: r for r in handoffs.routing.routes if r.applies}
        for area in AREAS:
            if area not in applies:
                continue
            if area == "finance" and toolbox.lab_draft is None:
                log("finance", "error", "skipped: there is no verified lab request to price")
                continue
            slot = AreaDraft(area=area, model=MUSE_SPARK_MODEL_ID)
            handoffs.drafts.append(slot)
            persist()
            try:
                write_draft(client, area, toolbox, applies[area].reason, verifier, log,
                            slot, persist)  # fmt: skip
            except Exception as exc:
                slot.status, slot.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
                log(area, "error", slot.error, slot.model)
            if area == "lab" and slot.verified:
                toolbox.lab_draft = slot.draft
        handoffs.status = "done"
    except Exception as exc:
        handoffs.status, handoffs.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
    persist()
    return handoffs


def approve_draft(box: BoxReview, area: AreaKey) -> AreaDraft:
    """A person approves one draft. It is marked approved; nothing is sent."""
    slot = next((d for d in box.handoffs.drafts if d.area == area), None) if box.handoffs else None
    if slot is None:
        raise ValueError(f"There is no {area} draft for this box.")
    if slot.status != "ready" or not slot.verified:
        raise ValueError("Only a draft that passed every check can be approved.")
    now = datetime.now(UTC)
    slot.status, slot.approved_at = "approved", now
    box.handoffs.log.append(AgentEvent(at=now, actor="geologist", kind="approve",
        text=f"{AREA_NAMES[area]} draft approved. Not sent: CoreSight has no outbound "
             "channel; the area receives it through the mine's own process."))  # fmt: skip
    return slot

