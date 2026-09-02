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
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fanfic_credential_broker as broker  # noqa: E402
from mission_g_rezero_draft_runner import DEFAULT_API, goi  # noqa: E402
from rclone_archive_copy import rclone_copy, rclone_verify  # noqa: E402

VALID_RIGHTS_MODES = ("REFERENCE_ONLY", "EMBED_ONLY", "REHOST_ALLOWED")
VOICE_ID = "piper:ngochuyennew"

#: Goc COLD-archive tren Google Drive cho video da RENDER XONG (final, khong
#: phai raw). CO Y tach rieng khoi `server/scraper/raw_archive.py::DRIVE_ARCHIVE_REMOTE`
#: ("archive/scraping/raw") — do la spool response THO truoc xu ly; day la
#: SAN PHAM CUOI CUNG sau render, ban chat khac han nen goc khac han, xem
#: `archive_final_render()` duoi day.
DRIVE_FINAL_MEDIA_REMOTE = "fanfic-gdrive:FanficWorld/archive/final/rendered"

#: Content-Type theo duoi tep — chi hai dinh dang render thuc te dung
#: (mkv/mp4); dinh dang khac roi ve octet-stream thay vi doan sai.
_RENDER_CONTENT_TYPES = {
    ".mkv": "video/x-matroska",
    ".mp4": "video/mp4",
}

