"""The only module that talks to Meta Model API.

Endpoints and model IDs are NOT hard-coded yet. Fill the TODOs from the
official docs (https://dev.meta.ai/docs/) once the API key is active (day 1).
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from coresight.schemas import GeologyDescription

# TODO(day 1): confirm against the official docs with a real key.
SAM_MODEL_ID: str | None = None
MUSE_SPARK_MODEL_ID: str | None = None
SEGMENT_PATH: str | None = None
DESCRIBE_PATH: str | None = None


class MetaClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("META_API_KEY")
        self.base_url = base_url or os.getenv("META_API_BASE_URL")
        if not self.api_key or not self.base_url:
            raise RuntimeError("META_API_KEY and META_API_BASE_URL must be set in .env")

    def segment_row(self, image_png: bytes, prompt: str) -> list[dict]:
        """SAM 3.1: masks of intact pieces and breaks in one core row.

        Day 1: smoke test with one photo. Day 4: production version with
        caching by image hash and retries.
        """
        raise NotImplementedError("day 1 (smoke test) / day 4 (segmentation)")

    def describe_interval(self, image_png: bytes, context: dict) -> GeologyDescription:
        """Muse Spark: lithology, alteration, mineralization and anomalies.

        The raw response is validated with GeologyDescription before returning.
        Day 1: smoke test. Day 6: structured output and anomaly flags.
        """
        raise NotImplementedError("day 1 (smoke test) / day 6 (descriptions)")
