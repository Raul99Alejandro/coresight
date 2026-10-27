"""The only module that talks to Meta Model API.

Endpoints, model IDs and request shapes come from the official docs
(https://dev.meta.ai/docs/, read 2026-10-25): sam/segmenting,
sam/reading-segmentation, image-understanding and structured-output; voice
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
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv
from meta_sam_parser import CompletedOutcome, decode_mask_to_raster, image_segmentation_format

from coresight.describe import cached_description, describe_prompt
from coresight.schemas import GeologyDescription, ModelDescription, Transcript, TrayCheck

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
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=180,
            transport=transport,
        )

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

        return cached_description(
            self.cache_dir, self.model, prompt, image_png, lambda: self._with_retries(call)
        )

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

    def respond(self, body: dict) -> dict:
        """One Responses API turn with function tools (the area agents).

        The agents send the whole conversation every turn (no
        previous_response_id), so the same box asks the same questions and the
        answers are cached by a hash of the request: a sample box is paid once.
        """
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / "responses" / f"{key}.json" if self.cache_dir else None
        if path and path.exists():
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
