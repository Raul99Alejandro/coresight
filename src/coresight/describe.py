"""Stage 4 helpers shared by every describe backend.

- ``describe_prompt``: the one prompt Muse Spark and Glimmer both get.
- ``Describer``: the contract a backend meets (meta_client.MetaClient and
  glimmer_client.GlimmerClient): image + context in, validated
  GeologyDescription out.
- ``png_bytes``: the image a backend gets, at most MAX_SIDE_PX on its longest side.

The crop of each run comes from coresight.crops.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from coresight.schemas import GeologyDescription, ModelDescription

MAX_SIDE_PX = 1568  # longest side sent to a model; more costs tokens, not detail

PROMPT = """\
You are a core logging geologist. The image shows drill core from one drilling run, \
photographed in a core tray. When the run fills several tray rows, the rows are stacked \
top to bottom in reading order, separated by a dark band. Describe only what is visible.

- lithology: standard rock name, colour, grain size, texture and fabric.
- alteration: type and intensity (none, weak, moderate, strong, pervasive), for example \
chloritic, sericitic, silicified, potassic, carbonate, oxidised. Write "none visible" if none.
- mineralization: visible sulfides or ore minerals (pyrite, chalcopyrite, pyrrhotite, \
sphalerite, galena, ...), their style (disseminated, veinlets, blebs, semi-massive, massive) \
and an estimated volume percent. Write "none visible" if none.
- anomalies: "visible_sulfides" when sulfides can be seen, with where and how much; \
"other" for anything else a geologist should check (fault gouge, a lithology contact, \
broken or missing core, a vein). One sentence each. Leave the list empty if there is nothing.
- confidence: from 0 to 1, how sure you are given the photo quality and resolution.

Core recovery, fracture counts and RQD are measured separately from the photo geometry: \
do not estimate them. Answer in English.
"""


def describe_prompt(context: dict) -> str:
    return PROMPT + "\nContext: " + json.dumps(context, ensure_ascii=False)


class Describer(Protocol):
    model: str

    def describe_interval(self, image_png: bytes, context: dict) -> GeologyDescription: ...


def png_bytes(image: np.ndarray, max_side: int = MAX_SIDE_PX) -> bytes:
    """PNG of ``image``, shrunk so its longest side is at most ``max_side``."""
    scale = max_side / max(image.shape[:2])
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("could not encode the crop as PNG")
    return buf.tobytes()


def png_data_url(image_png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(image_png).decode("ascii")


def cache_key(model: str, prompt: str, image_png: bytes) -> str:
    """Name of a cached description: the same model, prompt and image are never paid twice."""
    h = hashlib.sha256()
    for part in (model.encode(), b"\0", prompt.encode(), b"\0", image_png):
        h.update(part)
    return h.hexdigest()


def cached_description(
    cache_dir: Path | None, model: str, prompt: str, image_png: bytes, fetch: Callable[[], str]
) -> GeologyDescription:
    """Validated description from the cache, or from ``fetch`` (raw JSON text) and then cached.

    Only answers that pass ModelDescription are written to the cache.
    """
    path = None
    if cache_dir is not None:
        name = cache_key(model, prompt, image_png)
        path = Path(cache_dir) / "describe" / model / f"{name}.json"
        if path.exists():
            return ModelDescription.model_validate_json(path.read_text("utf-8")).to_geology()
    raw = fetch()
    description = ModelDescription.model_validate_json(raw)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(description.model_dump_json(indent=1), encoding="utf-8")
    return description.to_geology()
