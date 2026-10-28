"""Stage 6: the hole agent, the orchestrator and the four area agents.

When the geologist approves a box:
1. Code finds the trends along the hole (hole.hole_trends: RQD drop from the box
   above, weak zones, a change of rock, sulfides that appear or end). The hole agent
   (Muse Spark 1.3) reads them and proposes one action, from a closed list.
2. The orchestrator (Muse Wonder; plan B Muse Spark 1.3 when Wonder fails) reads the
   box, the hole and the hole agent's finding and decides which areas of the mine it
   concerns and why. Its prompt holds no routing rules.
3. Each area agent (Muse Spark 1.3) writes a draft with its own tools.

Verification is part of each submit step, not a tool an agent may skip (Meta's
Agents 102), and it runs at three milestones: the finding, the routing (before
any area agent writes) and every draft. Two layers: deterministic checks in
verify.py first; then, only if they pass, Muse Spark as a judge checks every text
claim against the geologist-approved record. The judge never runs on, and so never
passes, what verify.py rejected. A failure goes back to the agent with the reasons,
at most three attempts; after that the result reaches a person marked with why.
Every step, with turns, attempts and seconds of verification, lands in a decision
log the page shows as sentences.

Autonomy and its limits (Meta's "Agents Rule of Two": an agent should hold at
most two of [A] untrusted input, [B] private data or sensitive systems,
[C] changing state or communicating outside):
- The agents read model output about the photo [A] and the hole's history and
  price list [B]. They have no tool that sends, writes or changes anything [C]:
  a draft only reaches another area after a person approves it, and even then
  CoreSight only marks it approved; sending stays outside this program.
- The tool list of each agent is closed: a call to any other tool is refused.
- Numbers come from tools backed by geometry.py and the example price table;
  the models never compute them, and verify.py rejects any that do not match.
- Tool arguments and submissions are validated with Pydantic before use.

All Meta calls go through meta_client.MetaClient.respond.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, Field, ValidationError

from coresight import hole
from coresight.geometry import rock_quality_class
from coresight.meta_client import MUSE_SPARK_MODEL_ID, MUSE_WONDER_MODEL_ID
from coresight.schemas import (
    AgentEvent,
    AreaDraft,
    AreaKey,
    BoxReview,
    Check,
    Draft,
    Effort,
    Handoffs,
    HoleFinding,
    HoleReport,
    HoleTrend,
    JudgeVerdict,
    Routing,
    RoutingSignals,
)

PRICES_PATH = Path(__file__).resolve().parents[2] / "data" / "prices_example.json"
AREAS: tuple[AreaKey, ...] = ("lab", "safety", "plant", "finance")
MAX_TURNS = 8
MAX_ATTEMPTS = 3  # Agents 102: at most three attempts, then a person decides
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
    run: int = Field(ge=1, description="Run number in this box; 1 is the first run")


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
        self.finding: HoleFinding | None = None  # the hole agent's, once verified
        self.trends: list[HoleTrend] = hole.hole_trends(history, box) if box.runs else []

    def _run(self, n: int):
        if not 1 <= n <= len(self.box.runs):
            raise ValueError(f"run {n} does not exist; this box has runs 1 to {len(self.box.runs)}")
        return self.box.runs[n - 1]

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
                    **self.run_metrics(RunArg(run=i + 1)),
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

    def hole_log(self, _: NoArg) -> dict:
        """The hole by depth up to this box (earlier approved boxes and this one)."""
        boxes = [*self.history, self.box]  # the agents run after approval
        return hole.depth_history(hole.hole_view(boxes, self.box.hole_id))

    def hole_trends(self, _: NoArg) -> dict:
        """Trends between boxes that reach this box, found by code (hole.hole_trends)."""
        return {
            "hole_id": self.box.hole_id,
            "box_number": self.box.box_number,
            "trends": [t.model_dump(exclude_none=True) for t in self.trends],
            "note": "" if self.trends else "No trend along the hole reaches this box.",
            "source": "hole.hole_trends: numbers from geometry.py, rock names and sulfides "
            "from the geologist-approved descriptions",
        }

    def hole_finding(self, _: NoArg) -> dict:
        if self.finding is None:
            return {"note": "The hole agent has no verified finding for this box."}
        return self.finding.model_dump()

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
            Tool("hole_log", "The drill hole by depth up to this box, from geometry.py: "
                 "RQD, TCR, fracture frequency, Deere class, lithology and anomalies by run "
                 "and by 1 m interval, weak zones (consecutive poor intervals), and gaps or "
                 "overlaps between boxes.", NoArg, self.hole_log),
            Tool("hole_trends", "Trends along the hole that reach this box, found by code: "
                 "an RQD drop from the box above, weak zones, a change of rock at the "
                 "contact, sulfides that appear or end. Each with depths, boxes and a "
                 "summary sentence.", NoArg, self.hole_trends),
            Tool("hole_finding", "The hole agent's verified finding: the trends it "
                 "confirms and the action it proposes.", NoArg, self.hole_finding),
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
    "as the tools return them. Write in clear, short English for people at the mine: "
    "name runs by their number (Run 1 is the first) or their depth, and write metrics as "
    "people read them (RQD 26.7 %, recovery 53.1 %, 4.2 fractures per metre), never as "
    "field names such as rqd_pct. You only write a draft: nothing you write is sent until "
    "a person approves it."
)

HOLE_ROLE = (
    "You are the hole agent. You look at the whole drill hole, not one box. Read the "
    "trends code found along the hole with hole_trends, and the hole log or the box if "
    "you need more. Decide which trends matter for the next metres of drilling and for "
    "the mine, and propose one action:\n"
    "- oriented_core: ask the drillers for oriented core in the next runs, so the "
    "structure behind poor ground can be measured.\n"
    "- warn_geotech: warn geotechnics before the next run is drilled.\n"
    "- sample_contact: sample across a change of rock or of sulfides.\n"
    "- none: nothing along the hole needs an action now.\n"
    "Cite in trends the kinds you rely on. Write a title and a short body for the "
    "geologist with the depths, boxes and numbers as hole_trends gives them. A "
    "geological reading (for example a possible fault zone) must say what record it "
    "rests on. Then call submit_finding."
)

# No routing rules here: the orchestrator decides. Code checks the decision after.
ORCHESTRATOR = (
    "You are the orchestrator. Decide which areas of the mine should hear about this "
    "box, and why. What each area does:\n"
    "- lab: assays core for metals and other elements.\n"
    "- safety: the geotechnical and safety team; plans ground support and the next "
    "drilling runs.\n"
    "- plant: the processing plant; plans for the rock and ore that will reach it.\n"
    "- finance: pays assays from the hole's budget by pricing the lab's request.\n"
    "Read the box, its runs, the trends along the hole and the hole agent's finding with "
    "your tools. Decide each area yourself from what you read; nothing is decided for "
    "you. Give one route per area, applies true or false, with a reason of one or two "
    "sentences that cites the runs, depths and numbers you read. Then call route_box."
)

AREA_ROLES: dict[AreaKey, str] = {
    "lab": "You are the lab agent. Draft an assay request: which intervals to sample, "
           "the tests (codes from price_list) and the priority. Use count_samples for "
           "the number of samples of each interval. Put each interval in intervals.",
    "safety": "You are the geotechnical and safety agent. Draft a ground-condition alert "
              "for the runs with poor or very poor rock or intense fracturing (Deere "
              "class, RQD, fracture frequency) and for the trends along the hole that "
              "reach this box (hole_trends), with the action the hole agent proposed "
              "(hole_finding) and what to check before the next run (support, scaling). "
              "Put every run number you quote in figures and the depths of this box you "
              "mention in intervals; depths outside this box go only in the body.",
    "plant": "You are the processing plant agent. Draft a short notice on the rock and "
             "ore coming (rock type, sulfides) and how it differs from the boxes above "
             "(hole_trends). Put the depths of this box you mention in intervals.",
    "finance": "You are the finance agent. Read the lab request, price it with quote "
               "and draft the cost and its effect on the hole's assay budget. Copy the "
               "lines and total from quote into lines and total_usd. Say the prices are "
               "an example table.",
}  # fmt: skip

AREA_TOOLS: dict[AreaKey, tuple[str, ...]] = {
    "lab": ("box_summary", "run_metrics", "count_samples", "price_list"),
    "safety": ("box_summary", "run_metrics", "hole_trends", "hole_finding", "hole_log"),
    "plant": ("box_summary", "hole_trends", "hole_history"),
    "finance": ("lab_request", "quote", "price_list"),
}
HOLE_TOOLS = ("hole_trends", "hole_log", "box_summary")
ORCHESTRATOR_TOOLS = ("box_summary", "run_metrics", "hole_trends", "hole_finding", "hole_log")

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


def _say(name: str, args: dict, result: object) -> str:
    """One tool call as a sentence for the decision log, without field names."""
    r = result if isinstance(result, dict) else {}
    if name == "lab_request" and "note" in r:
        return "Looked for a verified lab request: there is none yet"
    if name == "box_summary":
        runs = r.get("runs", [])
        worst = min(runs, key=lambda x: x["rqd_pct"]) if runs else None
        tail = f"; the worst is run {worst['run']}, RQD {worst['rqd_pct']} %" if worst else ""
        return f"Read the box from geometry.py: {len(runs)} runs{tail}"
    if name == "run_metrics":
        return (f"Read run {r['run']} ({r['from_m']:.2f} to {r['to_m']:.2f} m): RQD "
                f"{r['rqd_pct']} %, recovery {r['tcr_pct']} %, "
                f"{r['fracture_frequency_per_m']} fractures per metre, "
                f"{r['rock_quality_deere']} rock")  # fmt: skip
    if name == "hole_history":
        n = len(r.get("earlier_boxes", []))
        return f"Read the hole history: {n} earlier approved box{'es' if n != 1 else ''}"
    if name == "hole_log":
        n = len(r.get("boxes_in_log", []))
        zones = len(r.get("weak_zones", []))
        return (f"Read the hole log by depth: {n} approved box{'es' if n != 1 else ''}, "
                f"{zones} weak zone{'s' if zones != 1 else ''}")  # fmt: skip
    if name == "hole_trends":
        trends = r.get("trends", [])
        if not trends:
            return "Read the trends along the hole: none reaches this box"
        return "Read the trends along the hole: " + "; ".join(t["summary"] for t in trends)
    if name == "hole_finding":
        if "note" in r:
            return "Looked for the hole agent's finding: there is none verified"
        return f"Read the hole agent's finding: “{r['title']}”"
    if name == "count_samples":
        return (f"Counted {r['samples']} assay samples in {r['from_m']:.2f} to "
                f"{r['to_m']:.2f} m")  # fmt: skip
    if name == "price_list":
        return "Read the example price table and the hole's assay budget"
    if name == "quote":
        return (f"Priced {len(r.get('lines', []))} test lines: ${r['total_usd']:,.2f}, "
                f"${r['remaining_after_usd']:,.2f} left in the hole budget")  # fmt: skip
    if name == "lab_request":
        return "Read the verified lab request"
    return f"Used the {name.replace('_', ' ')} tool"


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
    effort: Effort | None = None,
) -> T:
    """Tool loop until the agent calls its submit tool with valid arguments.

    Only the listed tools and the submit tool exist for the agent: any other name is
    refused (a closed tool list). ``effort`` counts the model turns.
    """
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
        if effort is not None:
            effort.turns += 1
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
                log(actor, "tool", _say(name, args, result), model)
            except KeyError:
                result = {"error": f"unknown tool {name}"}
            except (ValueError, ValidationError) as exc:  # bad arguments: tell the model
                result = {"error": str(exc)[:400]}
                why = "bad arguments" if isinstance(exc, ValidationError) else str(exc)[:120]
                log(
                    actor,
                    "retry",
                    f"The {str(name).replace('_', ' ')} tool refused the call "
                    f"({why}); the agent tries again",
                    model,
                )
            history.append({"type": "function_call_output", "call_id": call["call_id"],
                            "output": json.dumps(result)})  # fmt: skip
    raise AgentError(f"{actor}: no valid {submit_name} after {MAX_TURNS} turns")


# verify.verify(area, draft, box, prices, history, trends)
Verifier = Callable[..., list[Check]]
# verify.check_finding(finding, trends, box, history)
FindingCheck = Callable[[HoleFinding, list[HoleTrend], BoxReview, list[BoxReview]], list[Check]]
# verify.check_routing(routing, signals)
RoutingCheck = Callable[[Routing, RoutingSignals], list[Check]]
# (what is judged, its text, the approved record, effort) -> verdict
Judge = Callable[[str, str, dict, Effort], JudgeVerdict]

ACTION_WORDS = {
    "oriented_core": "asking for oriented core in the next runs",
    "warn_geotech": "warning geotechnics before the next run",
    "sample_contact": "sampling across the contact",
    "none": "no action",
}

JUDGE_ROLE = (
    "You are the judge. Code already checked every number of the text below against "
    "geometry.py; do not recompute numbers. Your job is the words: check every factual "
    "statement the text makes about the rock, the core, the hole or its trends against "
    "the record the geologist approved. One claim per statement. For each, say whether "
    "the record backs it and cite where (the run and field, the trend, the geologist's "
    "comment), or say what is missing. A recommendation is judged only on what it "
    "asserts about the rock. A reading stated as possible (for example a possible fault "
    "zone) is backed when the record shows what it rests on (a weak zone, intense "
    "fracturing, a drop in RQD). Be strict: what the record does not state is not "
    "backed (for example 'visible sulfides' needs a description that shows sulfides). "
    "Then call submit_verdict."
)


def record_for_judge(toolbox: Toolbox, reason: str | None = None) -> dict:
    """What the judge compares against: the approved box, the hole and the verified steps."""
    runs = []
    for i, r in enumerate(toolbox.box.runs):
        d = r.description
        runs.append({
            **toolbox.run_metrics(RunArg(run=i + 1)),
            "lithology": d.lithology if d else None,
            "alteration": d.alteration if d else None,
            "mineralization": d.mineralization if d else None,
            "anomalies": [f"{a.type.value}: {a.explanation}" for a in d.anomalies] if d else [],
            "geologist_comment": r.comment,
        })  # fmt: skip
    record = {
        "box": {"hole_id": toolbox.box.hole_id, "box_number": toolbox.box.box_number,
                "runs": runs},
        "trends_found_by_code": [t.summary for t in toolbox.trends],
        "earlier_boxes": toolbox.hole_history(NoArg())["earlier_boxes"],
        "price_table_notice": toolbox.prices.notice,
    }  # fmt: skip
    if toolbox.finding is not None:
        record["hole_agent_finding"] = toolbox.finding.model_dump()
    if toolbox.lab_draft is not None:
        record["verified_lab_request"] = toolbox.lab_draft.model_dump()
    if reason:
        record["why_the_orchestrator_sent_it"] = reason
    return record


def spark_judge(client, log: Log) -> Judge:
    """Muse Spark as a judge, through the same closed tool loop (no tools, one submit)."""

    def judge(what: str, text: str, record: dict, effort: Effort) -> JudgeVerdict:
        facts = json.dumps(record, ensure_ascii=False)
        prompt = f"{JUDGE_ROLE}\n\nWhat you judge: {what}.\n\n{text}\n\nApproved record:\n{facts}"
        return run_agent(client, MUSE_SPARK_MODEL_ID, prompt, [], "submit_verdict",
                         "Submit one verdict per claim.", JudgeVerdict, log, "judge",
                         effort)  # fmt: skip

    return judge


@dataclass
class Attempt:
    result: BaseModel
    checks: list[Check]
    verdict: JudgeVerdict | None
    ok: bool


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _reasons(checks: list[Check], verdict: JudgeVerdict | None, judge_error: str | None):
    out = [c.detail or c.name for c in checks if not c.ok]
    if verdict is not None:
        out += [f"“{c.claim}” is not backed by the record: {c.evidence}"
                for c in verdict.claims if not c.supported]  # fmt: skip
    if judge_error:
        out.append(f"the judge could not run ({judge_error})")
    return out


def cost(label: str, e: Effort, judged: bool = True) -> str:
    """The cost of a verified result, as the decision log says it."""
    verifying = e.check_s + e.judge_s
    parts = f"{e.check_s:.2f} s code" + (f", {e.judge_s:.1f} s judge" if judged else "")
    return (f"{label}: {_plural(e.attempts, 'attempt')}, {_plural(e.turns, 'model turn')}, "
            f"{e.work_s:.1f} s writing and {verifying:.1f} s verifying ({parts})")  # fmt: skip


def two_layers(
    label: str,
    actor: str,
    model: str,
    write: Callable[[str], T],
    base: str,
    check: Callable[[T], list[Check]],
    text_of: Callable[[T], str],
    judge: Judge,
    record: Callable[[], dict],
    effort: Effort,
    log: Log,
    keep: Callable[[Attempt], None],
) -> str | None:
    """Write, check with code, then judge; at most MAX_ATTEMPTS. None when it passed,
    else why it needs a person. The judge only runs when every check passed, so it
    never passes what verify.py rejected."""
    prompt, reasons = base, []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        effort.attempts = attempt
        t = time.monotonic()
        result = write(prompt)
        effort.work_s += time.monotonic() - t
        t = time.monotonic()
        checks = check(result)
        effort.check_s += time.monotonic() - t
        failed = [c for c in checks if not c.ok]
        log("verifier", "check", f"{label}, attempt {attempt}: {len(checks) - len(failed)} of "
            f"{len(checks)} checks passed" + (": " + "; ".join(c.detail for c in failed)
                                               if failed else ""))  # fmt: skip
        verdict, judge_error = None, None
        if not failed:
            t = time.monotonic()
            try:
                verdict = judge(label, text_of(result), record(), effort)
            except Exception as exc:  # the judge is a model call: say so, do not pass
                judge_error = f"{type(exc).__name__}: {str(exc)[:160]}"
                log("judge", "error", f"{label}: the judge could not run ({judge_error})",
                    MUSE_SPARK_MODEL_ID)  # fmt: skip
            effort.judge_s += time.monotonic() - t
            if verdict is not None:
                bad = [c for c in verdict.claims if not c.supported]
                n = len(verdict.claims)
                log("judge", "judge", f"{label}: {n - len(bad)} of {_plural(n, 'claim')} backed "
                    "by the approved record" + (": " + "; ".join(
                        f"“{c.claim}”, {c.evidence}" for c in bad) if bad else ""),
                    MUSE_SPARK_MODEL_ID)  # fmt: skip
        ok = not failed and verdict is not None and verdict.ok
        keep(Attempt(result, checks, verdict, ok))
        if ok:
            return None
        reasons = _reasons(checks, verdict, judge_error)
        if attempt < MAX_ATTEMPTS:
            log(actor, "retry", f"Attempt {attempt} sent back with "
                f"{_plural(len(reasons), 'reason')} to fix", model)  # fmt: skip
            notes = "\n".join(f"- {r}" for r in reasons)
            prompt = (f"{base}\n\nYour previous attempt failed verification. Fix these "
                      f"points and submit again:\n{notes}")  # fmt: skip
    why = f"Needs review: {MAX_ATTEMPTS} attempts failed. " + "; ".join(reasons)
    log(actor, "escalate", why, model)
    return why


def run_hole_agent(
    client, toolbox: Toolbox, finding_check: FindingCheck, judge: Judge, log: Log,
    report: HoleReport, save: Callable[[], None],
) -> None:  # fmt: skip
    """The hole agent reads code's trends and proposes one action, verified in two layers."""
    tools = [toolbox.tools()[n] for n in HOLE_TOOLS]

    def write(prompt: str) -> HoleFinding:
        f = run_agent(client, report.model, prompt, tools, "submit_finding",
                      "Submit the trends you rely on and the action you propose.",
                      HoleFinding, log, "hole", report.effort)  # fmt: skip
        log("hole", "finding", f"“{f.title}”, proposing {ACTION_WORDS[f.action]}", report.model)
        return f

    def keep(a: Attempt) -> None:
        report.finding, report.checks, report.judge, report.verified = (
            a.result, a.checks, a.verdict, a.ok)  # fmt: skip
        save()

    def text_of(f: HoleFinding) -> str:
        return (f"Title: {f.title}\n{f.body}\nProposed action: {ACTION_WORDS[f.action]}. "
                f"{f.action_reason}")  # fmt: skip

    report.escalation = two_layers(
        "Hole finding", "hole", report.model, write, f"{COMMON}\n\n{HOLE_ROLE}",
        lambda f: finding_check(f, toolbox.trends, toolbox.box, toolbox.history),
        text_of, judge, lambda: record_for_judge(toolbox), report.effort, log, keep,
    )  # fmt: skip
    report.status = "ready" if report.verified else "needs_review"
    if report.verified:
        toolbox.finding = report.finding


