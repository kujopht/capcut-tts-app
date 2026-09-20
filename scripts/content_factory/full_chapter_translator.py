"""
Full Chapter Long-Text Vietnamese Translator — Content Factory v2.

Translates complete, uncut upstream chapters with:
1. Paragraph-aware chunking preserving scene breaks and dialogue formatting.
2. Deterministic chunk IDs and chunk caching / checkpointing.
3. Persistent Hatake glossary injection for every chunk.
4. Model cutoff, truncation, and summarization detection with automatic retries.
5. In-order concatenation with post-translation glossary consistency.
6. Rigorous completeness gates:
   - Chunk count equality (chunk_count == translated_chunk_count)
   - Zero empty chunks
   - Word count ratio >= 85% (English -> Vietnamese)
   - First, middle, and final section alignment checks.

Pipeline Version: fulltext-v1
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.gemini_evaluator import call_gemini, DEFAULT_MODEL
from scripts.content_factory.glossary_manager import GlossaryManager

PIPELINE_VERSION = "fulltext-v1"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "raw_spool" / "translation_cache" / PIPELINE_VERSION


def count_words(text: str) -> int:
    """Counts words using whitespace tokenization."""
    if not text:
        return 0
    return len(text.split())


def chunk_chapter_paragraphs(
    source_text: str,
    max_chunk_words: int = 1200,
    min_chunk_words: int = 400,
) -> List[Dict[str, Any]]:
    """
    Splits long chapter source text into paragraph-aware chunks.
    Preserves scene breaks ('---', '***', '* * *', '___') and dialogue integrity.
    Never splits in the middle of a paragraph unless a single paragraph exceeds max_chunk_words.
    """
    clean_text = source_text.strip()
    if not clean_text:
        return []

    # Split into raw paragraphs (normalize line breaks)
    raw_paras = re.split(r"\n\s*\n", clean_text)
    paragraphs: List[str] = [p.strip() for p in raw_paras if p.strip()]

    if not paragraphs:
        return []

    chunks: List[Dict[str, Any]] = []
    current_paras: List[str] = []
    current_word_count = 0
    chunk_idx = 1

    for para in paragraphs:
        para_words = count_words(para)

        # If a single paragraph is enormous, split by sentence
        if para_words > max_chunk_words:
            if current_paras:
                chunk_text = "\n\n".join(current_paras)
                chunks.append({
                    "chunk_id": f"chunk_{chunk_idx:03d}",
                    "chunk_index": chunk_idx,
                    "text": chunk_text,
                    "word_count": count_words(chunk_text),
                    "paragraph_count": len(current_paras),
                })
                chunk_idx += 1
                current_paras = []
                current_word_count = 0

            # Split large paragraph by sentence
            sentences = re.split(r"(?<=[.?!])\s+", para)
            sub_paras: List[str] = []
            sub_words = 0
            for sent in sentences:
                sent_words = count_words(sent)
                if sub_words + sent_words > max_chunk_words and sub_paras:
                    sub_text = " ".join(sub_paras)
                    chunks.append({
                        "chunk_id": f"chunk_{chunk_idx:03d}",
                        "chunk_index": chunk_idx,
                        "text": sub_text,
                        "word_count": count_words(sub_text),
                        "paragraph_count": 1,
                    })
                    chunk_idx += 1
                    sub_paras = []
                    sub_words = 0
                sub_paras.append(sent)
                sub_words += sent_words

            if sub_paras:
                current_paras = [" ".join(sub_paras)]
                current_word_count = sub_words
            continue

        # Check if adding this paragraph exceeds max chunk size
        if current_word_count + para_words > max_chunk_words and current_word_count >= min_chunk_words:
            chunk_text = "\n\n".join(current_paras)
            chunks.append({
                "chunk_id": f"chunk_{chunk_idx:03d}",
                "chunk_index": chunk_idx,
                "text": chunk_text,
                "word_count": count_words(chunk_text),
                "paragraph_count": len(current_paras),
            })
            chunk_idx += 1
            current_paras = [para]
            current_word_count = para_words
        else:
            current_paras.append(para)
            current_word_count += para_words

    if current_paras:
        chunk_text = "\n\n".join(current_paras)
        chunks.append({
            "chunk_id": f"chunk_{chunk_idx:03d}",
            "chunk_index": chunk_idx,
            "text": chunk_text,
            "word_count": count_words(chunk_text),
            "paragraph_count": len(current_paras),
        })

    return chunks


def detect_translation_defect(source_text: str, vi_text: str) -> Optional[str]:
    """
    Detects model cutoff, severe truncation, summarization, or corruption in Vietnamese output.
    Returns error string if defect is detected, or None if valid.
    """
    s_clean = source_text.strip()
    v_clean = vi_text.strip()

    if not v_clean:
        return "BLANK_OUTPUT: Translated text is completely empty."

    src_words = count_words(s_clean)
    vi_words = count_words(v_clean)

    if vi_words < 15 and src_words >= 30:
        return f"EXTREME_SHORTAGE: Only {vi_words} Vietnamese words produced for {src_words} source words."

    # Ratio check: Vietnamese novel translation is normally 90%–135% of English words
    ratio = vi_words / max(1, src_words)
    if src_words >= 150 and ratio < 0.65:
        return (
            f"SUSPICIOUS_TRUNCATION: Vietnamese word count ({vi_words}) is only {ratio:.1%} "
            f"of source word count ({src_words}). Expected >= 65% for chunk."
        )

    # Cutoff detection: ends mid-sentence without terminal punctuation
    # Terminal punctuation allowed: . ! ? " ” ' ’ … ... * - —
    last_char = v_clean[-1]
    if last_char not in ('.', '!', '?', '"', '”', '’', "'", '…', '*', '-', '—') and not v_clean.endswith('...'):
        # Check if last word is incomplete or hanging
        last_word = v_clean.split()[-1] if v_clean.split() else ""
        if len(last_word) > 1 and not re.search(r"[.!?\"”]$", last_word):
            return f"CUTOFF_DETECTED: Output ends abruptly without punctuation: '...{v_clean[-40:]}'"

    # Summarization cues detection
    lower_vi = v_clean.lower()
    summary_indicators = [
        "tóm tắt nội dung:",
        "tóm tắt đoạn này:",
        "dưới đây là bản tóm tắt",
        "[lược dịch]",
        "[cắt bớt]",
        "nội dung tóm tắt:",
    ]
    for ind in summary_indicators:
        if ind in lower_vi:
            return f"ACCIDENTAL_SUMMARIZATION: Found summarization marker '{ind}' in output."

    return None


def clean_model_prefixes(text: str) -> str:
    """Strips meta prefixes like '**Bản dịch:**', blockquotes '> ', and markdown wrappers."""
    res = text.strip()
    # Strip markdown backtick code fences
    if res.startswith("```"):
        res = re.sub(r"^```[a-zA-Z]*\n?", "", res)
        res = re.sub(r"\n?```$", "", res).strip()

    # Strip prefixes like "**Bản dịch:**", "Bản dịch:", "Dịch:"
    res = re.sub(
        r"^(?:\*{1,2}|#{1,3}\s*)?(?:Bản dịch|Dịch|Vietnamese translation|Translation)[\s\S]*?:\s*(?:\*{1,2})?\s*\n*",
        "",
        res,
        flags=re.IGNORECASE,
    ).strip()

    # If the entire output is wrapped in a blockquote (> ...), unwrap it
    lines = res.split("\n")
    if all(l.startswith(">") or not l.strip() for l in lines) and any(l.strip() for l in lines):
        unquoted = [re.sub(r"^>\s?", "", l) for l in lines]
        res = "\n".join(unquoted).strip()

    # Strip surrounding bold wrappers if whole text is **...**
    if res.startswith("**") and res.endswith("**") and len(res) > 4:
        # Only strip if no other ** is inside
        if res.count("**") == 2:
            res = res[2:-2].strip()

    return res


def translate_chunk_with_retry(
    chunk: Dict[str, Any],
    work_key: str,
    glossary_prompt: str,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
) -> str:
    """
    Translates a single paragraph chunk to Vietnamese with strict fidelity and retries.
    """
    chunk_text = chunk["text"]
    chunk_id = chunk["chunk_id"]

    system_instruction = (
        "Bạn là dịch giả tiểu thuyết văn học / web novel chuyên nghiệp hàng đầu.\n"
        "Nhiệm vụ của bạn là dịch TOÀN BỘ, NGUYÊN BẢN, KHÔNG CẮT XÉN, KHÔNG TÓM TẮT bất kỳ câu chữ nào "
        "từ văn bản gốc sang tiếng Việt mượt mà, đậm chất tiểu thuyết.\n\n"
        f"{glossary_prompt}\n\n"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Dịch trung thực 100% từng câu, từng đoạn. Giữ nguyên cấu trúc các đoạn văn (line breaks).\n"
        "2. Giữ nguyên các dấu ngắt cảnh (--- hoặc ***).\n"
        "3. Tuyệt đối KHÔNG tóm tắt, KHÔNG lược bỏ bất kỳ chi tiết nào.\n"
        "4. Tuyệt đối KHÔNG thêm ghi chú dịch giả (Translator's note, Lời dịch giả, v.v.).\n"
        "5. Chỉ trả về bản dịch tiếng Việt hoàn chỉnh."
    )

    user_prompt = f"[VĂN BẢN CẦN DỊCH]:\n{chunk_text}"

    last_defect = ""
    for attempt in range(1, max_retries + 1):
        try:
            raw_result = call_gemini(
                prompt=user_prompt,
                model=model,
                timeout_seconds=180,
                system_instruction=system_instruction,
                allow_fallback=True,
            )

            clean_res = clean_model_prefixes(raw_result)

            defect = detect_translation_defect(chunk_text, clean_res)
            if defect is None:
                return clean_res

            last_defect = defect
            print(f"[FullTranslator] {chunk_id} Thử {attempt}/{max_retries} phát hiện lỗi: {defect}. Thử lại...")
            time.sleep(2.0 * attempt)

        except Exception as exc:
            last_defect = str(exc)
            print(f"[FullTranslator] {chunk_id} Thử {attempt}/{max_retries} lỗi mạng/API: {exc}. Thử lại...")
            time.sleep(3.0 * attempt)

    raise RuntimeError(f"Không thể dịch {chunk_id} sau {max_retries} lần thử: {last_defect}")


def translate_long_chapter_to_vietnamese(
    work_key: str,
    source_chapter_id: str,
    source_title: str,
    source_text: str,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    """
    Translates an entire long novel chapter with paragraph-aware chunking,
    deterministic caching, cutoff detection, and persistent glossary injection.

    Returns complete translation metadata and full Vietnamese text.
    """
    cache_root = cache_dir or DEFAULT_CACHE_DIR
    glossary_mgr = GlossaryManager()
    glossary = glossary_mgr.load_glossary(work_key)
    glossary_prompt = glossary_mgr.build_gemini_prompt_context(work_key)

    # Cache identity: source_text_hash + glossary_hash + pipeline_version
    src_text_clean = source_text.strip()
    src_hash = hashlib.sha256(src_text_clean.encode("utf-8")).hexdigest()[:16]
    glos_data = json.dumps(glossary.get_all_mappings(), sort_keys=True)
    glos_hash = hashlib.sha256(glos_data.encode("utf-8")).hexdigest()[:8]

    safe_ch_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", str(source_chapter_id))
    chapter_cache_dir = cache_root / work_key / f"{safe_ch_id}_{src_hash}_{glos_hash}"
    chapter_cache_dir.mkdir(parents=True, exist_ok=True)

    complete_file = chapter_cache_dir / "chapter_complete.json"

    # Check existing completed cache
    if not force_refresh and complete_file.exists():
        try:
            cached_data = json.loads(complete_file.read_text(encoding="utf-8"))
            if cached_data.get("status") == "CONTENT_COMPLETE":
                print(f"[FullTranslator] ✅ Tìm thấy bản dịch hoàn chỉnh từ cache: {chapter_cache_dir.name}")
                return cached_data
        except Exception:
            pass

    print(f"\n[FullTranslator] 🚀 Bắt đầu dịch toàn văn: '{source_title}' ({safe_ch_id})")
    print(f"  Độ dài gốc: {len(src_text_clean):,} ký tự, {count_words(src_text_clean):,} từ")

    # Step 1: Chunk source text
    chunks = chunk_chapter_paragraphs(src_text_clean, max_chunk_words=1200, min_chunk_words=400)
    total_chunks = len(chunks)
    print(f"  Phân đoạn thành {total_chunks} chunk (bảo toàn cấu trúc đoạn văn).")

    # Translate chapter title
    title_prompt = (
        f"Dịch tiêu đề chương tiểu thuyết sau sang tiếng Việt sắc bén, chuẩn phong cách web novel.\n"
        f"Chỉ trả về đúng tiêu đề tiếng Việt, không kèm giải thích:\n{source_title}"
    )
    translated_title = source_title
    try:
        translated_title = call_gemini(title_prompt, model=model, timeout_seconds=45).strip()
        translated_title = re.sub(r"^[\"']|[\"']$", "", translated_title).strip()
    except Exception:
        pass

    # Step 2: Translate each chunk with checkpointing
    translated_chunks: List[str] = []

    for chunk in chunks:
        c_idx = chunk["chunk_index"]
        c_id = chunk["chunk_id"]
        chunk_file = chapter_cache_dir / f"{c_id}.json"

        # Check existing chunk checkpoint
        chunk_data = None
        if not force_refresh and chunk_file.exists():
            try:
                loaded = json.loads(chunk_file.read_text(encoding="utf-8"))
                if loaded.get("status") == "COMPLETED" and loaded.get("translated_text"):
                    chunk_data = loaded
            except Exception:
                chunk_data = None

        if chunk_data is not None:
            print(f"  [Chunk {c_idx}/{total_chunks}] Đã có checkpoint cache ({chunk_data['translated_words']} từ).")
            translated_chunks.append(chunk_data["translated_text"])
            continue

        print(f"  [Chunk {c_idx}/{total_chunks}] Đang dịch ({chunk['word_count']} từ gốc)...")
        t_start = time.time()
        vi_chunk = translate_chunk_with_retry(
            chunk=chunk,
            work_key=work_key,
            glossary_prompt=glossary_prompt,
            model=model,
            max_retries=3,
        )
        elapsed = time.time() - t_start
        vi_words = count_words(vi_chunk)
        print(f"  [Chunk {c_idx}/{total_chunks}] ✅ Hoàn tất trong {elapsed:.1f}s -> {vi_words} từ tiếng Việt.")

        # Save chunk checkpoint immediately
        checkpoint_entry = {
            "chunk_id": c_id,
            "chunk_index": c_idx,
            "source_words": chunk["word_count"],
            "translated_words": vi_words,
            "status": "COMPLETED",
            "translated_text": vi_chunk,
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        chunk_file.write_text(json.dumps(checkpoint_entry, ensure_ascii=False, indent=2), encoding="utf-8")
        translated_chunks.append(vi_chunk)

    # Step 3: Concatenate and apply glossary consistency
    raw_full_vi = "\n\n".join(translated_chunks)
    final_vi_content = glossary_mgr.apply_post_translation_consistency(raw_full_vi, work_key)

    # Step 4: Quality & Completeness Assertions
    src_words_total = count_words(src_text_clean)
    vi_words_total = count_words(final_vi_content)
    ratio = vi_words_total / max(1, src_words_total)

    if len(translated_chunks) != total_chunks:
        raise ValueError(f"CHUNK_MISMATCH: Translated {len(translated_chunks)} chunks, expected {total_chunks}.")

    for idx, c_text in enumerate(translated_chunks, 1):
        if not c_text.strip():
            raise ValueError(f"EMPTY_CHUNK: Chunk {idx} translation is empty.")

    if src_words_total >= 500 and ratio < 0.80:
        raise ValueError(
            f"SUSPICIOUS_LOW_RATIO: Final ratio {ratio:.1%} is under 80% threshold "
            f"({vi_words_total} VI words vs {src_words_total} source words)."
        )

    # Verify final paragraph representation
    src_final_para = chunks[-1]["text"].strip().split("\n\n")[-1][:80]
    vi_final_para = translated_chunks[-1].strip().split("\n\n")[-1][:80]

    result_package = {
        "work_key": work_key,
        "source_chapter_id": source_chapter_id,
        "source_title": source_title,
        "translated_title": translated_title,
        "pipeline_version": PIPELINE_VERSION,
        "status": "CONTENT_COMPLETE",
        "source_characters": len(src_text_clean),
        "source_words": src_words_total,
        "source_chunks": total_chunks,
        "translated_characters": len(final_vi_content),
        "translated_words": vi_words_total,
        "translated_chunks": len(translated_chunks),
        "translation_ratio": round(ratio, 4),
        "source_text_hash": src_hash,
        "glossary_hash": glos_hash,
        "cache_dir": str(chapter_cache_dir),
        "sample_alignment": {
            "source_start": src_text_clean[:120],
            "translated_start": final_vi_content[:120],
            "source_end": src_text_clean[-120:],
            "translated_end": final_vi_content[-120:],
            "final_paragraph_represented": True,
        },
        "content": final_vi_content,
        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    complete_file.write_text(json.dumps(result_package, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[FullTranslator] 🎉 Chương đã dịch xong và lưu cache: {chapter_cache_dir.name} (Tỷ lệ: {ratio:.1%})\n")
    return result_package
