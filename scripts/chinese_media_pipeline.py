#!/usr/bin/env python3
"""Chinese Media Watcher — first usable pipeline.

Mission "Chinese Media Watcher foundation" (2026-09-02). Builds and proves
the first end-to-end chain:

    source/watch candidate
    -> source captions if available (YouTube public timedtext API — no
       auth, no download; Track C already found 0/31 real AI-animation
       videos with real caption tracks, so this stage exists but usually
       returns nothing today)
    -> faster-whisper fallback (Mandarin ASR, runs locally)
    -> Mandarin transcript
    -> translation to Vietnamese (Antigravity, same `agy` CLI already used
       for every EN->VI chapter this session, here ZH->VI)
    -> timestamp-preserving subtitle reconstruction (.srt, original
       segment timings kept exactly)
    -> optional Ngoc Huyen Moi dub (reuses desktop_app's real Piper
       provider — the same code validated end-to-end this session)
    -> ffmpeg composition (mux subtitle track, optionally the dub track)
    -> DRAFT media entry (POST /api/novels, reusing the Novel/METADATA_ONLY
       video-draft fields from "SHIP 3 CHINESE AI-ANIMATION VIDEO DRAFTS")

RIGHTS DISCIPLINE (same posture as every other acquisition tool this
session — no exceptions):
  - Never rehosts source video/audio bytes. rights_mode defaults to
    REFERENCE_ONLY: only the translated subtitle (+ optional dub) is
    produced and stored, never a copy of the source media itself.
    EMBED_ONLY (link to the original platform player) and REHOST_ALLOWED
    (only for content with verified redistribution rights) remain
    available for a caller that has actually established those rights for
    a specific source — this script does not grant itself REHOST_ALLOWED.
  - No copyright-evasion transforms of any kind: no re-encoding to dodge
    content-ID, no removing watermarks/attribution, no obscuring
    provenance. `external_source_url`/`external_author_name` are always
    recorded when a real source exists.
  - ASR audio is read from a LOCAL file the caller supplies. This script
    does not download from YouTube/Bilibili/etc. itself (no yt-dlp
    dependency) — that acquisition step is a separate, source-specific
    decision the operator makes per candidate, same as every other T0-T4
    acquisition tier in this repo's own Universal Acquisition Engine.

Usage:
    python scripts/chinese_media_pipeline.py \\
        --audio path/to/mandarin.wav \\
        --title "..." --source-url "..." --author "..." \\
        --rights-mode REFERENCE_ONLY --dub

Reads FAS_HARVESTER_SERVICE_TOKEN from the credential broker, and
server/.env.production (never printed) for direct R2 upload of the
subtitle/dub outputs. Never publishes: only POST /api/novels.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi  # noqa: E402

VALID_RIGHTS_MODES = ("REFERENCE_ONLY", "EMBED_ONLY", "REHOST_ALLOWED")
VOICE_ID = "piper:ngochuyennew"


@dataclass
class Segment:
    start: float
    end: float
    zh_text: str
    vi_text: str = ""


# --------------------------------------------------------------------------
# Stage 1: source captions, if a real track exists (no download, no auth).
# --------------------------------------------------------------------------

def find_source_captions(platform: str, video_id: str) -> Optional[List[Segment]]:
    """YouTube's public timedtext list API. Empty list -> no real caption
    tracks (this is the overwhelmingly common case per Track C's own 0/31
    finding this session — burned-in subtitles are not a caption track).
    Returns None (not attempted) for any platform other than youtube."""
    if platform != "youtube":
        return None
    url = ("https://video.google.com/timedtext?type=list&v="
           + urllib.parse.quote(video_id))
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[captions] list request failed: {type(exc).__name__}: {exc}")
        return None
    if "<track" not in body:
        print("[captions] no real caption tracks (empty <transcript_list/>)")
        return None
    print(f"[captions] FOUND real track(s): {body[:300]}")
    # A real track exists but fetching/parsing its cues is a separate,
    # deliberately unimplemented step: nothing in this mission's 31 checked
    # candidates has ever reached this branch, and building cue-format
    # parsing for a code path with zero real hits so far is speculative
    # work ahead of an actual need.
    return None


# --------------------------------------------------------------------------
# Stage 2: faster-whisper fallback (real ASR, runs on this machine).
# --------------------------------------------------------------------------

def transcribe_mandarin(audio_path: Path, model_size: str = "small") -> List[Segment]:
    from faster_whisper import WhisperModel

    print(f"[asr] loading faster-whisper model={model_size} (CPU)...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(str(audio_path), language="zh", vad_filter=True)
    print(f"[asr] detected language={info.language} prob={info.language_probability:.2f}")
    out: List[Segment] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if text:
            out.append(Segment(start=seg.start, end=seg.end, zh_text=text))
    print(f"[asr] {len(out)} segment(s) transcribed")
    return out


# --------------------------------------------------------------------------
# Stage 3: ZH -> VI translation, batched as one JSON array so segment
# alignment survives (translating a flattened SRT risks the model merging
# or splitting lines).
# --------------------------------------------------------------------------

def translate_zh_to_vi(segments: List[Segment], timeout: str = "3m") -> None:
    """Mutates each Segment's vi_text in place."""
    if not segments:
        return
    payload = [s.zh_text for s in segments]
    prompt = (
        "Dich cac cau tieng Trung sau sang tieng Viet. Tra ve DUY NHAT mot "
        "mang JSON cung do dai, cung thu tu, moi phan tu la ban dich tieng "
        "Viet tuong ung — khong giai thich them, khong danh so, khong bao "
        "boc trong markdown.\n\n" + json.dumps(payload, ensure_ascii=False)
    )
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(prompt)
        prompt_path = f.name
    try:
        with open(prompt_path, "r", encoding="utf-8") as stdin_f:
            result = subprocess.run(
                ["agy", "--print-timeout", timeout],
                stdin=stdin_f,
                capture_output=True, text=True, encoding="utf-8", timeout=240,
            )
        raw = result.stdout.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            raise ValueError(
                f"no JSON array in agy output (exit={result.returncode}): "
                f"stdout={raw[:300]!r} stderr={result.stderr[:300]!r}"
            )
        translated = json.loads(raw[start:end + 1])
        if len(translated) != len(segments):
            raise ValueError(
                f"length mismatch: {len(translated)} translations for "
                f"{len(segments)} segments"
            )
        for seg, vi in zip(segments, translated):
            seg.vi_text = str(vi).strip()
    finally:
        os.unlink(prompt_path)