def route_once(client, toolbox: Toolbox, prompt: str, log: Log, effort: Effort):
    """Muse Wonder decides; if it fails, Muse Spark 1.3 does the same job."""
    tools = [toolbox.tools()[n] for n in ORCHESTRATOR_TOOLS]
    for model in (MUSE_WONDER_MODEL_ID, MUSE_SPARK_MODEL_ID):
        log("orchestrator", "model", f"{model} is reading the box and the hole", model)
        try:
            routing = run_agent(client, model, prompt, tools, "route_box",
                                "Submit the decision for every area.", Routing, log,
                                "orchestrator", effort)  # fmt: skip
        except Exception as exc:  # Wonder is in preview: fall back, say so
            log("orchestrator", "error", f"{model} failed: {str(exc)[:200]}", model)
            continue
        return routing, model
    raise AgentError("Neither Muse Wonder nor Muse Spark produced a routing.")


def route(
    client, toolbox: Toolbox, signals: RoutingSignals, routing_check: RoutingCheck, log: Log,
    handoffs: Handoffs,
) -> bool:  # fmt: skip
    """The orchestrator routes; code checks the routing before any area agent writes."""
    base, effort = f"{COMMON}\n\n{ORCHESTRATOR}", handoffs.routing_effort
    prompt, reasons = base, []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        effort.attempts = attempt
        t = time.monotonic()
        routing, model = route_once(client, toolbox, prompt, log, effort)
        effort.work_s += time.monotonic() - t
        handoffs.routing, handoffs.orchestrator_model = routing, model
        for r in routing.routes:
            verdict = "applies" if r.applies else "does not apply"
            log("orchestrator", "route", f"{AREA_NAMES[r.area]} {verdict}: {r.reason}", model)
        t = time.monotonic()
        checks = routing_check(routing, signals)
        effort.check_s += time.monotonic() - t
        handoffs.routing_checks = checks
        failed = [c for c in checks if not c.ok]
        log("verifier", "check", f"Routing, attempt {attempt}: {len(checks) - len(failed)} of "
            f"{len(checks)} areas agree with the record" + (": " + "; ".join(
                c.detail for c in failed) if failed else ""))  # fmt: skip
        if not failed:
            handoffs.routing_verified = True
            return True
        reasons = [c.detail for c in failed]
        if attempt < MAX_ATTEMPTS:
            log("orchestrator", "retry", f"Routing sent back with "
                f"{_plural(len(reasons), 'reason')} to weigh", model)  # fmt: skip
            notes = "\n".join(f"- {r}" for r in reasons)
            prompt = (f"{base}\n\nCode checked your previous routing against the approved "
                      f"record and refused it:\n{notes}\nRoute again.")  # fmt: skip
    handoffs.routing_verified = False
    handoffs.escalation = (f"Routing needs review: {MAX_ATTEMPTS} attempts failed. "
                           + "; ".join(reasons))  # fmt: skip
    log("orchestrator", "escalate", handoffs.escalation, handoffs.orchestrator_model)
    return False


