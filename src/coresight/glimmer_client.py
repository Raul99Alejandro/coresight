"""Muse Glimmer, Meta's open-weight model, on our own hardware (offline mode).

Same contract as MetaClient.describe_interval (describe.Describer): same
prompt, same ModelDescription schema, same validation and cache. Glimmer is
served by llama.cpp as the docs show (https://dev.meta.ai/docs/muse-glimmer/deploy,
read 2026-10-26): an OpenAI-compatible ``/v1/chat/completions`` with images as
``image_url`` data URLs. llama.cpp turns ``response_format`` json_schema into a
grammar, so the answer is valid JSON of that schema.

    llama-server -m Muse-Glimmer-30B-KQuant-17GB-Q4_K_M.gguf
        --mmproj mmproj-Muse-Glimmer-30B-Q4_K_M.gguf -a muse-glimmer
        -ngl <layers that fit the GPU> -c 16384 --host 127.0.0.1 --port 8080

No call here leaves the machine; nothing goes to Meta Model API.
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

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
GLIMMER_MODEL_ID = "muse-glimmer"  # the alias given to llama-server with -a


class GlimmerClient:
    model = GLIMMER_MODEL_ID

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_dir: Path | None = DEFAULT_CACHE_DIR,
        max_retries: int = 2,
        backoff_s: float = 5.0,
        timeout_s: float = 900,  # a 30B model partly on CPU takes minutes per run
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        load_dotenv()
        base_url = base_url or os.getenv("GLIMMER_BASE_URL") or DEFAULT_BASE_URL
        api_key = api_key or os.getenv("GLIMMER_API_KEY")
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s, transport=transport
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
            "model": GLIMMER_MODEL_ID,
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
            "temperature": 0.2,
        }

        def call() -> str:
            resp = self._http.post("/chat/completions", json=body)
            if resp.status_code >= 400:
                error = TransientAPIError if resp.status_code in RETRY_STATUS else RuntimeError
                raise error(f"Glimmer {resp.status_code}: {resp.text}")
            return resp.json()["choices"][0]["message"]["content"]

        return cached_description(
            self.cache_dir, self.model, prompt, image_png, lambda: self._with_retries(call)
        )
