"""
Pure, beam-SDK-independent helper logic for cover_illustrious_app.py.

Split out so this logic can be real-unit-tested: `beam` is a remote-deploy-
only dependency (see cover_illustrious_app.py's own docstring) and is NOT
installed in this repo's own venv, so any module that does
`from beam import ...` at top level cannot be imported locally at all,
let alone tested. This file has zero such import, only stdlib.
"""
from __future__ import annotations

import base64

DEFAULT_NEGATIVE_PROMPT = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, "
    "extra digit, fewer digits, cropped, worst quality, low quality, "
    "normal quality, jpeg artifacts, signature, watermark, blurry"
)


def resolve_negative_prompt(negative_prompt: str) -> str:
    """Neu caller khong truyen negative_prompt (chuoi rong), dung mac dinh."""
    return negative_prompt or DEFAULT_NEGATIVE_PROMPT


def build_response_payload(
    png_bytes: bytes,
    *,
    model_load_seconds: float,
    inference_seconds: float,
    width: int,
    height: int,
) -> dict:
    """
    Lap rap dung response contract cua endpoint (xem
    server/cover_pipeline.py::HttpImageCoverProvider._call_simple, doc du
    lieu {"image_base64": ...} tu day).

    `model_load_seconds` la thoi gian load model DUY NHAT MOT LAN (tu
    on_start, xem load_pipeline() trong cover_illustrious_app.py) - moi
    request tren CUNG mot container se bao cung gia tri nay, KHONG phai 0,
    vi day la so lieu that cua lan load that su, khong phai "khong load
    lai" bi bao sai thanh 0.
    """
    return {
        "image_base64": base64.b64encode(png_bytes).decode("ascii"),
        "model_load_seconds": round(model_load_seconds, 3),
        "inference_seconds": round(inference_seconds, 3),
        "width": width,
        "height": height,
        "size_bytes": len(png_bytes),
    }