def write_draft(
    client, area: AreaKey, toolbox: Toolbox, reason: str, verifier: Verifier, judge: Judge,
    log: Log, slot: AreaDraft, save: Callable[[], None],
) -> None:  # fmt: skip
    """One area agent: draft, then verify.py and the judge, at most three attempts."""
    tools = [toolbox.tools()[n] for n in AREA_TOOLS[area]]
    base = f"{COMMON}\n\n{AREA_ROLES[area]}\n\nWhy the orchestrator sent you this box: {reason}"

    def write(prompt: str) -> Draft:
        d = run_agent(client, slot.model, prompt, tools, "submit_draft", "Submit your draft.",
                      Draft, log, area, slot.effort)  # fmt: skip
        log(area, "draft", f"“{d.title}”", slot.model)
        return d

    def keep(a: Attempt) -> None:
        slot.draft, slot.checks, slot.judge, slot.verified = a.result, a.checks, a.verdict, a.ok
        save()

    slot.escalation = two_layers(
        f"{AREA_NAMES[area]} draft", area, slot.model, write, base,
        lambda d: verifier(area, d, toolbox.box, toolbox.prices, toolbox.history,
                           toolbox.trends),
        lambda d: f"Title: {d.title}\n{d.body}", judge,
        lambda: record_for_judge(toolbox, reason), slot.effort, log, keep,
    )  # fmt: skip
    slot.status = "ready" if slot.verified else "needs_review"
    save()