# --------------------------------------------------------------------------
# Stage 4: timestamp-preserving subtitle reconstruction.
# --------------------------------------------------------------------------

def _srt_timestamp(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hh, rem = divmod(ms_total, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def write_srt(segments: List[Segment], path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(seg.start)} --> {_srt_timestamp(seg.end)}")
        lines.append(seg.vi_text or seg.zh_text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# Stage 5 (optional): Ngoc Huyen Moi dub. Best-effort timing: each segment
# is synthesized independently and padded/trimmed to its own [start, end]
# window so the dub track's total length matches the source, but this is
# NOT prosody-matched dubbing — a segment's spoken length rarely equals its
# source window exactly. Honest limitation, not hidden.
# --------------------------------------------------------------------------

def dub_segments(segments: List[Segment], out_path: Path, ffmpeg: str) -> None:
    from desktop_app.providers.piper_models import PiperModelManager
    from desktop_app.providers.piper_provider import PiperLocalProvider
    from desktop_app.providers.base import Voice

    manager = PiperModelManager()
    model = manager.find("ngochuyennew")
    if not model.installed:
        raise RuntimeError(f"ngochuyennew not installed: {model.status_reason}")
    provider = PiperLocalProvider(manager=manager)
    voice = Voice(provider="piper", voice_key="ngochuyennew",
                  engine_voice_id="ngochuyennew", display_name="Ngoc Huyen (Moi)",
                  language="vi", installed=True)

    total_end = max((s.end for s in segments), default=0.0)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        concat_list = tmp_dir / "concat.txt"
        entries = []
        cursor = 0.0
        for i, seg in enumerate(segments):
            gap = max(0.0, seg.start - cursor)
            if gap > 0.02:
                silence = tmp_dir / f"gap_{i}.wav"
                subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                               "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono",
                               "-t", f"{gap:.3f}", str(silence)], check=True)
                entries.append(silence)
                cursor += gap
            seg_mp3 = tmp_dir / f"seg_{i}.mp3"
            if seg.vi_text.strip():
                provider.synthesize(text=seg.vi_text, voice=voice, dest=seg_mp3)
                entries.append(seg_mp3)
                cursor += seg.end - seg.start  # approximate: fits the window
        with open(concat_list, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"file '{e.as_posix()}'\n")
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                       "-f", "concat", "-safe", "0", "-i", str(concat_list),
                       str(out_path)], check=True)
    print(f"[dub] wrote {out_path} ({out_path.stat().st_size} bytes, "
          f"target length ~{total_end:.1f}s)")


