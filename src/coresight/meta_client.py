"""The only module that talks to Meta Model API.

Endpoints, model IDs and request shapes come from the official docs
(https://dev.meta.ai/docs/, read 2026-10-25): sam/segmenting,
sam/reading-segmentation, image-understanding (with perception grounding, read 2026-10-28) and
structured-output; voice
from speech-to-text, api-reference/voice/transcribe and voice/schemas (read
2026-10-26); agents from overview (muse-wonder-1.0 takes the same requests
as Muse Spark) and tool-calling (Responses API function tools, read
2026-10-27).
Confirmed against the real API by the day 1 smoke test (scripts/smoke_day1.py).

SAM responses are cached on disk by a hash of model, prompt and image, so the
same row is never paid for twice, and transient failures (timeouts, 429, 5xx)
are retried with exponential backoff.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

from coresight.describe import cached_description, describe_prompt
from coresight.schemas import (
    GeologyDescription,
    ModelDescription,
    RowLocation,
    Transcript,
    TrayCheck,
)

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
SAM_MODEL_ID = "sam-3.1"
MUSE_SPARK_MODEL_ID = "muse-spark-1.3"
MUSE_WONDER_MODEL_ID = "muse-wonder-1.0"  # in preview (docs: overview)
RESPONSES_PATH = "/responses"
VOICE_MODEL_ID = "muse-voice-transcribe-1.0"
TRANSCRIBE_PATH = "/asr/transcribe"
VOICE_LANGUAGES = ["Spanish", "English"]  # a hint, not a hard setting (docs: languageBias)
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
TRAY_CHECK_PROMPT = """\
You are the first check of a drill-core logging system. Look at the whole photo.
Is it a photo of a drill core tray (a core box): a tray with several parallel rows
of rock core, taken from above? Answer is_core_tray false for anything else, for
example a screenshot of software or a web page, a person or a selfie, a document,
a landscape, or one or two pieces of core held or laid out without a tray.
what_it_shows: what the photo shows, in a few words. confidence: how sure you are
of is_core_tray, from 0 to 1."""

# Grounding prompt (docs: image-understanding, "Perception grounding"): boxes in a
# 0 to 1000 grid of the image sent, x first; "object grounding expert" and "do not
# miss" are the docs' advice for recall.
LOCATE_PROMPT = """\
You are an object grounding expert. This image is one row of a drill core tray seen
from above: pieces of rock core lie end to end along the row, from left to right,
between two wooden slats. Find every object lying in the row and give each one a
tight bounding box in a 0 to 1000 grid of this image: (0, 0) is the top left corner
and (1000, 1000) the bottom right, x from left to right, y from top to bottom.
kind of each object:
- core: one piece of rock core. Where the core is broken, give each piece its own
  box. Include short pieces and rubble.
- run_block: a block that marks the end of a drilling run (wood or foam, often with
  a depth written on it).