def draft_handoffs(
    box: BoxReview,
    history: list[BoxReview],
    client,
    verifier: Verifier,
    prices: Prices | None = None,
    save: Callable[[Handoffs], None] = lambda h: None,
    *,
    judge: Judge | None = None,
    finding_check: FindingCheck | None = None,
    routing_check: RoutingCheck | None = None,
) -> Handoffs:
    """Hole agent, routing and drafts for an approved box. Saves after every step."""
    if finding_check is None or routing_check is None:
        from coresight import verify  # verify.py imports this module

        finding_check = finding_check or verify.check_finding
        routing_check = routing_check or verify.check_routing
    handoffs = Handoffs()
    persist = lambda: save(handoffs)  # noqa: E731
    log = Log(handoffs, persist)
    toolbox = Toolbox(box, history, prices or load_prices())
    judge = judge or spark_judge(client, log)
    try:
        report = HoleReport(model=MUSE_SPARK_MODEL_ID, trends=toolbox.trends)
        handoffs.hole = report
        handoffs.signals = hole.routing_signals(history, box, toolbox.trends)
        found = "; ".join(t.summary for t in toolbox.trends)
        log("hole", "model", f"Code found {_plural(len(toolbox.trends), 'trend')} along the "
            f"hole{': ' + found if found else ''}. The hole agent is reading them",
            report.model)  # fmt: skip
        try:
            run_hole_agent(client, toolbox, finding_check, judge, log, report, persist)
        except Exception as exc:
            report.status, report.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
            log("hole", "error", report.error, report.model)
        if report.effort.attempts:
            log("hole", "cost", cost("Hole agent", report.effort), report.model)
        routed = route(client, toolbox, handoffs.signals, routing_check, log, handoffs)
        log("orchestrator", "cost", cost("Routing", handoffs.routing_effort, judged=False),
            handoffs.orchestrator_model)  # fmt: skip
        if not routed:
            handoffs.status = "done"
            persist()
            return handoffs
        applies = {r.area: r for r in handoffs.routing.routes if r.applies}
        for area in AREAS:
            if area not in applies:
                continue
            if area == "finance" and toolbox.lab_draft is None:
                log("finance", "error", "Skipped: there is no verified lab request to price")
                continue
            slot = AreaDraft(area=area, model=MUSE_SPARK_MODEL_ID)
            handoffs.drafts.append(slot)
            persist()
            try:
                write_draft(client, area, toolbox, applies[area].reason, verifier, judge, log,
                            slot, persist)  # fmt: skip
            except Exception as exc:
                slot.status, slot.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
                log(area, "error", slot.error, slot.model)
            if slot.effort.attempts:
                log(area, "cost", cost(f"{AREA_NAMES[area]} agent", slot.effort), slot.model)
            if area == "lab" and slot.verified:
                toolbox.lab_draft = slot.draft
        handoffs.status = "done"
    except Exception as exc:
        handoffs.status, handoffs.error = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
    persist()
    return handoffs


