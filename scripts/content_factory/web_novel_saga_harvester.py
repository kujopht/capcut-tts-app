"""Web Novel Saga Harvester & TTS Pipeline for Router V4.

Automates end-to-end harvesting of full-length, multi-chapter web fictions / novels:
1. Scrapes full chapter list from index URL (RoyalRoad, etc.).
2. Extracts full chapter text (thousands of words per chapter).
3. Translates to natural, fluent, literary Vietnamese via Gemini 3.8 Flash (agy multi-account pool).
4. Synthesizes crystal-clear audio with Piper TTS Ngoc Huyen (NghiTTS).
5. Generates millisecond-accurate synchronized transcript (.srt & .json).
6. Generates cover art and rich metadata.json.
7. Syncs completed chapters directly to Google Drive.
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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

from bs4 import BeautifulSoup

from scripts.content_factory.cover_generator import generate_novel_cover
from scripts.content_factory.gemini_evaluator import (
    call_gemini,
    generate_fanfic_world_metadata,
    translate_text,
)
from scripts.content_factory.naming import make_production_name, make_production_slug
from scripts.content_factory.worker2_text_fanfic import (
    LOCAL_SPOOL_DIR,
    _format_srt_time,
    _probe_duration,
    create_placeholder_cover,
    split_sentences_for_transcript,
    sync_to_google_drive,
    synthesize_with_synchronized_transcript,
)

DEFAULT_RR_URL = "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan"
OVERNIGHT_LOG = PROJECT_ROOT / "raw_spool" / "overnight_runner.log"


def log_runner(msg: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [NHÁNH 2 - SAGA DÀI] {msg}"
    print(line)
    try:
        OVERNIGHT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(OVERNIGHT_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def scrape_royalroad_fiction_metadata(fiction_url: str) -> Dict[str, Any]:
    """Extracts fiction metadata and all chapter links from a RoyalRoad fiction page."""
    cmd = [
        "curl.exe", "-s", "-L", "--max-time", "15",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        fiction_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"Không thể tải trang truyện {fiction_url}: {proc.stderr}")

    soup = BeautifulSoup(proc.stdout, "html.parser")
    title_el = soup.find("h1")
    title = title_el.text.strip() if title_el else "Unknown Fiction"

    author_el = soup.find("h4", class_="font-white")
    author = author_el.text.strip() if author_el else "RoyalRoad Author"

    desc_el = soup.find("div", class_="description")
    desc = desc_el.text.strip() if desc_el else ""

    cover_el = soup.find("img", class_="thumbnail") or soup.find("img", class_="inline-block")
    cover_url = ""
    if cover_el and cover_el.get("src"):
        src = cover_el.get("src")
        cover_url = src if src.startswith("http") else f"https://www.royalroad.com{src}"

    links = []
    seen = set()
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and "/chapter/" in href and href not in seen:
            seen.add(href)
            ch_name = a.text.strip()
            full_url = href if href.startswith("http") else f"https://www.royalroad.com{href}"
            links.append({"title": ch_name or f"Chương {len(links)+1}", "url": full_url})

    return {
        "title": title,
        "author": author,
        "description": desc,
        "cover_url": cover_url,
        "chapters": links,
        "source_url": fiction_url,
    }


def scrape_royalroad_chapter_content(chapter_url: str) -> Tuple[str, str]:
    """Extracts chapter title and cleaned text content from a RoyalRoad chapter page."""
    cmd = [
        "curl.exe", "-s", "-L", "--max-time", "15",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        chapter_url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"Lỗi khi cào chương {chapter_url}: {proc.stderr}")

    soup = BeautifulSoup(proc.stdout, "html.parser")
    title_el = soup.find("h1")
    title = title_el.text.strip() if title_el else "Chương"

    content_div = soup.find("div", class_="chapter-content")
    if not content_div:
        raise RuntimeError(f"Không tìm thấy vùng nội dung .chapter-content ở {chapter_url}")

    text = content_div.get_text("\n\n").strip()
    return title, text


def translate_long_chapter_to_vietnamese(
    chapter_text: str,
    fandom: str = "Naruto",
    context_notes: str = "",
    max_chunk_words: int = 1500,
) -> str:
    """Translates a full-length chapter to fluent Vietnamese, chunking if necessary."""
    words = chapter_text.split()
    if len(words) <= max_chunk_words:
        return translate_text(
            chapter_text,
            target_lang="vi",
            context_notes=f"Fandom: {fandom}. {context_notes}. Văn phong tiểu thuyết hấp dẫn, tự nhiên.",
        )

    # Chunk into digestible sections of ~1200 words at paragraph boundaries
    paragraphs = chapter_text.split("\n\n")
    chunks = []
    curr = []
    curr_len = 0

    for p in paragraphs:
        p_len = len(p.split())
        if curr_len + p_len > max_chunk_words and curr:
            chunks.append("\n\n".join(curr))
            curr = [p]
            curr_len = p_len
        else:
            curr.append(p)
            curr_len += p_len
    if curr:
        chunks.append("\n\n".join(curr))

    translated_chunks = []
    for idx, c in enumerate(chunks, 1):
        log_runner(f"Đang dịch phân đoạn {idx}/{len(chunks)} ({len(c.split())} từ)...")
        vi_chunk = translate_text(
            c,
            target_lang="vi",
            context_notes=f"Fandom: {fandom}. Phần {idx}/{len(chunks)} của chương. {context_notes}",
        )
        translated_chunks.append(vi_chunk.strip())

    return "\n\n".join(translated_chunks)


def harvest_novel_saga(
    fiction_url: str = DEFAULT_RR_URL,
    start_chapter: int = 1,
    max_chapters: int = 30,
    fandom_hint: str = "Naruto",
    auto_sync: bool = True,
) -> Dict[str, Any]:
    """Harvests multiple chapters of a full novel, translates, and generates TTS packages."""
    log_runner(f"Bắt đầu thu thập bộ tiểu thuyết dài từ: {fiction_url}")
    meta = scrape_royalroad_fiction_metadata(fiction_url)
    all_ch = meta.get("chapters", [])
    log_runner(f"Tìm thấy tổng cộng {len(all_ch)} chương của bộ truyện: '{meta['title']}' (Tác giả: {meta['author']})")

    if not all_ch:
        raise RuntimeError("Không tìm thấy chương nào trong mục lục truyện.")

    selected_chapters = all_ch[start_chapter - 1 : start_chapter - 1 + max_chapters]
    completed = []

    for idx, ch_info in enumerate(selected_chapters, start=start_chapter):
        log_runner(f"\n=== ĐANG XỬ LÝ CHƯƠNG {idx}/{len(all_ch)}: '{ch_info['title']}' ===")
        ch_raw_title, ch_raw_text = scrape_royalroad_chapter_content(ch_info["url"])
        raw_words = len(ch_raw_text.split())
        log_runner(f"Đã cào văn bản gốc chương {idx}: {raw_words} từ tiếng Anh")

        # Standardized production naming
        clean_novel_title = meta["title"]
        if ":" in clean_novel_title:
            clean_novel_title = clean_novel_title.split(":")[0].strip()
        prod_name = make_production_name(fandom=fandom_hint, title=meta["title"], part_num=idx, default_part_type="Chương")
        slug = make_production_slug(fandom=fandom_hint, title=meta["title"], default_part_type=f"c{idx:02d}")
        work_dir = LOCAL_SPOOL_DIR / prod_name

        if (work_dir / "audio.mp3").exists() and (work_dir / "transcript.srt").exists():
            log_runner(f"Chương {idx} đã hoàn tất từ trước trong spool. Bỏ qua.")
            completed.append(prod_name)
            continue

        work_dir.mkdir(parents=True, exist_ok=True)
        (work_dir / "source_en.txt").write_text(ch_raw_text, encoding="utf-8")

        # Translate to Vietnamese via Gemini
        log_runner(f"Gemini 3.8 Flash đang dịch chương {idx} sang văn phong tiểu thuyết tiếng Việt...")
        vi_story = translate_long_chapter_to_vietnamese(
            ch_raw_text,
            fandom=fandom_hint,
            context_notes=f"Bộ truyện: {meta['title']}, Chương {idx}",
        )
        (work_dir / "story_vi.txt").write_text(vi_story, encoding="utf-8")
        vi_words = len(vi_story.split())
        log_runner(f"Đã dịch xong chương {idx}: {vi_words} từ tiếng Việt")

        # Split into sentences for Piper TTS
        sentences = split_sentences_for_transcript(vi_story)
        log_runner(f"Đã phân rã chương {idx} thành {len(sentences)} câu thoại. Bắt đầu tổng hợp TTS Ngọc Huyền...")

        # Run Piper TTS
        master_audio, srt_path, json_path = synthesize_with_synchronized_transcript(sentences, work_dir, rate="1.0")
        dur_s = _probe_duration(master_audio)
        dur_m = round(dur_s / 60, 1)
        log_runner(f"✅ Hoàn tất audio chương {idx}: {dur_s:.1f}s (~{dur_m} phút)")

        # Create cover
        cover_path = work_dir / "cover.jpg"
        if not cover_path.exists():
            generate_novel_cover(
                title=clean_novel_title,
                author=meta["author"],
                fandom=fandom_hint,
                chapter_label=f"Chương {idx:02d}",
                output_path=cover_path,
                base_art_url=meta.get("cover_url"),
            )

        # Generate fanfic.world metadata
        meta_data = generate_fanfic_world_metadata(
            title=f"{clean_novel_title} - Chương {idx:02d}",
            text_context=vi_story[:1000],
            author=meta["author"],
            source_url=ch_info["url"],
            fandom_hint=fandom_hint,
        )
        meta_data.update({
            "chapter_index": idx,
            "total_chapters": len(all_ch),
            "novel_title": meta["title"],
            "duration_seconds": dur_s,
            "duration_minutes": dur_m,
            "word_count": vi_words,
            "voice": "piper:ngochuyennew",
            "source_platform": "RoyalRoad / Web Novel",
            "source_url": ch_info["url"],
            "slug": slug,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })
        (work_dir / "metadata.json").write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Google Drive Sync
        if auto_sync:
            try:
                sync_to_google_drive(work_dir, slug)
                log_runner(f"Đã đồng bộ chương {idx} lên Google Drive!")
            except Exception as e:
                log_runner(f"Lỗi đồng bộ Drive chương {idx}: {e}")

        completed.append(prod_name)

    log_runner(f"🎉 ĐÃ HOÀN TẤT BỘ TIỂU THUYẾT: {len(completed)} chương ({fiction_url})")
    return {
        "status": "SUCCESS",
        "novel_title": meta["title"],
        "chapters_processed": len(completed),
        "fandom": fandom_hint,
    }


def main():
    parser = argparse.ArgumentParser(description="Web Novel Saga Harvester & TTS Pipeline")
    parser.add_argument("--url", default=DEFAULT_RR_URL, help="RoyalRoad or Web Fiction URL")
    parser.add_argument("--start", type=int, default=1, help="Start chapter number")
    parser.add_argument("--max-chapters", type=int, default=10, help="Max chapters to process")
    parser.add_argument("--fandom", default="Naruto", help="Fandom hint")
    parser.add_argument("--no-sync", action="store_true", help="Skip Google Drive sync")
    args = parser.parse_args()

    harvest_novel_saga(
        fiction_url=args.url,
        start_chapter=args.start,
        max_chapters=args.max_chapters,
        fandom_hint=args.fandom,
        auto_sync=not args.no_sync,
    )


if __name__ == "__main__":
    main()
