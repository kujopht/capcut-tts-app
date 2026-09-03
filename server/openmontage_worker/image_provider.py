"""Provider-neutral image-generation interface (mission requirement 6:
"provider-neutral AnimationWorker"). `ImageProvider` is the abstraction the
worker codes against; `BeamAnimagineProvider` is the one concrete,
PROVEN implementation - the isolated `cover-illustrious-chartest` Beam
endpoint validated across the two preceding missions in this session.

Per explicit mission instruction ("Do NOT run another model/provider
benchmark" / "Freeze the visual-generation method"), no new provider is
introduced here - this module exists so a future provider could be added
without changing worker.py, not to actually add one now.
"""
from __future__ import annotations

import base64
import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol

REPO = Path(r"C:\Users\nguye\Documents\CapCut-TTS-App")
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))


@dataclass
class ImageResult:
    png_bytes: bytes
    seed: int
    wall_seconds: float
    cost_usd: float


class ImageProvider(Protocol):
    def generate(self, *, prompt: str, negative_prompt: str, seed: int,
                 width: int, height: int, reference_image_png: Optional[bytes] = None,
                 reference_strength: float = 0.5) -> ImageResult:
        ...


class BeamAnimagineProvider:
    """Wraps the isolated `cover-illustrious-chartest` Beam endpoint
    (deployed in the preceding "character-consistency stress test"
    mission, NOT the shared production `cover-illustrious` endpoint).
    Reuses the same cached sdxl-weights Volume - no re-download."""

    URL = "https://cover-illustrious-chartest-994d9f3-v1.app.beam.cloud"
    RTX4090_PER_SECOND_USD = 0.000191667

    def __init__(self):
        from beam_credential import resolve_beam_token
        token = resolve_beam_token()
        if not token:
            raise RuntimeError("No BEAM_TOKEN available via the credential broker.")
        self._token = token

    @staticmethod
    def _placeholder_png() -> bytes:
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (512, 512), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def generate(self, *, prompt: str, negative_prompt: str, seed: int,
                 width: int, height: int, reference_image_png: Optional[bytes] = None,
                 reference_strength: float = 0.5) -> ImageResult:
        import httpx

        ref_png = reference_image_png if reference_image_png is not None else self._placeholder_png()
        ref_strength = reference_strength if reference_image_png is not None else 0.03
        payload = {
            "prompt": prompt, "negative_prompt": negative_prompt, "steps": 28,
            "width": width, "height": height, "seed": seed,
            "primary_reference_images_base64": [base64.b64encode(ref_png).decode("ascii")],
            "reference_strength": ref_strength,
        }
        client = httpx.Client(base_url=self.URL, headers={"Authorization": f"Bearer {self._token}"}, timeout=300.0)
        t0 = time.monotonic()
        resp = client.post("", json=payload)
        wall = time.monotonic() - t0
        cost = wall * self.RTX4090_PER_SECOND_USD
        if resp.status_code != 200:
            raise RuntimeError(f"Beam generation failed: HTTP {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        png_bytes = base64.b64decode(body["image_base64"])
        return ImageResult(png_bytes=png_bytes, seed=body.get("seed", seed),
                            wall_seconds=wall, cost_usd=cost)