- card: a card, tag or label.
- waxed_sample: core wrapped in wax, foil or plastic, taken as a sample.
- other: anything else in the row that is not rock core (a bag, a tool, a spacer).
Do not box the slats, the tray walls or empty tray. Do not miss any piece."""

# One SAM record: "<id><|box;...|><|mask;...;data=H,W,ENC payload|>" (docs:
# sam/reading-segmentation). The box token has no payload, so records are found
# by their box; the base85 mask payload can itself contain "|", ">" and ",".
_RECORD_START = re.compile(r"(\d+)<\|box;([^|]*)\|><\|mask;")


def _data_url(image_png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_png).decode("ascii")


def _fields(token_body: str) -> dict[str, str]:
    """'x1=1;y1=2;data=27,60,~abc' -> {'x1': '1', 'y1': '2', 'data': '27,60,~abc'}."""
    out = {}
    for part in token_body.split(";"):
        key, _, value = part.partition("=")
        out[key] = value
    return out


def parse_sam_text(text: str) -> list[dict]:
    """Records of a single-image SAM response, masks left encoded.

    Each record: {"id", "box": {x1, y1, x2, y2, w, h[, c]}, "mask": "H,W,ENC payload"}.
    Use sam_masks() for the decoded rasters.
    """
    starts = list(_RECORD_START.finditer(text))
    records = []
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        mask_body = text[match.end() : end].rstrip().removesuffix(",").removesuffix("|>")
        _, _, data = mask_body.partition("data=")
        box = {k: float(v) for k, v in _fields(match.group(2)).items()}
        records.append({"id": int(match.group(1)), "box": box, "mask": data})
    return records


def sam_masks(text: str) -> list[dict]:
    """Decoded masks of a single-image SAM response, via the official meta_sam_parser.

    Each mask comes cropped to its object's bounds. Returns one dict per object:
    {"id", "bounds": (left, top, right, bottom), "confidence", "mask"} where "mask"
    is a bool array of shape (bottom - top, right - left) in source pixels.
    """
    parser = image_segmentation_format().create_parser()
    parser.push(text)
    result = parser.finish(CompletedOutcome()).result
    out = []
    for record in result.records:
        if record.kind != "mask":
            continue
        m, b = record.mask, record.bounds
        raster = np.frombuffer(decode_mask_to_raster(m), dtype=np.uint8)
        raster = raster.reshape(m.height, m.width)
        size = (b.right - b.left, b.bottom - b.top)
        if raster.shape[::-1] != size:
            raster = cv2.resize(raster, size, interpolation=cv2.INTER_NEAREST)
        out.append(
            {
                "id": int(record.object_id),
                "bounds": (b.left, b.top, b.right, b.bottom),
                "confidence": record.confidence,
                "mask": raster > 0,
            }
        )
    return out


MAX_SAM_OBJECTS = 16  # objects per box and point prompt (docs: sam/segmenting)


@dataclass(frozen=True)
class SamPoint:
    """A point prompt in pixels of the image sent; negative means "not this object"."""

    x: float
    y: float
    positive: bool = True


@dataclass(frozen=True)
class SamObject:
    """One object of a box and point prompt: our id, at most one box, then its points.

    box is (x1, y1, x2, y2) in pixels of the image sent, x2 and y2 inclusive.
    SAM answers under the same id, so each mask can be tied back to its prompt.
    """

    id: int
    box: tuple[float, float, float, float] | None = None
    points: tuple[SamPoint, ...] = ()


def _prompt_image_size(size: tuple[int, int]) -> tuple[int, int]:
    """(w, h) checked to be positive whole pixels."""
    try:
        w, h = size
    except (TypeError, ValueError):
        raise ValueError(f"image size must be (w, h), got {size!r}") from None
    for n in (w, h):
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise ValueError(f"image size must be positive whole pixels, got {size!r}")
    return w, h


def _prompt_pixel(value: float, what: str) -> int:
    """A prompt coordinate floored to a whole pixel, as the API does."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a number, got {value!r}")
    try:
        return int(value // 1)
    except (OverflowError, ValueError):
        raise ValueError(f"{what} out of range: {value!r}") from None


def _grid_pixel(value: float, n: int) -> int:
    """A 0 to 1000 grid coordinate as a clamped pixel of a side ``n``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"grid coordinate must be a number, got {value!r}")
    try:
        pixel = int(value * n // 1000)  # 1000 scales to n, clamped to n - 1 below
    except (OverflowError, ValueError):
        raise ValueError(f"grid coordinate out of range: {value!r}") from None
    return max(0, min(pixel, n - 1))


def sam_prompt(objects: Sequence[SamObject], size: tuple[int, int]) -> str:
    """The input_text of a SAM 3.1 box and point prompt for one image of ``size`` (w, h).

    Raises ValueError when the API would refuse it. Spec: tests/test_sam_prompts.py.
    """
    w, h = _prompt_image_size(size)
    if not objects:
        raise ValueError("at least one object")
    if len(objects) > MAX_SAM_OBJECTS:
        raise ValueError(f"at most {MAX_SAM_OBJECTS} objects, got {len(objects)}")
    seen = set()
    rendered = []
    for obj in objects:
        if isinstance(obj.id, bool) or not isinstance(obj.id, int) or obj.id < 0:
            raise ValueError(f"object id must be a whole number from 0, got {obj.id!r}")
        if obj.id in seen:
            raise ValueError(f"duplicate object id {obj.id}")
        seen.add(obj.id)
        if obj.box is None and not any(p.positive for p in obj.points):
            raise ValueError(f"object {obj.id} needs a box or a positive point")
        chunk = [str(obj.id)]
        if obj.box is not None:
            try:
                bx1, by1, bx2, by2 = obj.box
            except (TypeError, ValueError):
                raise ValueError(f"object {obj.id} box must be (x1, y1, x2, y2)") from None
            what = f"object {obj.id} box"
            x1 = _prompt_pixel(bx1, what)
            y1 = _prompt_pixel(by1, what)
            x2 = _prompt_pixel(bx2, what)
            y2 = _prompt_pixel(by2, what)
            if not (0 <= x1 <= x2 < w and 0 <= y1 <= y2 < h):
                raise ValueError(f"object {obj.id} box {(x1, y1, x2, y2)} outside {w}x{h}")
            chunk.append(f"<|box;x1={x1};y1={y1};x2={x2};y2={y2};w={w};h={h}|>")
        for point in obj.points:
            what = f"object {obj.id} point"
            x = _prompt_pixel(point.x, what)
            y = _prompt_pixel(point.y, what)
            if not (0 <= x < w and 0 <= y < h):
                raise ValueError(f"object {obj.id} point {(x, y)} outside {w}x{h}")
            if not point.positive:
                chunk.append("-")
            chunk.append(f"<|point;x={x};y={y};w={w};h={h}|>")
        rendered.append("".join(chunk))
    return "<0f>" + ",".join(rendered)


def grid_box_to_pixels(
    box: tuple[float, float, float, float], size: tuple[int, int]
) -> tuple[int, int, int, int]:
    """A Muse Spark box in the 0 to 1000 grid as an inclusive pixel box of the image sent.

    Spec: tests/test_sam_prompts.py.
    """
    w, h = _prompt_image_size(size)
    try:
        gx1, gy1, gx2, gy2 = box
    except (TypeError, ValueError):
        raise ValueError(f"grid box must be (x1, y1, x2, y2), got {box!r}") from None
    x1 = _grid_pixel(gx1, w)
    y1 = _grid_pixel(gy1, h)
    x2 = _grid_pixel(gx2, w)
    y2 = _grid_pixel(gy2, h)
    # A backwards box is put in order, so the result is always a valid prompt.
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def _output_text(response: dict) -> str:
    """Concatenate the output_text parts of a non-streaming /responses result."""
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


class TransientAPIError(RuntimeError):
    """A failure worth retrying: timeout, rate limit or server error."""


def sam_cache_key(image_png: bytes, prompt: str) -> str:
    h = hashlib.sha256()
    for part in (SAM_MODEL_ID.encode(), b"\0", prompt.encode(), b"\0", image_png):
        h.update(part)
    return h.hexdigest()


class UsageLog:
    """Every request to Meta Model API and every answer read from the cache instead.

    One JSON line each in ``<cache_dir>/usage.jsonl`` (the cache volume in
    production), read by the credit watch (GET /api/ops/usage). Only the model,
    the status, the seconds and the tokens: never a prompt, an image or the key.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def add(self, model: str, **fields) -> None:
        entry = {"at": round(time.time(), 1), "model": model, **fields}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:  # a line cut by a crash: skip it
                continue
        return out


def usage_summary(entries: list[dict], now: float | None = None) -> dict:
    """Calls, cache hits, errors, tokens and seconds per model, last hour / 24 h / all."""
    now = time.time() if now is None else now
    windows = {"hour": 3600, "day": 86400, "all": float("inf")}
    out: dict = {}
    for name, span in windows.items():
        models: dict = {}
        for e in entries:
            if now - e["at"] > span:
                continue
            m = models.setdefault(e["model"], {"calls": 0, "cached": 0, "errors": 0,
                                               "rate_limited": 0, "input_tokens": 0,
                                               "output_tokens": 0, "seconds": 0.0})  # fmt: skip
            if e.get("cached"):
                m["cached"] += 1
                continue
            m["calls"] += 1
            status = e.get("status", 200)
            m["errors"] += status >= 400
            m["rate_limited"] += status == 429
            m["input_tokens"] += e.get("input_tokens") or 0
            m["output_tokens"] += e.get("output_tokens") or 0
            m["seconds"] = round(m["seconds"] + (e.get("seconds") or 0), 1)
        out[name] = models
    return out


def _request_model(request: httpx.Request) -> str:
    if request.url.path.endswith(TRANSCRIBE_PATH):
        return VOICE_MODEL_ID
    try:
        return json.loads(request.content).get("model", "unknown")
    except (ValueError, AttributeError):
        return "unknown"


class MetaClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        max_retries: int = 4,
        backoff_s: float = 2.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("META_API_KEY")
        self.base_url = (base_url or os.getenv("META_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        if not self.api_key:
            raise RuntimeError("META_API_KEY must be set in .env")
        self.usage = UsageLog(Path(cache_dir) / "usage.jsonl") if cache_dir else None
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=180,
            transport=transport,
            event_hooks={"request": [self._started], "response": [self._answered]},
        )

    def _started(self, request: httpx.Request) -> None:
        request.extensions["coresight_t0"] = time.perf_counter()

    def _answered(self, response: httpx.Response) -> None:
        """The credit watch: one line per request that reached the API."""
        if self.usage is None:
            return
        request = response.request
        model = _request_model(request)
        tokens: dict = {}
        if model != SAM_MODEL_ID and response.status_code < 400:  # SAM streams: no body yet
            response.read()
            try:
                usage = response.json().get("usage") or {}
                tokens = {k: usage.get(k) for k in ("input_tokens", "output_tokens")}
            except (ValueError, AttributeError):
                pass
        t0 = request.extensions.get("coresight_t0")
        seconds = round(time.perf_counter() - t0, 2) if t0 else None
        self.usage.add(model, status=response.status_code, seconds=seconds, **tokens)

    def cache_hit(self, model: str) -> None:
        """An answer read from the cache instead of the API (also SAM's decoded masks)."""
        if self.usage is not None:
            self.usage.add(model, cached=True)

    def _with_retries(self, call: Callable[[], str]) -> str:
        """Run ``call``; on a transient failure wait backoff_s * 2**attempt and retry."""
        for attempt in range(self.max_retries + 1):
            try:
                return call()
            except (TransientAPIError, httpx.TimeoutException, httpx.TransportError):
                if attempt == self.max_retries:
                    raise
                self._sleep(self.backoff_s * 2**attempt)
        raise AssertionError("unreachable")

    def segment_row(self, image_png: bytes, prompt: str) -> list[dict]:
        """SAM 3.1: one record per object matching a short noun-phrase prompt."""
        return parse_sam_text(self.segment_row_raw(image_png, prompt))

    def segment_row_raw(self, image_png: bytes, prompt: str) -> str:
        """SAM 3.1 raw output text: from the cache, or from the API and then cached."""
        path = None
        if self.cache_dir is not None:
            path = Path(self.cache_dir) / "sam" / f"{sam_cache_key(image_png, prompt)}.txt"
            if path.exists():
                self.cache_hit(SAM_MODEL_ID)
                return path.read_text(encoding="utf-8")
        text = self._with_retries(lambda: self._sam_request(image_png, prompt))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return text

    def _sam_request(self, image_png: bytes, prompt: str) -> str:
        """One streamed SAM 3.1 call, as the docs recommend."""
        body = {
            "model": SAM_MODEL_ID,
            "stream": True,
            "metadata": {"include_confidence": "true"},
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": _data_url(image_png)},
                    ],
                }
            ],
        }
        chunks = []
        with self._http.stream("POST", RESPONSES_PATH, json=body) as resp:
            if resp.status_code >= 400:
                resp.read()
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"SAM {resp.status_code}: {resp.text}")
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload or payload == "[DONE]":
                    continue
                event = json.loads(payload)
                if event.get("type") == "response.output_text.delta":
                    chunks.append(event.get("delta", ""))
        return "".join(chunks)

    model = MUSE_SPARK_MODEL_ID  # the describe backend (describe.Describer)

    def describe_interval(self, image_png: bytes, context: dict) -> GeologyDescription:
        """Muse Spark: lithology, alteration, mineralization and visible anomalies.

        The answer is constrained to ModelDescription (json_schema), validated
        and cached; rule anomalies are added later by coresight.anomalies.
        """
        prompt = describe_prompt(context)
        body = {
            "model": MUSE_SPARK_MODEL_ID,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": _data_url(image_png)},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "GeologyDescription",
                    "schema": ModelDescription.model_json_schema(),
                }
            },
        }

        def call() -> str:
            resp = self._http.post(RESPONSES_PATH, json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Muse Spark {resp.status_code}: {resp.text}")
            return _output_text(resp.json())

        fetched = []

        def fetch() -> str:
            fetched.append(True)
            return self._with_retries(call)

        description = cached_description(self.cache_dir, self.model, prompt, image_png, fetch)
        if not fetched:
            self.cache_hit(MUSE_SPARK_MODEL_ID)
        return description

    def check_tray(self, image_png: bytes) -> TrayCheck:
        """Muse Spark on the whole photo: is it a core tray at all? (the input gate).

        Same request as describe_interval with the TrayCheck schema; the answer
        is validated and cached by a hash of model, prompt and image.
        """
        name = hashlib.sha256(
            b"\0".join([MUSE_SPARK_MODEL_ID.encode(), TRAY_CHECK_PROMPT.encode(), image_png])
        ).hexdigest()
        path = self.cache_dir / "tray_check" / f"{name}.json" if self.cache_dir else None
        if path and path.exists():
            self.cache_hit(MUSE_SPARK_MODEL_ID)
            return TrayCheck.model_validate_json(path.read_text(encoding="utf-8"))
        body = {
            "model": MUSE_SPARK_MODEL_ID,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": TRAY_CHECK_PROMPT},
                        {"type": "input_image", "image_url": _data_url(image_png)},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "TrayCheck",
                    "schema": TrayCheck.model_json_schema(),
                }
            },
        }

        def call() -> str:
            resp = self._http.post(RESPONSES_PATH, json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Muse Spark {resp.status_code}: {resp.text}")
            return _output_text(resp.json())

        check = TrayCheck.model_validate_json(self._with_retries(call))
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(check.model_dump_json(indent=1), encoding="utf-8")
        return check

    def locate_row(self, image_png: bytes) -> RowLocation:
        """Muse Spark localizes the core pieces of one row and what is not core (point B).

        Grounding with structured output, as the docs recommend: the boxes come back
        as schemas.RowLocation (0 to 1000 grid of the image sent), validated and
        cached by a hash of model, prompt and image.
        """
        name = hashlib.sha256(
            b"\0".join([MUSE_SPARK_MODEL_ID.encode(), LOCATE_PROMPT.encode(), image_png])
        ).hexdigest()
        path = self.cache_dir / "locate" / f"{name}.json" if self.cache_dir else None
        if path and path.exists():
            self.cache_hit(MUSE_SPARK_MODEL_ID)
            return RowLocation.model_validate_json(path.read_text(encoding="utf-8"))
        body = {
            "model": MUSE_SPARK_MODEL_ID,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": LOCATE_PROMPT},
                        {"type": "input_image", "image_url": _data_url(image_png)},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "RowLocation",
                    "schema": RowLocation.model_json_schema(),
                }
            },
        }

        def call() -> str:
            resp = self._http.post(RESPONSES_PATH, json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Muse Spark {resp.status_code}: {resp.text}")
            return _output_text(resp.json())

        location = RowLocation.model_validate_json(self._with_retries(call))
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(location.model_dump_json(indent=1), encoding="utf-8")
        return location

    def respond(self, body: dict) -> dict:
        """One Responses API turn with function tools (the area agents).

        The agents send the whole conversation every turn (no
        previous_response_id), so the same box asks the same questions and the
        answers are cached by a hash of the request: a sample box is paid once.
        """
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / "responses" / f"{key}.json" if self.cache_dir else None
        if path and path.exists():
            self.cache_hit(body.get("model", "unknown"))
            return json.loads(path.read_text(encoding="utf-8"))

        def call() -> str:
            resp = self._http.post(RESPONSES_PATH, json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"{body.get('model')} {resp.status_code}: {resp.text}")
            return resp.text

        text = self._with_retries(call)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return json.loads(text)

    def transcribe(self, wav: bytes, keywords: list[str] | None = None) -> Transcript:
        """Muse Voice Transcribe: one push-to-talk clip (mono 16-bit PCM WAV) to text.

        Not cached: every dictation is new. 429 and 5xx are retried.
        """
        request = {
            "model": VOICE_MODEL_ID,
            "audioEncoding": "WAV",
            "mode": "PUSH_TO_TALK",
            "languageBias": VOICE_LANGUAGES,
        }
        if keywords:
            request["keywords"] = keywords

        def call() -> str:
            resp = self._http.post(
                TRANSCRIBE_PATH,
                headers={"Accept": "application/json"},
                files={
                    "request": (None, json.dumps(request), "application/json"),
                    "audio": ("dictation.wav", wav, "audio/wav"),
                },
            )
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Muse Voice Transcribe {resp.status_code}: {resp.text}")
            return resp.text

        return Transcript.model_validate_json(self._with_retries(call))