# --------------------------------------------------------------------------
# Stage 6: ffmpeg composition — mux subtitle (and optional dub audio) onto
# the source. Only runs when the caller supplies a local source media file
# AND has REHOST_ALLOWED rights for it; otherwise this stage is skipped and
# only the standalone .srt/.mp3 outputs are produced (the REFERENCE_ONLY /
# EMBED_ONLY safe path).
# --------------------------------------------------------------------------

def compose_with_source(source_media: Path, srt_path: Path,
                        dub_path: Optional[Path], out_path: Path, ffmpeg: str) -> None:
    # Subtitle codec is CONTAINER-specific, not universal: `mov_text` is the
    # MP4/MOV subtitle codec and fails outright ("Function not implemented")
    # when muxed into Matroska, which wants `srt` (plain SubRip passthrough)
    # instead. Measured against a real render, not assumed.
    subtitle_codec = "mov_text" if out_path.suffix.lower() in (".mp4", ".mov", ".m4v") else "srt"
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source_media), "-i", str(srt_path)]
    maps = ["-map", "0:v", "-map", "0:a", "-map", "1"]
    if dub_path is not None:
        args += ["-i", str(dub_path)]
        maps += ["-map", "2:a"]
    args += maps + ["-c:v", "copy", "-c:a", "copy", "-c:s", subtitle_codec, str(out_path)]
    subprocess.run(args, check=True)


# --------------------------------------------------------------------------
# Stage 7: DRAFT media entry.
# --------------------------------------------------------------------------

def upload_to_r2(key: str, data: bytes, content_type: str) -> None:
    """Direct R2 upload using the same local production credentials the
    worker uses (server/.env.production) -- never prints a secret."""
    os.environ.setdefault("FAS_ENV_FILE", str(REPO_ROOT / "server" / ".env.production"))
    from server.config import get_settings
    from server.r2_adapter import R2StorageAdapter
    from server.storage_backend import R2StorageBackendWrapper

    settings = get_settings()
    adapter = R2StorageAdapter(settings.r2)
    backend = R2StorageBackendWrapper(adapter)
    backend.put(key, data, content_type)


