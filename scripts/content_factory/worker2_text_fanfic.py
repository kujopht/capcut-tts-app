"""Worker 2: Raw Fanfic Scraper & Audio Novel Factory.

Pipeline:
1. Ingest raw text via FanFicFare URL, local file, or Gemini 3.8 Flash curation.
2. Quality filter via Gemini 3.8 Flash (Threshold >= 7.5).
3. Translate / polish into fluent Vietnamese novel style.
4. Synthesize voiceover using Ngoc Huyen (NghiTTS / Piper).
5. Generate millisecond-accurate synchronized transcript (.srt, .json).
6. Package & auto-sync to Google Drive `FanficWorld/production/works/fanfic-tts/<slug>`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess


from desktop_app.providers.base import Voice
from desktop_app.providers.piper_models import PiperModelManager
from desktop_app.providers.piper_provider import PiperLocalProvider
from desktop_app.text_chunker import chunk_text
from scripts.content_factory.cloud_tts_client import synthesize_cloud_tts
from scripts.content_factory.gemini_evaluator import (
    DEFAULT_MODEL,
    QUALITY_THRESHOLD,
    call_gemini,
    evaluate_content,
    generate_fanfic_world_metadata,
    translate_text,
)
from scripts.content_factory.cover_generator import generate_novel_cover
from scripts.content_factory.naming import make_production_name, make_production_slug

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/fanfic-tts"
LOCAL_SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "fanfic_tts"


def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:60].strip("-") or "fanfic-novel"


def _format_srt_time(seconds: float) -> str:
    ms_total = round(seconds * 1000)
    hh, rem = divmod(ms_total, 3_600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _probe_duration(media_path: Path) -> float:
    """Probes exact audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(media_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(proc.stdout.strip())


def scrape_via_fanficfare(url: str, output_dir: Path) -> Dict[str, Any]:
    """Scrapes raw fanfic using FanFicFare CLI."""
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Worker2] Đang cạo truyện từ URL: {url} bằng FanFicFare...")
    
    fff_bin = str(PROJECT_ROOT / ".venv" / "Scripts" / "fanficfare.exe")
    if not Path(fff_bin).exists():
        fff_bin = "fanficfare"
    cmd = [fff_bin, "-f", "txt", url]
    proc = subprocess.run(cmd, cwd=str(output_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
    
    txt_files = list(output_dir.glob("*.txt"))
    if not txt_files:
        raise RuntimeError(f"FanFicFare không tải được tệp txt nào: {proc.stderr or proc.stdout}")

    story_file = txt_files[0]
    content = story_file.read_text(encoding="utf-8", errors="replace")
    
    # Extract simple header metadata from fanficfare text output
    title_m = re.search(r"Title:\s*(.+)", content)
    author_m = re.search(r"Author:\s*(.+)", content)
    summary_m = re.search(r"Summary:\s*([\s\S]*?)(?:\n\n|\n[A-Z][a-z]+:)", content)

    title = title_m.group(1).strip() if title_m else story_file.stem
    author = author_m.group(1).strip() if author_m else "Tác giả mạng"
    summary = summary_m.group(1).strip() if summary_m else ""

    return {
        "title": title,
        "author": author,
        "summary": summary,
        "raw_text": content,
        "source_url": url,
    }


def curate_via_gemini(
    topic_prompt: str,
    chapter_num: int = 1,
    series_title: str = "",
    fandom_hint: str = "",
    previous_summary: str = "",
) -> Dict[str, Any]:
    """Curates or drafts an engaging fanfic chapter when starting from topic or prompt.
    
    Supports multi-chapter narrative continuity (Chương 01 -> Chương 02).
    """
    if chapter_num == 1:
        print(f"[Worker2] Gemini 3.8 Flash đang sáng tạo nội dung Chương 01 theo chủ đề: '{topic_prompt}'...")
        prompt = f"""Bạn là một tác giả tiểu thuyết đồng nhân (fanfic) đỉnh cao, chuyên viết trường thiên.
Hãy viết CHƯƠNG 01 chi tiết, kịch tính và cuốn hút dựa trên ý tưởng sau:
'{topic_prompt}'

Yêu cầu tác phẩm:
1. Đặt tiêu đề bộ truyện thật kêu, ấn tượng, chuẩn phong cách light novel/đồng nhân.
2. Xác định rõ Fandom và nhân vật chính.
3. Nội dung PHẢI ĐẠT 3500-5000 từ tiếng Việt. Viết chi tiết, không được tóm tắt hay bỏ qua cảnh nào. Bao gồm: cảnh mở đầu, xây dựng bối cảnh, phát triển tâm lý nhân vật, ít nhất 3 đoạn đối thoại dài sinh động, mô tả hành động chi tiết, và kết thúc bằng cliffhanger nghẹt thở.
4. Viết bằng tiếng Việt tự nhiên, mượt mà, đúng văn phong tiểu thuyết trường thiên hiện đại.
5. KHÔNG TÓM TẮT — mỗi chi tiết phải được viết đầy đủ như một chương sách thực sự.

BẮT BUỘC định dạng đầu ra theo cấu trúc:
[TITLE]: <Tiêu đề bộ truyện>
[AUTHOR]: <Bút danh tác giả>
[FANDOM]: <Tên fandom>
[SUMMARY]: <Tóm tắt 2 câu về sự kiện chương 1>
[CONTENT]:
<Nội dung chương 1 — tối thiểu 3500 từ...>
"""
    else:
        print(f"[Worker2] Gemini 3.8 Flash đang sáng tạo Chương {chapter_num:02d} nối tiếp bộ truyện '{series_title}'...")
        prompt = f"""Bạn là tác giả của bộ tiểu thuyết đồng nhân trường thiên '{series_title}' thuộc Fandom {fandom_hint}.
Chủ đề tác phẩm: '{topic_prompt}'
Tóm tắt diễn biến chương trước:
'{previous_summary}'

Nhiệm vụ: Viết tiếp CHƯƠNG {chapter_num:02d} với mạch truyện liền mạch, đẩy cao xung đột và phát triển tâm lý nhân vật.
Yêu cầu:
1. Nội dung PHẢI ĐẠT 3500-5000 từ tiếng Việt — viết đầy đủ như một chương sách thực sự, không được tóm tắt hay bỏ qua cảnh nào.
2. Bao gồm: diễn biến chính liên tiếp từ chương trước, ít nhất 3 đoạn đối thoại dài sinh động, mô tả cảm xúc & hành động chi tiết, và kết thúc hồi hộp để kéo người đọc sang chương tiếp.
3. Viết bằng tiếng Việt mượt mà, văn phong tiểu thuyết trường thiên, KHÔNG TÓM TẮT.

BẮT BUỘC định dạng đầu ra theo cấu trúc:
[TITLE]: {series_title}
[AUTHOR]: Fanfic World AI
[FANDOM]: {fandom_hint}
[SUMMARY]: <Tóm tắt 2 câu diễn biến chương này>
[CONTENT]:
<Nội dung chương {chapter_num} — tối thiểu 3500 từ...>
"""
    raw = call_gemini(prompt, model=DEFAULT_MODEL, timeout_seconds=180)
    
    title_m = re.search(r"\[TITLE\]:\s*(.+)", raw)
    author_m = re.search(r"\[AUTHOR\]:\s*(.+)", raw)
    fandom_m = re.search(r"\[FANDOM\]:\s*(.+)", raw)
    summary_m = re.search(r"\[SUMMARY\]:\s*(.+)", raw)
    content_idx = raw.find("[CONTENT]:")

    title = title_m.group(1).strip() if title_m else (series_title or "Đồng Nhân Tuyệt Phẩm")
    author = author_m.group(1).strip() if author_m else "Fanfic World AI"
    fandom = fandom_m.group(1).strip() if fandom_m else (fandom_hint or "Đồng Nhân")
    summary = summary_m.group(1).strip() if summary_m else ""
    content = raw[content_idx + len("[CONTENT]:"):].strip() if content_idx != -1 else raw

    return {
        "title": title,
        "author": author,
        "fandom": fandom,
        "summary": summary,
        "raw_text": content,
        "source_url": "curated_by_gemini",
    }


def split_sentences_for_transcript(text: str) -> List[str]:
    """Splits full text into natural, readable sentence segments for subtitling."""
    # Split paragraphs first
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    sentences: List[str] = []
    
    # Regex split by sentence boundaries (. ! ? ...)
    sentence_split_re = re.compile(r'(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ"\'“‘])')
    
    for para in paragraphs:
        # Ignore markdown headers
        if para.startswith("#"):
            continue
        parts = sentence_split_re.split(para)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # If a part is too long (> 150 chars), break gently by commas or conjunctions
            if len(part) > 160:
                sub_parts = re.split(r'(?<=,)\s+', part)
                sentences.extend([sp.strip() for sp in sub_parts if sp.strip()])
            else:
                sentences.append(part)

    return sentences


def synthesize_with_synchronized_transcript(
    sentences: List[str],
    output_dir: Path,
    rate: str = "1.0",
    voice_type: str = "BV074_streaming",
) -> Tuple[Path, Path, Path]:
    """Synthesizes all sentences with CapCut / Piper and builds millisecond-accurate transcripts.
    
    Returns (master_audio_path, srt_transcript_path, json_transcript_path).
    """
    manager = PiperModelManager()
    model = manager.find("ngochuyennew")
    provider = PiperLocalProvider(manager=manager) if model.installed else None
    voice = Voice(
        provider="piper",
        voice_key="ngochuyennew",
        engine_voice_id="ngochuyennew",
        display_name="Ngọc Huyền (Mới)",
        language="vi",
        installed=True,
    )

    temp_parts_dir = output_dir / "audio_parts"
    temp_parts_dir.mkdir(parents=True, exist_ok=True)

    concat_list_file = temp_parts_dir / "concat.txt"
    concat_lines = []

    srt_cues = []
    json_cues = []
    cursor_time = 0.0

    # Rate percentage for cloud TTS
    cloud_rate = "+0%"
    try:
        rate_val = float(rate)
        diff = int(round((rate_val - 1.0) * 100))
        cloud_rate = f"{diff:+d}%"
    except Exception:
        cloud_rate = "+0%"

    import concurrent.futures

    tasks = []
    for i, sentence in enumerate(sentences, start=1):
        clean_text = sentence.strip()
        if clean_text:
            part_mp3 = temp_parts_dir / f"part_{i:04d}.mp3"
            tasks.append((i, clean_text, part_mp3))

    def _synth_worker(item):
        idx, text, out_file = item
        if out_file.exists() and out_file.stat().st_size > 100:
            return idx, text, out_file, "cached"

        # 1. CapCut voices (BV...): Direct official CapCut API (Cô Gái Hoạt Ngôn / Nhỏ Ngọt Ngào)
        if voice_type.startswith("BV") or voice_type.startswith("multi_"):
            for retry in range(3):
                try:
                    from capcut_tts_api.client import CapCutClient
                    c = CapCutClient()
                    res = c.generate_speech([text], voice=voice_type, timeout=30.0)
                    import json as _json
                    payload = _json.loads(res["data"]["tasks"][0]["payload"])
                    sub = payload["audio_subtitles"][0]
                    url = sub.get("speech_url")
                    if url:
                        import requests as _req
                        r = _req.get(url, timeout=20)
                        if r.status_code == 200 and len(r.content) > 100:
                            out_file.write_bytes(r.content)
                            return idx, text, out_file, "capcut"
                except Exception:
                    time.sleep(1.0)
            return idx, text, out_file, "error"

        # 2. Piper / Non-CapCut voices: Offload to Lightning AI CPU Studio
        try:
            if synthesize_cloud_tts(text=text, voice=voice_type, dest_path=out_file, rate=cloud_rate, timeout=35.0):
                return idx, text, out_file, "cloud"
        except Exception:
            pass

        # 3. Tertiary: Fallback to local Piper ONNX
        if provider is not None:
            try:
                provider.synthesize(text=text, voice=voice, dest=out_file, rate=rate)
                return idx, text, out_file, "local"
            except Exception as exc:
                print(f"[Worker2] Cảnh báo: Lỗi tổng hợp câu {idx}: {exc}")
                return idx, text, out_file, "error"
        return idx, text, out_file, "error"

    # Parallel concurrent dispatch: Utilize all 4 vCPUs and 16GB RAM on Cloud Studio
    max_workers = 4
    cloud_count = 0
    local_count = 0

    print(f"[Worker2] Bắt đầu tổng hợp song song {len(tasks)} câu với {max_workers} luồng (Tận dụng toàn bộ 4 vCPUs & 16GB RAM Cloud)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_synth_worker, t) for t in tasks]
        done_cnt = 0
        for f in concurrent.futures.as_completed(futures):
            idx, text, out_file, src = f.result()
            done_cnt += 1
            if src == "cloud":
                cloud_count += 1
            elif src == "local":
                local_count += 1
            if done_cnt % 20 == 0 or done_cnt == len(tasks):
                print(f"[Worker2] Tiến độ song song: {done_cnt}/{len(tasks)} câu hoàn thành [Cloud: {cloud_count}, Local: {local_count}]...")

    # Chronologically build transcript and concat list
    for idx, clean_text, part_mp3 in tasks:
        if not part_mp3.exists() or part_mp3.stat().st_size < 100:
            continue
        duration = _probe_duration(part_mp3)

        start_time = cursor_time
        end_time = cursor_time + duration
        cursor_time = end_time

        # Format SRT Cue
        srt_cues.append(f"{idx}\n{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}\n{clean_text}\n")
        json_cues.append({
            "index": idx,
            "start": round(start_time, 3),
            "end": round(end_time, 3),
            "start_time": _format_srt_time(start_time),
            "end_time": _format_srt_time(end_time),
            "text": clean_text,
        })

        concat_lines.append(f"file '{part_mp3.resolve().as_posix()}'")

    print(f"[Worker2] Đã tổng hợp {len(tasks)} câu: {cloud_count} câu qua Lightning AI CPU Studio, {local_count} câu qua Local Piper.")
    concat_list_file.write_text("\n".join(concat_lines), encoding="utf-8")

    # Concatenate all parts into master audio
    master_audio = output_dir / "audio.mp3"
    print(f"[Worker2] Đang nối các đoạn audio thành tệp master: {master_audio.name}...")
    concat_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list_file),
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(master_audio),
    ]
    subprocess.run(concat_cmd, check=True)

    # Write SRT and JSON transcripts
    srt_path = output_dir / "transcript.srt"
    json_path = output_dir / "transcript.json"

    srt_path.write_text("\n".join(srt_cues), encoding="utf-8")
    json_path.write_text(json.dumps(json_cues, ensure_ascii=False, indent=2), encoding="utf-8")

    # Clean up parts
    try:
        shutil.rmtree(temp_parts_dir)
    except OSError:
        pass

    print(f"[Worker2] Đã tạo tệp audio hoàn chỉnh: {master_audio} ({cursor_time:.1f}s)")
    print(f"[Worker2] Đã tạo transcript đồng bộ: {srt_path.name} & {json_path.name}")

    return master_audio, srt_path, json_path


def create_placeholder_cover(
    title: str,
    author: str,
    output_path: Path,
    fandom: str = "General",
    chapter_label: str = "",
    base_art_path: Optional[Path | str] = None,
    base_art_url: Optional[str] = None,
    voice_name: str = "Cô Gái Hoạt Ngôn (CapCut)",
    series_art_dir: Optional[Path | str] = None,
) -> Path:
    """Generates an aesthetic novel cover image using Pillow & typography engine."""
    return generate_novel_cover(
        title=title,
        author=author,
        fandom=fandom,
        chapter_label=chapter_label,
        output_path=output_path,
        base_art_path=base_art_path,
        base_art_url=base_art_url,
        voice_name=voice_name,
        series_art_dir=series_art_dir,
    )


def sync_to_google_drive(local_dir: Path, slug: str) -> str:
    """Syncs completed novel package to Google Drive."""
    remote_path = f"{DRIVE_TARGET_BASE}/{slug}"
    print(f"[Worker2] Đang đồng bộ tác phẩm lên Google Drive: {remote_path}...")
    cmd = ["rclone", "copy", str(local_dir), remote_path]
    subprocess.run(cmd, check=True)
    print(f"[Worker2] Đồng bộ Drive hoàn tất: {remote_path}")
    return remote_path


def process_text_fanfic(
    source: str,
    min_score: float = QUALITY_THRESHOLD,
    auto_sync: bool = True,
    tts_rate: str = "1.0",
    chapters_per_series: int = 20,
) -> Dict[str, Any]:
    """Full execution pipeline for Worker 2 with multi-chapter series production."""
    # 1. Ingest content
    is_external = source.startswith("http://") or source.startswith("https://") or Path(source).is_file()

    if source.startswith("http://") or source.startswith("https://"):
        raw_data = scrape_via_fanficfare(source, LOCAL_SPOOL_DIR / "temp_scrape")
    elif Path(source).is_file():
        file_p = Path(source)
        text = file_p.read_text(encoding="utf-8", errors="replace")
        raw_data = {
            "title": file_p.stem,
            "author": "Bản địa",
            "summary": text[:200],
            "raw_text": text,
            "source_url": str(file_p),
        }
    else:
        # Topic or creative prompt
        raw_data = curate_via_gemini(source, chapter_num=1)

    # Skip rule: If external source has only 1 chapter and < 8000 words -> Skip immediately
    if is_external:
        word_count = len(raw_data["raw_text"].split())
        if word_count < 8000:
            print(f"[Worker2] Bỏ qua tác phẩm '{raw_data['title']}': Truyện chỉ có {word_count} từ, chưa đạt chuẩn bộ truyện dài kỳ (yêu cầu >= 8.000 từ / nhiều chương).")
            return {
                "status": "SKIPPED",
                "title_vi": raw_data["title"],
                "reason": f"Truyện quá ngắn ({word_count} từ < 8000 từ)",
            }

    # 2. Quality Evaluation via Gemini 3.8 Flash
    eval_res = evaluate_content(
        title=raw_data["title"],
        description_or_snippet=raw_data["raw_text"][:2500],
        source_type="text_novel",
        threshold=min_score,
    )
    print(f"[Worker2] Đánh giá tác phẩm: Điểm {eval_res.score}/10 (Duyệt: {eval_res.approved})")
    if not eval_res.approved:
        raise RuntimeError(f"Tác phẩm không đạt ngưỡng chất lượng ({eval_res.score} < {min_score}). Lý do: {eval_res.reasoning}")

    fandom = eval_res.fandom or "Naruto"
    series_title = raw_data["title"]
    completed_chapters: List[Dict[str, Any]] = []

    last_summary = raw_data.get("summary", "")
    current_chapter_data = raw_data

    target_chapters = 1 if is_external else max(1, chapters_per_series)
    print(f"[Worker2] Chuẩn bị sản xuất bộ truyện gồm {target_chapters} chương liên tiếp...")

    last_prod_name = ""
    last_slug = ""
    last_metadata = {}
    last_work_dir = None
    last_drive_path = None
    total_audio_duration = 0.0

    # Shared series-level art directory: 1 base_art.png chung cho toàn bộ series
    # Đặt trong LOCAL_SPOOL_DIR/_series_art/<series_slug>/ để không xung đột với chapter dirs
    _series_art_slug = make_production_slug(fandom=eval_res.fandom or "Fanfic", title=series_title, part="art", default_part_type="art")
    series_art_dir = LOCAL_SPOOL_DIR / "_series_art" / _series_art_slug
    series_art_dir.mkdir(parents=True, exist_ok=True)

    # 3. Produce each chapter in the series
    for ch_idx in range(1, target_chapters + 1):
        if ch_idx > 1:
            # Curate consecutive chapter continuing from previous
            current_chapter_data = curate_via_gemini(
                topic_prompt=source,
                chapter_num=ch_idx,
                series_title=series_title,
                fandom_hint=fandom,
                previous_summary=last_summary,
            )
            last_summary = current_chapter_data.get("summary", "")

        print(f"\n[Worker2] === Đang xử lý Chương {ch_idx:02d}/{target_chapters:02d}: '{current_chapter_data['title']}' ===")

        prod_name = make_production_name(fandom=fandom, title=series_title, part_num=ch_idx, default_part_type="Chương")
        slug = make_production_slug(fandom=fandom, title=series_title, part=f"c{ch_idx:02d}", default_part_type="c")
        work_dir = LOCAL_SPOOL_DIR / prod_name
        work_dir.mkdir(parents=True, exist_ok=True)

        # Smart Resumption: Skip already completed chapters with valid audio
        audio_file = work_dir / "audio.mp3"
        meta_file = work_dir / "metadata.json"
        if audio_file.exists() and audio_file.stat().st_size > 10000 and meta_file.exists():
            print(f"[Worker2] ⏭️ Chương {ch_idx:02d} đã có sẵn và hoàn thiện ({audio_file.stat().st_size:,} bytes). Bỏ qua tổng hợp lại...")
            try:
                m_existing = json.loads(meta_file.read_text(encoding="utf-8"))
                ch_duration = m_existing.get("duration_seconds", 0) or _probe_duration(audio_file)
            except Exception:
                m_existing = {}
                ch_duration = _probe_duration(audio_file)
            total_audio_duration += ch_duration
            completed_chapters.append({
                "chapter": ch_idx,
                "folder_name": prod_name,
                "slug": slug,
                "title_vi": m_existing.get("title_vi", prod_name),
                "duration_seconds": ch_duration,
                "drive_path": None,
            })
            last_prod_name = prod_name
            last_slug = slug
            last_metadata = m_existing
            last_work_dir = work_dir
            continue

        story_text = current_chapter_data["raw_text"]
        # Translate or polish if foreign language detected
        is_foreign = len(re.findall(r"\b(the|and|is|was|in|to|he|she|it|that)\b", story_text[:500], re.IGNORECASE)) > 4
        if is_foreign:
            print(f"[Worker2] Phát hiện văn bản ngoại ngữ ở Chương {ch_idx}. Đang dịch sang tiếng Việt...")
            story_text = translate_text(story_text[:8000], context_notes=f"Fandom: {fandom}")

        # Save clean Vietnamese text
        story_txt_path = work_dir / "story_vi.txt"
        story_txt_path.write_text(story_text, encoding="utf-8")

        # Select voice according to user specification:
        # Fanfic -> Cô Gái Hoạt Ngôn (BV074_streaming)
        # Học đường lãng mạn -> Nhỏ Ngọt Ngào (BV421_vivn_streaming)
        is_school_romance = any(k in (source + " " + series_title + " " + fandom).lower() for k in [
            "học đường", "lãng mạn", "thanh xuân", "tình cảm", "school", "romance", "vườn trường", "ngọt sủng", "tình yêu"
        ])
        if is_school_romance:
            selected_voice = "BV421_vivn_streaming"
            voice_display_name = "Nhỏ Ngọt Ngào (CapCut)"
        else:
            selected_voice = "BV074_streaming"
            voice_display_name = "Cô Gái Hoạt Ngôn (CapCut)"

        # Split into sentences and synthesize with synchronized transcript
        sentences = split_sentences_for_transcript(story_text)
        print(f"[Worker2] Tách được {len(sentences)} câu thoại/dẫn truyện cho Chương {ch_idx}. Giọng đọc: {voice_display_name}")
        master_audio, srt_path, json_path = synthesize_with_synchronized_transcript(
            sentences, work_dir, rate=tts_rate, voice_type=selected_voice
        )
        ch_duration = _probe_duration(master_audio)
        total_audio_duration += ch_duration

        # Generate visual cover image — reuse series-level artwork across all chapters
        cover_path = work_dir / "cover.jpg"
        create_placeholder_cover(
            title=series_title,
            author=current_chapter_data["author"],
            output_path=cover_path,
            fandom=fandom,
            chapter_label=f"Chương {ch_idx:02d}",
            voice_name=voice_display_name,
            series_art_dir=series_art_dir,
        )

        # Generate rich metadata for fanfic.world
        metadata = generate_fanfic_world_metadata(
            title=f"{series_title} - Chương {ch_idx:02d}",
            text_context=story_text[:3000],
            author=current_chapter_data["author"],
            source_url=current_chapter_data.get("source_url", "https://fanfic.world/novel"),
            fandom_hint=fandom,
        )

        source_url = current_chapter_data.get("source_url") or "https://fanfic.world/novel"
        source_platform = "Web Fanfic Archive" if is_external else "Fanfic World AI Studio (Original Novel)"
        source_status = "Đang ra (Ongoing - Chờ cập nhật)" if target_chapters < 50 else "Full (Đã hoàn thành)"

        metadata.update({
            "folder_name": prod_name,
            "slug": slug,
            "title_original": series_title,
            "chapter_index": ch_idx,
            "chapter_total": target_chapters,
            "quality_score": eval_res.score,
            "evaluation_reasoning": eval_res.reasoning,
            "source_url": source_url,
            "source_author": current_chapter_data.get("author", "Tác giả mạng"),
            "source_platform": source_platform,
            "source_status": source_status,
            "latest_chapter_scraped": ch_idx,
            "voice_used": selected_voice,
            "voice_name": voice_display_name,
            "duration_seconds": ch_duration,
            "sentence_count": len(sentences),
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

        meta_file = work_dir / "metadata.json"
        meta_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        # Write dedicated source.txt
        source_file = work_dir / "source.txt"
        source_content = (
            f"=== THÔNG TIN NGUỒN GỐC TIỂU THUYẾT (FANFIC.WORLD) ===\n"
            f"Tác phẩm: {series_title}\n"
            f"Fandom: {fandom}\n"
            f"Tác giả gốc: {current_chapter_data.get('author', 'Tác giả mạng')}\n"
            f"Nền tảng / Nguồn phát hành: {source_platform}\n"
            f"Đường dẫn gốc (URL): {source_url}\n"
            f"Tình trạng tác phẩm: {source_status}\n"
            f"Chương hiện tại: Chương {ch_idx:02d} / {target_chapters:02d}\n"
            f"Giọng lồng tiếng: {voice_display_name}\n"
            f"Thời điểm thu thập: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Ghi chú fanfic.world: Lưu vết nguồn gốc để phục vụ ghi công (attribution) khi đăng tải lên web và tự động cập nhật các chương tiếp theo khi tác giả phát hành thêm.\n"
        )
        source_file.write_text(source_content, encoding="utf-8")

        # Sync to Google Drive
        drive_path = None
        if auto_sync:
            drive_path = sync_to_google_drive(work_dir, prod_name)

        ch_result = {
            "chapter": ch_idx,
            "folder_name": prod_name,
            "slug": slug,
            "title_vi": metadata["title_vi"],
            "duration_seconds": ch_duration,
            "drive_path": drive_path,
        }
        completed_chapters.append(ch_result)

        last_prod_name = prod_name
        last_slug = slug
        last_metadata = metadata
        last_work_dir = work_dir
        last_drive_path = drive_path

    return {
        "status": "SUCCESS",
        "folder_name": last_prod_name,
        "slug": last_slug,
        "title_vi": last_metadata.get("title_vi", series_title),
        "description_vi": last_metadata.get("description_vi", ""),
        "score": eval_res.score,
        "duration_seconds": round(total_audio_duration, 1),
        "chapters_count": len(completed_chapters),
        "chapters": completed_chapters,
        "voice": "Ngọc Huyền (NghiTTS)",
        "local_dir": str(last_work_dir) if last_work_dir else "",
        "drive_path": last_drive_path,
        "files": [f.name for f in last_work_dir.iterdir()] if last_work_dir else [],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker 2: Raw Fanfic Scraper & Audio Novel Factory")
    parser.add_argument("--source", "-s", type=str, help="URL, local file, or topic prompt", required=True)
    parser.add_argument("--min-score", type=float, default=QUALITY_THRESHOLD, help="Minimum quality score")
    parser.add_argument("--chapters", "-c", type=int, default=2, help="Number of chapters to produce for series")
    parser.add_argument("--rate", type=str, default="1.0", help="TTS speech rate multiplier")
    parser.add_argument("--no-sync", action="store_true", help="Skip Google Drive sync")
    args = parser.parse_args()

    res = process_text_fanfic(args.source, min_score=args.min_score, auto_sync=not args.no_sync, tts_rate=args.rate, chapters_per_series=args.chapters)
    print("\n" + "=" * 60)
    print(json.dumps(res, ensure_ascii=False, indent=2))

