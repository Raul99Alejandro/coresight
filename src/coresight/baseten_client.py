"""Muse Spark Open, Meta's open-weight model, served by Baseten Model APIs.

The only module that talks to Baseten. Same contract as
MetaClient.describe_interval (describe.Describer): same prompt, same
ModelDescription schema, same validation and cache.

From the Baseten docs (read 2026-10-27): docs.baseten.co/reference/inference-api/
chat-completions, inference/model-apis/vision and inference/model-apis/reasoning.

- OpenAI-compatible ``POST /chat/completions`` at https://inference.baseten.co/v1.
- Images go as ``image_url`` with a base64 data URL.
- ``response_format`` json_schema constrains the answer.
- The model always reasons: the reasoning comes in ``reasoning_content`` and
  the answer in ``content``; only ``content`` is parsed. Reasoning tokens are
  billed inside ``completion_tokens``.

The key works only with the model ID below (Baseten mail of 27 Oct), not the
``meta-models/muse-spark-open`` shown in their docs.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from dotenv import load_dotenv

from coresight.describe import cached_description, describe_prompt, png_data_url
from coresight.meta_client import DEFAULT_CACHE_DIR, RETRY_STATUS, TransientAPIError
from coresight.schemas import GeologyDescription, ModelDescription

DEFAULT_BASE_URL = "https://inference.baseten.co/v1"
MUSE_SPARK_OPEN_MODEL_ID = "meta-models/muse-spark-open-1026"
# USD per million tokens, baseten.co/pricing on 2026-10-27
PRICE_INPUT_PER_M = 1.25
PRICE_OUTPUT_PER_M = 4.25


def cost_usd(usage: dict) -> float:
    return (
        usage.get("prompt_tokens", 0) * PRICE_INPUT_PER_M
        + usage.get("completion_tokens", 0) * PRICE_OUTPUT_PER_M
    ) / 1e6


class BasetenClient:
    model = MUSE_SPARK_OPEN_MODEL_ID

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
        api_key = api_key or os.getenv("BASETEN_API_KEY")
        if not api_key:
            raise RuntimeError("BASETEN_API_KEY must be set in .env")
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        self.usage: list[dict] = []  # token usage of every paid call, oldest first
        self._http = httpx.Client(
            base_url=(base_url or DEFAULT_BASE_URL).rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300,
            transport=transport,
        )

    def _with_retries(self, call: Callable[[], str]) -> str:
        for attempt in range(self.max_retries + 1):
            try:
                return call()
            except (TransientAPIError, httpx.TimeoutException, httpx.TransportError):
                if attempt == self.max_retries:
                    raise
                self._sleep(self.backoff_s * 2**attempt)
        raise AssertionError("unreachable")

    def describe_interval(self, image_png: bytes, context: dict) -> GeologyDescription:
        prompt = describe_prompt(context)
        body = {
            "model": MUSE_SPARK_OPEN_MODEL_ID,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": png_data_url(image_png)}},
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "GeologyDescription",
                    "schema": ModelDescription.model_json_schema(),
                },
            },
        }

        def call() -> str:
            resp = self._http.post("/chat/completions", json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Baseten {resp.status_code}: {resp.text}")
            data = resp.json()
            if data.get("usage"):
                self.usage.append(data["usage"])
            return data["choices"][0]["message"]["content"]

        return cached_description(
            self.cache_dir, self.model, prompt, image_png, lambda: self._with_retries(call)
        )