def approve_draft(box: BoxReview, area: AreaKey, override: bool = False) -> AreaDraft:
    """A person approves one draft. It is marked approved; nothing is sent.

    A draft that failed verification three times reaches the person marked with why;
    they may still approve it, but only explicitly (``override``), and the log says so.
    """
    slot = next((d for d in box.handoffs.drafts if d.area == area), None) if box.handoffs else None
    if slot is None:
        raise ValueError(f"There is no {area} draft for this box.")
    if slot.status == "needs_review":
        if not override:
            raise ValueError("This draft failed verification three times. Read why, then "
                             "approve it explicitly if it is right.")  # fmt: skip
    elif slot.status != "ready" or not slot.verified:
        raise ValueError("Only a draft that passed every check can be approved.")
    now = datetime.now(UTC)
    over = slot.status == "needs_review"
    slot.status, slot.approved_at, slot.approved_over_checks = "approved", now, over
    what = (f"{AREA_NAMES[area]} draft approved by the geologist although it failed "
            "verification" if over else f"{AREA_NAMES[area]} draft approved")  # fmt: skip
    box.handoffs.log.append(AgentEvent(at=now, actor="geologist", kind="approve",
        text=f"{what}. Not sent: CoreSight has no outbound channel; the area receives it "
             "through the mine's own process."))  # fmt: skip
    return slot
