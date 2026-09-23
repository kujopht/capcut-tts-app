"""Lightning AI Free CPU Worker for High-Speed TTS Audio Generation.

Runs inside the free CPU Studio (scratch-studio-devbox) with 4 vCPUs & 16GB RAM.
Exposes a lightweight FastAPI endpoint on port 8000.
Supports:
1. Piper ONNX (Ngọc Huyền Mới - NghiTTS) running locally on the cloud CPU!
2. CapCut TTS (Thanh Nien Tu Tin, Nhe Ngot Ngao).
3. Microsoft Edge-TTS (fallback).

Returns synthesized MP3 audio streams directly to offload 100% CPU load from local PC.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import FileResponse, Response
import uvicorn
import edge_tts

def get_piper_binary() -> str:
    """Locates the piper binary across common environments."""
    which_piper = shutil.which("piper")
    if which_piper:
        return which_piper
    py_bin = Path(sys.executable).parent / "piper"
    if py_bin.exists():
        return str(py_bin)
    for candidate in [
        "/home/zeus/miniconda3/envs/cloudspace/bin/piper",
        "/home/zeus/.local/bin/piper",
        "/usr/local/bin/piper",
    ]:
        if Path(candidate).exists():
            return candidate
    return "piper"


# Paths for Piper ONNX
PIPER_MODEL_DIRS = [
    Path("/teamspace/studios/this_studio/models/piper"),
    Path("/content/models/piper"),
    Path.home() / ".local/share/piper/models",
]
ONNX_PATH = Path("/teamspace/studios/this_studio/models/piper/ngochuyennew.onnx")
JSON_PATH = Path("/teamspace/studios/this_studio/models/piper/ngochuyennew.onnx.json")
for _d in PIPER_MODEL_DIRS:
    if (_d / "ngochuyennew.onnx").exists():
        ONNX_PATH = _d / "ngochuyennew.onnx"
        JSON_PATH = _d / "ngochuyennew.onnx.json"
        break

# Try importing CapCutClient if package uploaded
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, "/teamspace/studios/this_studio")
try:
    from capcut_tts_api.client import CapCutClient
    capcut_available = True
    capcut_client = CapCutClient()
except Exception as exc:
    capcut_available = False
    capcut_client = None

app = FastAPI(title="Lightning AI CPU TTS Worker")

import wave
import hashlib

RAM_DIR = Path("/dev/shm") if Path("/dev/shm").exists() else Path(tempfile.gettempdir())

# Auto-load RCLONE_CONFIG from /content/rclone_env.sh if set by setup script
_rclone_env_file = Path("/content/rclone_env.sh")
if _rclone_env_file.exists() and not os.environ.get("RCLONE_CONFIG"):
    for _line in _rclone_env_file.read_text().splitlines():
        _line = _line.strip().lstrip("export").strip()
        if _line.startswith("RCLONE_CONFIG="):
            _val = _line.split("=", 1)[1].strip().strip("'\"")
            if _val and Path(_val).exists():
                os.environ["RCLONE_CONFIG"] = _val
                print(f"[TTS Server] Loaded RCLONE_CONFIG={_val} from {_rclone_env_file}")
            break

# Try pre-loading PiperVoice into RAM at startup
piper_voice_ram = None
try:
    if ONNX_PATH.exists():
        from piper.voice import PiperVoice
        piper_voice_ram = PiperVoice.load(str(ONNX_PATH), config_path=str(JSON_PATH))
        print(f"[TTS Server] Preloaded PiperVoice Ngọc Huyền Mới directly into RAM! Sample rate: {getattr(piper_voice_ram.config, 'sample_rate', 22050)}")
except Exception as e:
    print(f"[TTS Server] PiperVoice RAM preload failed ({e}), will use CLI fallback.")


@app.get("/health")
def health_check() -> Dict[str, Any]:
    piper_bin = get_piper_binary()
    return {
        "status": "HEALTHY",
        "device": "cpu",
        "service": "lightning-tts-cpu",
        "piper_supported": ONNX_PATH.exists(),
        "piper_in_ram": piper_voice_ram is not None,
        "ram_disk": str(RAM_DIR),
        "piper_binary": piper_bin,
        "piper_model": str(ONNX_PATH) if ONNX_PATH.exists() else None,
        "capcut_supported": capcut_available,
        "default_voices": [
            "ngochuyennew",
            "BV075_streaming",
            "BV421_vivn_streaming",
            "vi-VN-HoaiMyNeural",
            "vi-VN-NamMinhNeural",
        ],
    }


@app.post("/v1/tts/synthesize")
async def synthesize_v1(
    text: str = Form(...),
    voice_id: str = Form("ngochuyennew"),
    chapter_id: Optional[str] = Form(None),
    chunk_index: Optional[int] = Form(None),
    content_hash: Optional[str] = Form(None),
    rate: str = Form("+0%"),
    pitch: str = Form("+0Hz"),
    output_format: str = Form("mp3"),
) -> Response:
    """Production Serverless TTS endpoint with content hash validation and performance telemetry."""
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    actual_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
    if content_hash and content_hash.strip().lower() != actual_hash:
        raise HTTPException(
            status_code=400,
            detail=f"CONTENT_HASH_MISMATCH: Provided '{content_hash}' != computed '{actual_hash}'"
        )

    t_start = time.time()
    task_tag = f"{time.time()}_{os.getpid()}_{actual_hash[:8]}"
    wav_path = RAM_DIR / f"piper_{task_tag}.wav"
    mp3_path = RAM_DIR / f"piper_{task_tag}.mp3"

    try:
        if not ONNX_PATH.exists():
            raise HTTPException(status_code=503, detail=f"Piper ONNX model not found at {ONNX_PATH}")

        # Synthesize WAV
        if piper_voice_ram is not None:
            sample_rate = int(getattr(piper_voice_ram.config, 'sample_rate', 22050) or 22050)
            method = getattr(piper_voice_ram, 'synthesize_wav', None)
            with wave.open(str(wav_path), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                method(clean_text, wf)
        else:
            piper_bin = get_piper_binary()
            cmd = [piper_bin, "--model", str(ONNX_PATH), "--output_file", str(wav_path)]
            proc = subprocess.run(cmd, input=clean_text.encode("utf-8"), capture_output=True, check=False)
            if proc.returncode != 0:
                err_msg = proc.stderr.decode("utf-8", errors="replace")
                raise HTTPException(status_code=500, detail=f"Piper CLI error: {err_msg}")

        # Measure audio duration
        duration_s = 0.0
        with wave.open(str(wav_path), 'rb') as wf:
            frames = wf.getnframes()
            rate_hz = wf.getframerate()
            duration_s = frames / float(rate_hz) if rate_hz else 0.0

        if output_format.lower() == "wav":
            audio_bytes = wav_path.read_bytes()
            media_type = "audio/wav"
        else:
            # Encode MP3 at 64kbps CBR (standard audiobook bitrate, low storage) or 128k
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(wav_path),
                "-c:a", "libmp3lame", "-b:a", "64k",
                str(mp3_path)
            ]
            subprocess.run(ffmpeg_cmd, check=True)
            audio_bytes = mp3_path.read_bytes()
            media_type = "audio/mpeg"

        elapsed_s = time.time() - t_start
        audio_sha = hashlib.sha256(audio_bytes).hexdigest()

        headers = {
            "X-Chapter-ID": str(chapter_id or ""),
            "X-Chunk-Index": str(chunk_index if chunk_index is not None else ""),
            "X-Voice-ID": voice_id,
            "X-Content-Hash": actual_hash,
            "X-Audio-Duration-Seconds": f"{duration_s:.3f}",
            "X-Synthesis-Time-Seconds": f"{elapsed_s:.3f}",
            "X-Audio-SHA256": audio_sha,
        }
        return Response(content=audio_bytes, media_type=media_type, headers=headers)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS synthesis failure: {exc}")
    finally:
        wav_path.unlink(missing_ok=True)
        mp3_path.unlink(missing_ok=True)


@app.post("/synthesize")
async def synthesize_text(
    text: str = Form(...),
    voice: str = Form("ngochuyennew"),
    rate: str = Form("+0%"),
    pitch: str = Form("+0Hz"),
) -> Response:
    """Synthesizes text into high-quality MP3 audio and streams it directly."""
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    voice_lower = voice.lower()

    # 1. Check if Piper voice requested (Ngọc Huyền Mới - NghiTTS)
    if "ngochuyen" in voice_lower or voice_lower in ("piper", "piper:ngochuyennew", "ngochuyennew"):
        if not ONNX_PATH.exists():
            raise HTTPException(status_code=503, detail=f"Piper ONNX model not found at {ONNX_PATH}")

        # Unique file names in RAM disk /dev/shm
        task_tag = f"{time.time()}_{os.getpid()}_{abs(hash(clean_text))}"
        wav_path = RAM_DIR / f"piper_{task_tag}.wav"
        mp3_path = RAM_DIR / f"piper_{task_tag}.mp3"

        try:
            # FAST IN-RAM SYNTHESIS PATH
            if piper_voice_ram is not None:
                sample_rate = int(getattr(piper_voice_ram.config, 'sample_rate', 22050) or 22050)
                method = getattr(piper_voice_ram, 'synthesize_wav', None)
                with wave.open(str(wav_path), 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(sample_rate)
                    method(clean_text, wf)
            else:
                # Fallback to CLI
                piper_bin = get_piper_binary()
                cmd = [piper_bin, "--model", str(ONNX_PATH), "--output_file", str(wav_path)]
                proc = subprocess.run(cmd, input=clean_text.encode("utf-8"), capture_output=True, check=False)
                if proc.returncode != 0:
                    err_msg = proc.stderr.decode("utf-8", errors="replace")
                    print(f"[TTS] Lỗi Piper: {err_msg}")
                    raise HTTPException(status_code=500, detail=f"Piper CLI error: {err_msg}")

            # Fast RAM-to-RAM MP3 encoding via FFmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(wav_path),
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(mp3_path)
            ]
            subprocess.run(ffmpeg_cmd, check=True)

            audio_bytes = mp3_path.read_bytes()
            return Response(content=audio_bytes, media_type="audio/mpeg")
        except HTTPException:
            raise
        except Exception as p_exc:
            print(f"[TTS] Lỗi xử lý âm thanh Piper ({p_exc})")
            raise HTTPException(status_code=500, detail=f"Piper synthesis error: {p_exc}")
        finally:
            wav_path.unlink(missing_ok=True)
            mp3_path.unlink(missing_ok=True)

    # 2. Check if CapCut voice requested (BV075, BV421, etc.)
    if voice.startswith("BV") or voice.startswith("multi_"):
        if not capcut_available or capcut_client is None:
            raise HTTPException(status_code=503, detail=f"CapCut client not configured on server for voice {voice}")
        try:
            res = capcut_client.generate_speech([clean_text], voice=voice, timeout=25.0)
            import json as _json, requests as _req
            payload = _json.loads(res["data"]["tasks"][0]["payload"])
            sub = payload["audio_subtitles"][0]
            url = sub.get("speech_url")
            if url:
                r = _req.get(url, timeout=20)
                if r.status_code == 200 and len(r.content) > 100:
                    return Response(content=r.content, media_type="audio/mpeg")
            raise HTTPException(status_code=502, detail="CapCut did not return valid speech URL")
        except HTTPException:
            raise
        except Exception as c_exc:
            print(f"[TTS] CapCut lỗi ({c_exc})")
            raise HTTPException(status_code=502, detail=f"CapCut synthesis failed for voice {voice}: {c_exc}")

    # 3. Fallback: Edge-TTS (only for explicit vi-VN requests, NOT for CapCut voices)
    edge_voice = voice if voice.startswith("vi-VN") else "vi-VN-HoaiMyNeural"
    try:
        communicate = edge_tts.Communicate(clean_text, edge_voice, rate=rate, pitch=pitch)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return Response(content=buf.read(), media_type="audio/mpeg")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS error: {str(exc)}")


@app.post("/download_and_sync")
async def download_and_sync(
    url: str = Form(...),
    branch: str = Form("youtube_audio"),        # "youtube_audio" | "ai_animation"
    dest_slug: str = Form(...),                  # thư mục con trên Drive
    drive_remote: str = Form("fanfic-gdrive:FanficWorld/production/works/existing-audio"),
) -> Dict[str, Any]:
    """Downloads audio/video from YouTube via yt-dlp on the cloud CPU and uploads to Google Drive via rclone.

    Args:
        url: YouTube URL to download.
        branch: "youtube_audio" (MP3 only) or "ai_animation" (MP4 + audio).
        dest_slug: Subfolder name on Google Drive under drive_remote.
        drive_remote: rclone remote path (default: fanfic-gdrive:...existing-audio).

    Returns:
        JSON with status, file counts, and Drive path.
    """
    import json as _json

    # Find rclone config (check env, then fallback to well-known paths)
    rclone_config = os.environ.get("RCLONE_CONFIG", "")
    if not rclone_config:
        for candidate in [
            Path.home() / ".config/rclone/rclone.conf",
            Path("/teamspace/studios/this_studio/.config/rclone/rclone.conf"),
            Path("/content/rclone.conf"),
        ]:
            if candidate.exists():
                rclone_config = str(candidate)
                break

    # yt-dlp binary
    ytdlp_bin = shutil.which("yt-dlp") or "/home/zeus/miniconda3/envs/cloudspace/bin/yt-dlp"

    # Working dir in /dev/shm for speed (fallback /tmp)
    work_dir = RAM_DIR / f"dl_{abs(hash(url + dest_slug))}"
    work_dir.mkdir(parents=True, exist_ok=True)
    drive_path = f"{drive_remote.rstrip('/')}/{dest_slug}"

    try:
        # ── Step 1: Get metadata ───────────────────────────────────────────────
        dump_cmd = [ytdlp_bin, "--dump-json", "--no-warnings", "--no-playlist", url]
        dump_p = subprocess.run(dump_cmd, capture_output=True, text=True, timeout=60)
        info = {}
        if dump_p.returncode == 0:
            try:
                info = _json.loads(dump_p.stdout.strip())
            except Exception:
                pass
        title = info.get("title", dest_slug)
        duration = info.get("duration", 0)

        print(f"[Download] Branch={branch} | Title={title} | URL={url}")

        # ── Step 2: Download ───────────────────────────────────────────────────
        if branch == "ai_animation":
            dl_cmd = [
                ytdlp_bin,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "--write-thumbnail", "--convert-thumbnails", "jpg",
                "-o", str(work_dir / "video.%(ext)s"),
                "-o", f"thumbnail:{work_dir}/cover.%(ext)s",
                "--no-warnings", url,
            ]
        else:  # youtube_audio
            dl_cmd = [
                ytdlp_bin,
                "--extract-audio", "--audio-format", "mp3", "--audio-quality", "192K",
                "--write-thumbnail", "--convert-thumbnails", "jpg",
                "-o", str(work_dir / "audio.%(ext)s"),
                "-o", f"thumbnail:{work_dir}/cover.%(ext)s",
                "--no-warnings", url,
            ]

        t0 = time.time()
        dl_p = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=600)
        if dl_p.returncode != 0:
            err = (dl_p.stderr or "")[:500]
            raise HTTPException(status_code=500, detail=f"yt-dlp error: {err}")

        elapsed_dl = time.time() - t0
        files = list(work_dir.iterdir())
        print(f"[Download] ✓ Tải xong {len(files)} file trong {elapsed_dl:.1f}s → {work_dir}")

        # ── Step 3: Upload to Google Drive ────────────────────────────────────
        if not rclone_config:
            raise HTTPException(status_code=503, detail="rclone config not found on Cloud Studio")

        rclone_cmd = [
            "rclone", "copy", str(work_dir), drive_path,
            "--config", rclone_config,
            "--drive-chunk-size", "128M",
            "--transfers", "4",
            "--stats", "0",
        ]
        t1 = time.time()
        rc_p = subprocess.run(rclone_cmd, capture_output=True, text=True, timeout=600)
        elapsed_up = time.time() - t1

        if rc_p.returncode != 0:
            err = (rc_p.stderr or "")[:500]
            raise HTTPException(status_code=500, detail=f"rclone error: {err}")

        print(f"[Download] ✓ Đã upload lên Drive: {drive_path} ({elapsed_up:.1f}s)")

        return {
            "status": "SUCCESS",
            "title": title,
            "duration_sec": duration,
            "branch": branch,
            "files": [f.name for f in files],
            "drive_path": drive_path,
            "time_download_sec": round(elapsed_dl, 1),
            "time_upload_sec": round(elapsed_up, 1),
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"download_and_sync error: {exc}")
    finally:
        # Dọn /dev/shm
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
