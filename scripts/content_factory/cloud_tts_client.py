"""Lightning AI Cloud TTS Client.

Routes text-to-speech synthesis requests to the free CPU Studio (scratch-studio-devbox).
Offloads 100% of CPU and RAM load from the local computer.
Smoothly falls back to local synthesis if network is unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
import requests

DEFAULT_LIGHTNING_TTS_URL = "https://8000-01m0aq288xz87ygvxbzhx9pf3w.cloudspaces.litng.ai"


def synthesize_cloud_tts(
    text: str,
    voice: str,
    dest_path: Path,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    timeout: float = 60.0,
) -> bool:
    """Synthesizes text via the remote Lightning AI CPU Studio.

    Args:
        text: Text content to synthesize.
        voice: Voice ID (e.g. 'BV075_streaming', 'BV421_vivn_streaming', 'vi-VN-HoaiMyNeural').
        dest_path: Path to save the resulting .mp3 file.
        rate: Speed rate (e.g. '+0%', '+10%').
        pitch: Voice pitch (e.g. '+0Hz').
        timeout: Network timeout in seconds.

    Returns:
        True if synthesis succeeded remotely and file was written, False otherwise.
    """
    remote_url = os.environ.get("LIGHTNING_TTS_URL", DEFAULT_LIGHTNING_TTS_URL).rstrip("/")
    if not remote_url:
        return False

    for attempt in range(2):
        try:
            resp = requests.post(
                f"{remote_url}/synthesize",
                data={
                    "text": text.strip(),
                    "voice": voice,
                    "rate": rate,
                    "pitch": pitch,
                },
                timeout=timeout,
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                dest_path = Path(dest_path)
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(resp.content)
                return True
            else:
                print(f"[CloudTTS] Server trả status {resp.status_code} ({resp.text[:80]})")
        except Exception as exc:
            print(f"[CloudTTS] Không thể kết nối Cloud TTS ({exc})")

        # If first attempt failed, attempt On-Demand Auto-Wake
        if attempt == 0:
            try:
                from scripts.content_factory.lightning_helper import ensure_cpu_tts_studio
                print("[CloudTTS] 💤 Đang thử tự động đánh thức CPU Studio (On-Demand Wake)...")
                if not ensure_cpu_tts_studio():
                    break
            except Exception as e:
                print(f"[CloudTTS] Không thể tự động đánh thức: {e}")
                break

    return False