#: `slug` trong `archive_final_render()` bi noi truc tiep vao ca R2 key
#: lan duong dan Google Drive remote (qua rclone) — allowlist chat de
#: chan path traversal ("..", "/", "\\") va ky tu la tren nhanh rclone
#: Drive (rclone coi day la thanh phan duong dan that, khac R2 key chi
#: la chuoi). Chi chu thuong/so, noi bang "-", khong dau "-" o dau/cuoi.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _agy_binary() -> str:
    """Absolute path to the `agy` (Antigravity) CLI. Real, observed defect
    (2026-09-02): bare "agy" resolves fine in some execution contexts (an
    interactive shell with the right PATH) but NOT in a plain
    subprocess.run(["agy", ...]) from a background-task process, which
    raises FileNotFoundError - a genuinely different failure than the
    "command" permission denial this module also guards against (see
    translate_zh_to_vi()'s prompt). Same resolve-fresh-every-call pattern
    as `_fanficfare_binary()` in server/scraper/fanficfare_provider.py -
    PATH first, known install location as fallback, never assume."""
    found = shutil.which("agy")
    if found:
        return found
    local_candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"
    if local_candidate.is_file():
        return str(local_candidate)
    return "agy"  # last resort - let subprocess raise its own clear error


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
    # Ro rang cam agy tu goi cong cu/lenh nao: voi payload lon (vd 1147
    # doan That), agy tu y muon chay "python -c ..." de tu kiem tra hieu
    # dung cua no truoc khi tra loi - o che do headless khong co ai xac
    # nhan quyen "command" nay, bi tu choi, va toan bo dich That bai
    # (ValueError "no JSON array in agy output", da xac minh That qua
    # C:\Users\nguye\.gemini\antigravity-cli\conversations\*.db, buoc
    # step_type=132: "permission check failed for command \"python -c
    # ...\""). Day KHONG PHAI mot buoc can thiet cho tac vu — chi la thoi
    # quen tu kiem tra cua agy. Cau nay chan No o goc, khong can mo them
    # bat ky permission/allow-rule nao trong settings.json cua agy — da
    # xac minh That: cung mot payload 1147 phan tu, chi them cau nay,
    # dich thanh cong 1147/1147, JSON hop le, khong con bi tu choi quyen.
    prompt = (
        "Dich cac cau tieng Trung sau sang tieng Viet. Tra ve DUY NHAT mot "
        "mang JSON cung do dai, cung thu tu, moi phan tu la ban dich tieng "
        "Viet tuong ung — khong giai thich them, khong danh so, khong bao "
        "boc trong markdown. KHONG duoc chay bat ky lenh/script/cong cu nao de "
        "kiem tra hay xac minh — day la mot yeu cau van ban thuan tuy, tra loi "
        "truc tiep bang JSON, khong goi cong cu nao ca.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(prompt)
        prompt_path = f.name
    try:
        with open(prompt_path, "r", encoding="utf-8") as stdin_f:
            result = subprocess.run(
                [_agy_binary(), "--print-timeout", timeout],
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


_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _parse_srt_timestamp(hh: str, mm: str, ss: str, ms: str) -> float:
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


def parse_srt(path: Path) -> List[Segment]:
    """Inverse of `write_srt()` — reconstructs `Segment`s (start/end/
    vi_text) from an already-written .srt so a re-dub can reuse a prior
    run's ASR+translation instead of repeating them (mission "FIX REAL
    CHINESE DUB COVERAGE", section 4: "Avoid repeating ASR/translation if
    unchanged"). `zh_text` is left empty — the .srt never carried it, and
    `dub_segments()` only reads `vi_text`/`start`/`end`."""
    blocks = path.read_text(encoding="utf-8").strip().split("\n\n")
    segments: List[Segment] = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        m = _SRT_TIME_RE.search(lines[1])
        if not m:
            continue
        start = _parse_srt_timestamp(*m.groups()[0:4])
        end = _parse_srt_timestamp(*m.groups()[4:8])
        text = "\n".join(lines[2:]).strip()
        segments.append(Segment(start=start, end=end, zh_text="", vi_text=text))
    return segments


# --------------------------------------------------------------------------
# Stage 5 (optional): Ngoc Huyen Moi dub.
#
# ROOT-CAUSE FIX (2026-09-02, "FIX REAL CHINESE DUB COVERAGE" mission): the
# previous version advanced its placement `cursor` by the ASSUMED source
# window length (`seg.end - seg.start`) instead of the synthesized audio's
# ACTUAL measured duration, and never verified `provider.synthesize()`
# actually produced usable output. On the real wikitongues_henan artifact
# this silently produced a dub covering only 32.9s of a 217.9s video
# (15.1%) — a real production defect caught by VisualMediaQA. Real proof
# this fix addresses it: docs/reports/dub-coverage-fix-2026-09-02.md.
#
# Fixed behavior, per segment:
#   1. Synthesize at natural rate (1.0).
#   2. MEASURE the actual rendered duration (ffprobe) — never assumed.
#   3. If it fits the source window: place as-is, cursor advances by the
#      real measured duration (not the window length) — self-correcting,
#      so a short/long segment never silently drifts every later segment.
#   4. If it overruns the window: retry at a bounded faster rate (capped
#      at MAX_DUB_RATE) rather than accepting arbitrarily fast speech.
#   5. If it STILL overruns after the rate cap: allow it to spill into
#      whatever real silence exists before the next segment's own start
#      time (never overlapping the next segment's speech). If the overrun
#      exceeds even that available slack, the segment is flagged
#      `needs_review=True` in the returned `List[DubSegmentResult]` —
#      placed anyway (better than silently dropped), but the caller can
#      gate on this list before DRAFT_READY.
#
# Returns per-segment diagnostics so a caller can compute real
# TTS_REQUESTED/TTS_SUCCEEDED/FINAL_DUB_SEGMENTS counts — see
# `dub_coverage_metrics()` below.
# --------------------------------------------------------------------------

#: A segment that would need to speed up MORE than this to fit its source
#: window instead spills into adjacent silence (or is flagged for review)
#: rather than being sped up further — "do not create absurdly fast speech
#: just to fit a short interval" (mission requirement, section 2).
MAX_DUB_RATE = 1.3


@dataclass
class DubSegmentResult:
    index: int
    requested: bool  # non-empty vi_text -> a synthesis attempt was made
    synth_ok: bool = False
    actual_duration: float = 0.0
    window_duration: float = 0.0
    rate_used: float = 1.0
    placed_start: float = 0.0
    overrun_seconds: float = 0.0
    needs_review: bool = False
    reason: str = ""


def _probe_audio_duration(path: Path, ffmpeg: str) -> float:
    """Real measured duration via ffprobe (sits next to `ffmpeg` in the
    same install — same discovery the caller already used for `ffmpeg`
    itself, so no new binary dependency)."""
    ffprobe = str(Path(ffmpeg).with_name(
        Path(ffmpeg).name.replace("ffmpeg", "ffprobe")))
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def dub_segments(
    segments: List[Segment], out_path: Path, ffmpeg: str, *,
    max_rate: float = MAX_DUB_RATE,
) -> List[DubSegmentResult]:
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
    results: List[DubSegmentResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        concat_list = tmp_dir / "concat.txt"
        entries = []
        cursor = 0.0
        for i, seg in enumerate(segments):
            window = seg.end - seg.start
            result = DubSegmentResult(
                index=i, requested=bool(seg.vi_text.strip()), window_duration=window)

            gap = max(0.0, seg.start - cursor)
            if gap > 0.02:
                silence = tmp_dir / f"gap_{i}.wav"
                subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                               "-f", "lavfi", "-i", f"anullsrc=r=22050:cl=mono",
                               "-t", f"{gap:.3f}", str(silence)], check=True)
                entries.append(silence)
                cursor += gap

            if not result.requested:
                result.reason = "empty translated text"
                results.append(result)
                continue

            result.placed_start = cursor
            next_start = segments[i + 1].start if i + 1 < len(segments) else None

            try:
                seg_mp3 = tmp_dir / f"seg_{i}_r100.mp3"
                provider.synthesize(text=seg.vi_text, voice=voice, dest=seg_mp3, rate="1.0")
                actual = _probe_audio_duration(seg_mp3, ffmpeg)
                rate_used = 1.0

                if actual > window and window > 0:
                    needed_rate = min(actual / window, max_rate)
                    if needed_rate > 1.01:
                        sped_mp3 = tmp_dir / f"seg_{i}_sped.mp3"
                        provider.synthesize(text=seg.vi_text, voice=voice,
                                            dest=sped_mp3, rate=f"{needed_rate:.3f}")
                        sped_actual = _probe_audio_duration(sped_mp3, ffmpeg)
                        if sped_actual > 0:
                            seg_mp3, actual, rate_used = sped_mp3, sped_actual, needed_rate

                entries.append(seg_mp3)
                result.synth_ok = actual > 0
                result.actual_duration = actual
                result.rate_used = rate_used
                cursor += actual  # real measured duration, not the assumed window

                overrun = max(0.0, actual - window)
                if overrun > 0.05:
                    result.overrun_seconds = overrun
                    available_slack = (next_start - cursor) if next_start is not None else None
                    if available_slack is not None and available_slack < 0:
                        result.needs_review = True
                        result.reason = (
                            f"overran by {overrun:.2f}s even at rate={rate_used:.2f} "
                            f"and exceeded available silence before the next segment")
                    else:
                        result.reason = (
                            f"overran by {overrun:.2f}s at rate={rate_used:.2f}; "
                            f"spilled into adjacent silence, no collision")
            except Exception as exc:
                result.synth_ok = False
                result.needs_review = True
                result.reason = f"synthesize() raised: {type(exc).__name__}: {exc}"

            results.append(result)

        # SECOND real bug this fix addresses (found while rebuilding the
        # real wikitongues_henan dub): the concat DEMUXER (`-f concat`)
        # stream-copies its inputs — it requires every input to share
        # identical codec parameters. `entries` mixes raw PCM WAV silence
        # files with Piper's MP3 segment output; feeding that straight to
        # the demuxer produced "Invalid PCM packet" decode errors and
        # silently truncated the real rebuild's output to 67s even though
        # per-segment diagnostics showed all 55 segments correctly placed
        # through 217.6s. Fix: normalize every piece to the SAME WAV specs
        # the silence generator already uses (22050Hz mono PCM) before
        # concatenating, then encode to the final format once at the end —
        # the demuxer only ever sees uniform input.
        normalized: List[Path] = []
        for idx, e in enumerate(entries):
            if e.suffix.lower() == ".wav":
                normalized.append(e)
                continue
            norm = tmp_dir / f"norm_{idx}.wav"
            subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                           "-i", str(e), "-ar", "22050", "-ac", "1", str(norm)], check=True)
            normalized.append(norm)

        with open(concat_list, "w", encoding="utf-8") as f:
            for e in normalized:
                f.write(f"file '{e.as_posix()}'\n")
        concat_wav = tmp_dir / "concat_out.wav"
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                       "-f", "concat", "-safe", "0", "-i", str(concat_list),
                       str(concat_wav)], check=True)
        subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                       "-i", str(concat_wav), str(out_path)], check=True)

    placed = sum(1 for r in results if r.synth_ok)
    review = sum(1 for r in results if r.needs_review)
    print(f"[dub] wrote {out_path} ({out_path.stat().st_size} bytes, "
          f"target length ~{total_end:.1f}s) — {placed}/{len(results)} segments placed, "
          f"{review} flagged for review")
    return results


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

    # Idempotent lookup BEFORE creating anything: a placeholder Novel for
    # this exact source may already exist (e.g. ship_video_drafts_runner.py
    # created it earlier with subtitle_status=PENDING_SOURCE, no subtitle/dub
    # yet). Same GET/keying pattern as ship_video_drafts_runner.py and
    # mission_g_rezero_draft_runner.py — keyed on external_source_url, the
    # canonical identity used everywhere in this codebase for this purpose.
    # Reusing it here (instead of always POSTing) is the actual fix for the
    # real, disclosed duplicate Appwrite document this mission hit in
    # production.
    if source_url:
        ma, r = goi(DEFAULT_API, "GET", "/api/novels?mine=true&limit=200", token=token)
        if ma != 200:
            raise RuntimeError(f"GET /api/novels?mine=true -> {ma}: {r}")
        existing = next(
            (n for n in r.get("novels", []) if n.get("external_source_url") == source_url),
            None,
        )
        if existing:
            novel_id = existing["novel_id"]
            ma, r = goi(DEFAULT_API, "PATCH", f"/api/novels/{novel_id}/media-processing", {
                "subtitle_key": subtitle_key,
                "dub_audio_key": dub_key,
                "subtitle_status": "READY",
            }, token=token)
            if ma != 200:
                raise RuntimeError(f"PATCH /api/novels/{novel_id}/media-processing -> {ma}: {r}")
            return novel_id

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


