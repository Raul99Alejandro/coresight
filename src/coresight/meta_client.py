"""The only module that talks to Meta Model API.

Endpoints, model IDs and request shapes come from the official docs
(https://dev.meta.ai/docs/, read 2026-10-25): sam/segmenting,
sam/reading-segmentation, image-understanding and structured-output.
Not yet run against a real key: the day 1 smoke test
(scripts/smoke_day1.py) is what confirms them.
"""

from __future__ import annotations

import base64
import json
import os
import re

import httpx
from dotenv import load_dotenv

from coresight.schemas import GeologyDescription

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
SAM_MODEL_ID = "sam-3.1"
MUSE_SPARK_MODEL_ID = "muse-spark-1.3"
RESPONSES_PATH = "/responses"

# One SAM record: "<id><|box;...|><|mask;...|>" (docs: sam/reading-segmentation).
_RECORD = re.compile(r"(\d+)<\|box;([^|]*)\|><\|mask;([^|]*)\|>")


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
    Decoding the mask raster needs the official meta_sam_parser package.
    """
    records = []
    for obj_id, box_body, mask_body in _RECORD.findall(text):
        box = {k: float(v) for k, v in _fields(box_body).items()}
        mask = _fields(mask_body)
        records.append({"id": int(obj_id), "box": box, "mask": mask.get("data", "")})
    return records


def _output_text(response: dict) -> str:
    """Concatenate the output_text parts of a non-streaming /responses result."""
    parts = []
    for item in response.get("output", []):
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "".join(parts)


class MetaClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("META_API_KEY")
        self.base_url = (base_url or os.getenv("META_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        if not self.api_key:
            raise RuntimeError("META_API_KEY must be set in .env")
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=180,
        )

    def segment_row(self, image_png: bytes, prompt: str) -> list[dict]:
        """SAM 3.1: one record per object matching a short noun-phrase prompt.

        Day 4 adds caching by image hash and retries.
        """
        return parse_sam_text(self.segment_row_raw(image_png, prompt))

    def segment_row_raw(self, image_png: bytes, prompt: str) -> str:
        """SAM 3.1 raw output text, streamed as the docs recommend."""
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
                raise RuntimeError(f"SAM {resp.status_code}: {resp.text}")
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

    def describe_interval(self, image_png: bytes, context: dict) -> GeologyDescription:
        """Muse Spark: lithology, alteration, mineralization and anomalies.

        The raw response is validated with GeologyDescription before returning.
        Day 6: prompt tuning and anomaly rules.
        """
        prompt = (
            "You are a core logging geologist. Describe the drill core in this photo. "
            "Return lithology, alteration, mineralization, anomalies (only these types: "
            "low_recovery, intense_fracturing, visible_sulfides, other) and your confidence "
            "from 0 to 1. Do not compute RQD. Context: " + json.dumps(context)
        )
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
                    "schema": GeologyDescription.model_json_schema(),
                }
            },
        }
        resp = self._http.post(RESPONSES_PATH, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"Muse Spark {resp.status_code}: {resp.text}")
        return GeologyDescription.model_validate_json(_output_text(resp.json()))
