"""Lightning AI Serverless Worker for AI Animation & Whisper Transcription.

Runs inside a Lightning AI Studio with an L4 or T4 GPU.
Exposes a high-performance FastAPI endpoint on port 8000.
Transcribes 30-minute audio files in ~30-45 seconds using CUDA float16.
"""

import ctypes
import os
import shutil
import site
import sys
import tempfile
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional

# Preload NVIDIA CUDA 12 libraries into global namespace
for sp in site.getsitepackages():
    for sub in ["nvidia/cublas/lib", "nvidia/cudnn/lib"]:
        lp = os.path.join(sp, sub)
        if os.path.isdir(lp):
            if "LD_LIBRARY_PATH" in os.environ:
                os.environ["LD_LIBRARY_PATH"] = f"{lp}:{os.environ['LD_LIBRARY_PATH']}"
            else:
                os.environ["LD_LIBRARY_PATH"] = lp
            for fname in sorted(os.listdir(lp)):
                if fname.endswith(".so.12") or fname.endswith(".so.9"):
                    try:
                        ctypes.CDLL(os.path.join(lp, fname), mode=ctypes.RTLD_GLOBAL)
                    except Exception:
                        pass

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
import uvicorn
from faster_whisper import WhisperModel

app = FastAPI(title="Lightning AI Whisper GPU Worker")

try:
    has_gpu = shutil.which("nvidia-smi") is not None
except Exception:
    has_gpu = False

if has_gpu:
    try:
        print("[Init] Đang nạp model faster-whisper lên GPU (CUDA - float16)...")
        model = WhisperModel("small", device="cuda", compute_type="float16")
        current_device = "cuda"
        print("[Init] ✅ GPU L4/T4 đã sẵn sàng xử lý siêu tốc!")
    except Exception as exc:
        print(f"[Init] Lỗi CUDA ({exc}), fallback sang CPU...")
        model = WhisperModel("small", device="cpu", compute_type="int8")
        current_device = "cpu"
else:
    print("[Init] Không phát hiện GPU, nạp faster-whisper trên CPU (int8)...")
    model = WhisperModel("small", device="cpu", compute_type="int8")
    current_device = "cpu"


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "HEALTHY", "device": current_device, "model": "faster-whisper-small"}


@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("auto"),
) -> Dict[str, Any]:
    """Transcribes uploaded audio on GPU and returns synchronized dialogue lines."""
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        lang_arg = language if language and language != "auto" else None
        segments, info = model.transcribe(
            str(tmp_path),
            vad_filter=True,
            language=lang_arg,
        )
        lines = []
        for i, seg in enumerate(segments, start=1):
            txt = seg.text.strip()
            if txt:
                lines.append({
                    "index": i,
                    "start": round(seg.start, 3),
                    "end": round(seg.end, 3),
                    "original_text": txt,
                })

        return {
            "status": "SUCCESS",
            "detected_language": info.language,
            "language_probability": round(info.language_probability, 3),
            "lines_count": len(lines),
            "lines": lines,
        }
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@app.post("/render_video")
async def render_video_endpoint(
    video: UploadFile = File(...),
    subtitles: UploadFile = File(...),
    dub_audio: Optional[UploadFile] = File(None),
    mask_y: int = Form(648),
    mask_h: int = Form(72),
):
    """Renders final video on L4 GPU using NVENC hardware acceleration."""
    work_dir = Path(tempfile.mkdtemp(prefix="l4_render_"))
    raw_v = work_dir / "raw.mp4"
    ass_f = work_dir / "subtitles.ass"
    out_v = work_dir / "rendered.mp4"

    try:
        with open(raw_v, "wb") as f:
            shutil.copyfileobj(video.file, f)

        with open(ass_f, "wb") as f:
            shutil.copyfileobj(subtitles.file, f)

        dub_f = None
        if dub_audio and dub_audio.filename:
            dub_f = work_dir / "dub.mp3"
            with open(dub_f, "wb") as f:
                shutil.copyfileobj(dub_audio.file, f)

        vf = f"drawbox=y={mask_y}:h={mask_h}:color=black:t=fill,subtitles=subtitles.ass"

        if dub_f and dub_f.exists():
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(raw_v),
                "-i", str(dub_f),
                "-filter_complex",
                f"[0:v]{vf}[v_out];[0:a]volume=0.16[a_bg];[1:a]volume=1.05[a_fg];[a_bg][a_fg]amix=inputs=2:duration=first[a_out]",
                "-map", "[v_out]",
                "-map", "[a_out]",
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                "-c:a", "aac", "-b:a", "192k",
                str(out_v),
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(raw_v),
                "-vf", vf,
                "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
                "-c:a", "copy",
                str(out_v),
            ]

        proc = subprocess.run(cmd, cwd=str(work_dir), capture_output=True, text=True)
        if proc.returncode != 0:
            # Fallback to libx264 if nvenc encounters stream issue
            if "h264_nvenc" in cmd:
                idx = cmd.index("h264_nvenc")
                cmd[idx] = "libx264"
                cmd[idx + 1] = "-preset"
                cmd[idx + 2] = "fast"
                cmd[idx + 3] = "-crf"
                cmd[idx + 4] = "20"
                subprocess.run(cmd, cwd=str(work_dir), check=True)

        if not out_v.exists():
            return JSONResponse({"status": "ERROR", "error": "Rendered video not produced"}, status_code=500)

        video_bytes = out_v.read_bytes()
        return Response(content=video_bytes, media_type="video/mp4")
    except Exception as exc:
        return JSONResponse({"status": "ERROR", "error": str(exc)}, status_code=500)
    finally:
        try:
            shutil.rmtree(work_dir)
        except OSError:
            pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