# --------------------------------------------------------------------------
# Final-render archival (mission "Persist the one real QA_PASS rendered
# video", 2026-09-02). NOT part of the ASR/translate/dub/compose chain above
# — those stages are FROZEN and untouched. This is a separate, additive
# step a caller runs AFTER `compose_with_source()` (or any other already-
# finished REHOST_ALLOWED render) has produced ONE local video file, to
# durably persist it: a HOT copy on R2 (served/downloaded from) + a COLD
# copy on Google Drive (disaster-recovery), plus a sha256 checksum + size
# recorded on the Novel so the archive can be verified later without
# re-deriving anything. Never touches disposable pipeline intermediates
# (temp audio, per-segment TTS files, ASR working files) — it only ever
# sees the one finished `local_render_path` a caller hands it.
# --------------------------------------------------------------------------


def _sha256_and_size(path: Path, chunk_size: int = 1024 * 1024) -> Tuple[str, int]:
    """Streamed sha256 + byte count — never loads the whole file into
    memory (the real backfill target is ~47MB; this scales to much larger
    files the same way)."""
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def archive_final_render(*, local_render_path: Path, novel_id: str,
                         slug: str, token: str) -> Dict:
    """Archive ONE already-finished rendered video for a REHOST_ALLOWED
    Novel (the caller is responsible for having already verified those
    rights — this function does not re-check `rights_mode`).

    Order of operations:
      1. sha256 + size of `local_render_path` (streamed, see
         `_sha256_and_size`).
      2. HOT copy to R2 via `upload_to_r2()` at a CONTENT-ADDRESSED key —
         `rendered_media/svc_harvester/{slug}-{sha256[:16]}{ext}` — never a
         random suffix (unlike `ship_draft()`'s subtitle/dub keys): the key
         is a pure function of (slug, file content), so a re-run with the
         identical file reproduces the identical key and overwrites the
         same R2 object instead of creating a new one.
      3. COLD copy to Google Drive under `DRIVE_FINAL_MEDIA_REMOTE`, one
         subdirectory per (slug, content) — same content-addressing, same
         idempotency reasoning. Reuses `rclone_archive_copy.rclone_copy`/
         `rclone_verify` (copy-only, never sync/move/delete/purge — see
         that module's own docstring); `rclone copy <single-file>
         <remote-dir>` places the file at `<remote-dir>/<basename>` (rclone
         treats a file source + directory dest as "copy into it" — verified
         locally against a real rclone binary before relying on it here),
         so no separate local staging directory is needed.
      4. A REAL Google Drive file id, parsed from the `lsjson` output
         `rclone_verify()` already fetched (no extra rclone call) — NOT a
         path string. Confirmed against this repo's own already-
         authenticated `fanfic-gdrive:` remote (Google Drive backend) that
         `lsjson` DOES expose a real "ID" field for every entry (checked
         2026-09-02 by listing the existing raw-source archive root — every
         file and directory carried one, e.g.
         "ID":"1Wvrc5KNkz8LFQJapogj49wlXtGynno-a"). The fallback below
         (storing the remote directory path itself) exists only for a
         differently-configured rclone backend that doesn't expose Drive
         ids — it is documented but has never actually been exercised
         against this repo's real remote.
      5. PATCH /api/novels/{novel_id}/media-processing with EXACTLY
         `rendered_media_key`/`rendered_archive_file_id`/
         `rendered_checksum`/`rendered_size_bytes`. Deliberately does NOT
         set `qa_state` — QA verdict is the caller's own decision, set
         separately (same or a follow-up PATCH call).

    IDEMPOTENT by construction: re-running with the identical local file
    recomputes the identical sha256, therefore the identical R2 key and
    the identical Drive remote directory, so both uploads are safe
    overwrites of the same objects (never a new/duplicate object), and the
    PATCH re-writes the Novel with the same values — a safe no-op re-write,
    never a second Novel record.
    """
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"slug khong hop le: {slug!r} — chi cho phep chu thuong/so, noi "
            f"bang '-', khong dau '-' o dau/cuoi (chan path traversal khi "
            f"noi vao R2 key va duong dan Google Drive)"
        )

    local_render_path = Path(local_render_path)
    sha256_hex, size_bytes = _sha256_and_size(local_render_path)

    ext = local_render_path.suffix.lower() or ".mp4"
    content_type = _RENDER_CONTENT_TYPES.get(ext, "application/octet-stream")
    r2_key = f"rendered_media/svc_harvester/{slug}-{sha256_hex[:16]}{ext}"
    upload_to_r2(r2_key, local_render_path.read_bytes(), content_type)

    drive_remote_dir = f"{DRIVE_FINAL_MEDIA_REMOTE}/{slug}-{sha256_hex[:16]}"
    copy_result = rclone_copy(str(local_render_path), drive_remote_dir)
    if copy_result["exit_code"] != 0:
        raise RuntimeError(
            f"rclone copy to {drive_remote_dir} failed "
            f"(exit={copy_result['exit_code']}): {copy_result['stderr_tail']}"
        )
    verify_result = rclone_verify(str(local_render_path), drive_remote_dir)
    if verify_result["check_exit_code"] != 0:
        raise RuntimeError(
            f"rclone check against {drive_remote_dir} failed "
            f"(exit={verify_result['check_exit_code']}): "
            f"{verify_result['check_stderr_tail']}"
        )

    # See docstring point 4: real Drive file id when the backend exposes
    # one, else the remote directory path as a documented fallback.
    drive_file_id = drive_remote_dir
    try:
        entries = json.loads(verify_result.get("lsjson") or "[]")
        match = next(
            (e for e in entries
             if e.get("Name") == local_render_path.name and not e.get("IsDir")),
            None,
        )
        if match and match.get("ID"):
            drive_file_id = match["ID"]
    except (json.JSONDecodeError, TypeError):
        pass

    ma, r = goi(DEFAULT_API, "PATCH", f"/api/novels/{novel_id}/media-processing", {
        "rendered_media_key": r2_key,
        "rendered_archive_file_id": drive_file_id,
        "rendered_checksum": sha256_hex,
        "rendered_size_bytes": size_bytes,
    }, token=token)
    if ma != 200:
        raise RuntimeError(
            f"PATCH /api/novels/{novel_id}/media-processing -> {ma}: {r}")

    return {
        "novel_id": novel_id,
        "r2_key": r2_key,
        "drive_remote_dir": drive_remote_dir,
        "drive_file_id": drive_file_id,
        "sha256": sha256_hex,
        "size_bytes": size_bytes,
        "content_type": content_type,
    }


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