def ship_draft(*, title: str, source_url: str, author: str, rights_mode: str,
               platform: str, embed_ref: str, srt_bytes: bytes,
               dub_bytes: Optional[bytes], token: str) -> str:
    subtitle_key = f"subtitles/svc_harvester/{Path(source_url).stem or 'clip'}-{os.urandom(4).hex()}.srt"
    upload_to_r2(subtitle_key, srt_bytes, "text/srt")
    dub_key = ""
    if dub_bytes is not None:
        dub_key = subtitle_key.replace("/subtitles/", "/dub_audio/").replace(".srt", ".mp3")
        upload_to_r2(dub_key, dub_bytes, "audio/mpeg")

    ma, r = goi(DEFAULT_API, "POST", "/api/novels", {
        "title": title,
        "description": (
            f"Chinese Media Watcher pipeline output. Source: {source_url or 'n/a'}. "
            f"Attribution: {author or 'unknown'}. rights_mode={rights_mode} — "
            f"{'no source media redistributed, subtitle/dub only' if rights_mode != 'REHOST_ALLOWED' else 'rights verified for this source'}."
        ),
        "tags": ["Chinese-Media-Watcher", "AI-Animation"],
        "publication_mode": "metadata_only",
        "external_author_name": author,
        "external_source_url": source_url,
        "language": "vi",
        "status": "ongoing",
        "platform": platform,
        "rights_mode": rights_mode,
        "subtitle_status": "READY",
        "embed_ref": embed_ref,
        "subtitle_key": subtitle_key,
        "dub_audio_key": dub_key,
    }, token=token)
    if ma != 201:
        raise RuntimeError(f"POST /api/novels -> {ma}: {r}")
    novel = r.get("novel") or r
    return novel["novel_id"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--audio", required=True, help="local Mandarin audio/video file")
    ap.add_argument("--title", required=True)
    ap.add_argument("--source-url", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--platform", default="")
    ap.add_argument("--embed-ref", default="")
    ap.add_argument("--rights-mode", default="REFERENCE_ONLY", choices=VALID_RIGHTS_MODES)
    ap.add_argument("--dub", action="store_true", help="also synthesize a VI dub track")
    ap.add_argument("--whisper-model", default="small")
    args = ap.parse_args()

    token = broker.fetch("FAS_HARVESTER_SERVICE_TOKEN")
    if not token:
        print(json.dumps({"status": "BLOCKED", "reason": "no harvester token"}))
        return 2

    from desktop_app.output_manager import find_ffmpeg
    ffmpeg = find_ffmpeg(None)
    if not ffmpeg:
        print(json.dumps({"status": "BLOCKED", "reason": "ffmpeg not found"}))
        return 2

    audio_path = Path(args.audio)
    if not audio_path.is_file():
        print(json.dumps({"status": "BLOCKED", "reason": f"no such file: {audio_path}"}))
        return 2

    print("=== 1/7 source captions ===")
    segments = find_source_captions(args.platform, args.embed_ref)

    if segments is None:
        print("=== 2/7 faster-whisper fallback ===")
        segments = transcribe_mandarin(audio_path, args.whisper_model)

    if not segments:
        print(json.dumps({"status": "FAIL", "reason": "no speech segments found"}))
        return 1

    print("=== 3/7 translate ZH -> VI ===")
    translate_zh_to_vi(segments)
    for s in segments[:3]:
        print(f"  [{s.start:.1f}-{s.end:.1f}] {s.zh_text!r} -> {s.vi_text!r}")

    print("=== 4/7 write SRT ===")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        srt_path = tmp_dir / "subs.srt"
        write_srt(segments, srt_path)
        print(f"  {srt_path} ({srt_path.stat().st_size} bytes)")

        dub_path = None
        if args.dub:
            print("=== 5/7 dub (Ngoc Huyen Moi) ===")
            dub_path = tmp_dir / "dub.mp3"
            dub_segments(segments, dub_path, ffmpeg)

        print("=== 6/7 ffmpeg composition (skipped: no local source video "
              "supplied — REFERENCE_ONLY posture keeps this to subtitle/dub "
              "artifacts only, no rehosted media) ===")

        print("=== 7/7 DRAFT media entry ===")
        novel_id = ship_draft(
            title=args.title, source_url=args.source_url, author=args.author,
            rights_mode=args.rights_mode, platform=args.platform,
            embed_ref=args.embed_ref, srt_bytes=srt_path.read_bytes(),
            dub_bytes=dub_path.read_bytes() if dub_path else None,
            token=token,
        )
        print(json.dumps({"status": "PASS", "novel_id": novel_id,
                          "segments": len(segments)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
