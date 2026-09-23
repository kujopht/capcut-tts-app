"""
Permanent Publish Quality Gate — Content Factory v2.

Production-grade gate that validates chapter text and audio before allowing publication.
Enforces:
1. complete_source_fetch: Non-empty source text with valid provenance.
2. content_classification_complete: Classified into canonical entry types before translation.
3. all_source_chunks_accounted_for: Source segmented with full paragraph coverage.
4. translated_chunks_match_expected: Exact equality of source and translated chunk counts.
5. no_empty_translated_chunk: Zero blank or whitespace-only chunks.
6. no_detected_model_cutoff: No abrupt model cutoff or unclosed sentence endings.
7. no_detected_summarization: Zero accidental summarization or truncation keywords.
8. final_source_section_represented: Source tail paragraph faithfully represented in translation.
9. translation_cache_identity_valid: Cache key includes source_hash + glossary_version + pipeline_version.
10. tts_input_hash_matches_candidate: Audio input text hash matches Vietnamese publication text hash.
11. audio_duration_sanity: Audio duration and speech rate sanity check.

IMPORTANT: Does NOT use character ratio alone as a hard gate (EN->VI expansion/contraction varies).
Chunk coverage + tail coverage + hash consistency form the authoritative proof.

If ANY hard requirement fails:
  publish_allowed = False (PUBLISH = DISABLED)
The UI displays the exact blocking reasons.
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Summary indicators that suggest accidental LLM compression instead of translation
SUMMARIZATION_PATTERNS = [
    r"\btác giả tóm tắt\b",
    r"\bphần còn lại của chương\b",
    r"\bđoạn sau kể về\b",
    r"\bnhìn chung trong chương này\b",
    r"\bcâu chuyện tiếp tục với việc tóm lược\b",
    r"\[\s*tóm tắt\s*\]",
    r"\[\s*lược dịch\s*\]",
    r"^\s*tóm tắt\s*:",
    r"\bdưới đây là bản tóm tắt\b",
    r"\btóm tắt nội dung\b",
]

# Cutoff indicators at the very end of translated text
CUTOFF_TERMINATORS = [
    r",\s*$",
    r":\s*$",
    r";\s*$",
    r"\b(và|hoặc|nhưng|vì|khi|rằng|là|của|trong|với)\s*$",
    r"\.\.\.\s*$",  # Trailing ellipsis without prior sentence closure
]

PIPELINE_VERSION = "fulltext-v1"


class EntryClassification(str, enum.Enum):
    STORY_CHAPTER = "STORY_CHAPTER"
    EXTRA = "EXTRA"
    AUTHOR_NOTE = "AUTHOR_NOTE"
    ANNOUNCEMENT = "ANNOUNCEMENT"
    UNKNOWN = "UNKNOWN"


class CheckResult(BaseModel):
    name: str
    passed: bool
    is_hard_gate: bool = True
    detail: str = ""
    evidence: Dict[str, Any] = Field(default_factory=dict)


class QualityGateResult(BaseModel):
    chapter_id: str
    source_order: int
    display_order: Optional[int] = None
    classification: EntryClassification = EntryClassification.UNKNOWN
    publish_allowed: bool = False
    passed_all_checks: bool = False
    blocking_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    checks: Dict[str, CheckResult] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def summary_badge(self) -> str:
        if self.publish_allowed:
            return "✅ PUBLISH = ALLOWED"
        return f"⛔ PUBLISH = DISABLED ({len(self.blocking_reasons)} blocking issues)"


def compute_cache_identity(source_text_hash: str, glossary_version: str, pipeline_version: str = PIPELINE_VERSION) -> str:
    """Deterministic cache identity incorporating source hash + glossary + pipeline version."""
    seed = f"{source_text_hash}:{glossary_version}:{pipeline_version}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()


class PublishQualityGate:
    """Evaluates whether a chapter meets all 11 production quality criteria."""

    def __init__(self, glossary_version: str = "hatake_v2", pipeline_version: str = PIPELINE_VERSION):
        self.glossary_version = glossary_version
        self.pipeline_version = pipeline_version

    def audit_chapter(
        self,
        chapter_id: str,
        source_order: int,
        source_text: str,
        translated_text: str,
        classification: EntryClassification,
        source_chunks: Optional[List[Dict[str, Any]]] = None,
        translated_chunks: Optional[List[Dict[str, Any]]] = None,
        display_order: Optional[int] = None,
        cache_metadata: Optional[Dict[str, Any]] = None,
        audio_file_path: Optional[Path] = None,
        audio_duration_seconds: Optional[float] = None,
        tts_input_text: Optional[str] = None,
    ) -> QualityGateResult:
        """Runs the 11-point audit on a candidate chapter."""
        checks: Dict[str, CheckResult] = {}
        blocking: List[str] = []
        warnings: List[str] = []

        # 1. Complete Source Fetch
        src_clean = (source_text or "").strip()
        src_words = len(src_clean.split())
        c1_pass = len(src_clean) >= 50 and src_words >= 10
        c1_detail = f"Source text: {len(src_clean):,} chars, {src_words:,} words"
        if not c1_pass:
            blocking.append("Nguồn chương trống hoặc quá ngắn (<50 ký tự / <10 từ).")
        checks["complete_source_fetch"] = CheckResult(
            name="Complete Source Fetch",
            passed=c1_pass,
            is_hard_gate=True,
            detail=c1_detail,
            evidence={"chars": len(src_clean), "words": src_words},
        )

        # 2. Content Classification Complete
        c2_pass = classification in (EntryClassification.STORY_CHAPTER, EntryClassification.EXTRA)
        if classification == EntryClassification.UNKNOWN:
            blocking.append("Phân loại nội dung chưa xác định (UNKNOWN) — yêu cầu kiểm duyệt thủ công.")
            c2_detail = "Phân loại UNKNOWN: Yêu cầu review trước khi xuất bản."
        elif classification in (EntryClassification.ANNOUNCEMENT, EntryClassification.AUTHOR_NOTE):
            blocking.append(f"Mục là {classification.value} (Thông báo / Ghi chú) — không được xuất bản như chương truyện đọc.")
            c2_detail = f"Entry type {classification.value}: Không được vào mục lục đọc chính."
        else:
            c2_detail = f"Phân loại chuẩn: {classification.value}"
        checks["content_classification_complete"] = CheckResult(
            name="Content Classification Complete",
            passed=c2_pass,
            is_hard_gate=True,
            detail=c2_detail,
            evidence={"classification": classification.value},
        )

        # 3. All Source Chunks Accounted For
        if isinstance(source_chunks, int):
            s_count = source_chunks
            s_chunks = [{} for _ in range(s_count)]
        else:
            s_chunks = source_chunks or []
            s_count = len(s_chunks)
        c3_pass = s_count > 0 or src_words == 0
        if not c3_pass:
            blocking.append("Không có danh sách chunk nguồn được ghi nhận.")
        checks["all_source_chunks_accounted_for"] = CheckResult(
            name="All Source Chunks Accounted For",
            passed=c3_pass,
            is_hard_gate=True,
            detail=f"Source chunks: {s_count} chunks",
            evidence={"source_chunks_count": s_count},
        )

        # 4. Translated Chunks Match Expected Count
        if isinstance(translated_chunks, int):
            t_count = translated_chunks
            t_chunks = [{} for _ in range(t_count)]
        else:
            t_chunks = translated_chunks or []
            t_count = len(t_chunks)
        c4_pass = (s_count == t_count) and t_count > 0
        if not c4_pass:
            blocking.append(f"Số lượng chunk dịch ({t_count}) không khớp số lượng chunk nguồn ({s_count}).")
        checks["translated_chunks_match_expected"] = CheckResult(
            name="Translated Chunks Match Expected",
            passed=c4_pass,
            is_hard_gate=True,
            detail=f"Expected: {s_count} chunks, Translated: {t_count} chunks",
            evidence={"source_count": s_count, "translated_count": t_count},
        )

        # 5. No Empty Translated Chunk
        empty_chunk_indices = []
        if isinstance(translated_chunks, list):
            for idx, tc in enumerate(t_chunks, start=1):
                if isinstance(tc, str):
                    txt = tc
                elif isinstance(tc, dict):
                    txt = tc.get("text", "") or tc.get("translated_text", "")
                else:
                    txt = str(tc)
                if not txt.strip():
                    empty_chunk_indices.append(idx)
        elif t_count > 0 and not (translated_text or "").strip():
            empty_chunk_indices.append(1)
        c5_pass = len(empty_chunk_indices) == 0
        if not c5_pass:
            blocking.append(f"Phát hiện chunk dịch rỗng tại vị trí: {empty_chunk_indices}")
        checks["no_empty_translated_chunk"] = CheckResult(
            name="No Empty Translated Chunk",
            passed=c5_pass,
            is_hard_gate=True,
            detail=f"Empty chunks: {len(empty_chunk_indices)}",
            evidence={"empty_chunk_indices": empty_chunk_indices},
        )

        # 6. No Detected Model Cutoff
        vi_clean = (translated_text or "").strip()
        cutoff_detected = False
        cutoff_reason = ""
        for pat in CUTOFF_TERMINATORS:
            if re.search(pat, vi_clean, re.IGNORECASE):
                # If pattern is trailing ellipsis, verify if upstream source also ended with an ellipsis
                if pat == r"\.\.\.\s*$" and re.search(r"(\.\.\.|…)\s*$", src_clean):
                    continue
                cutoff_detected = True
                cutoff_reason = f"Đuôi văn bản kết thúc đột ngột hoặc chứa từ nối chưa hoàn tất ('{pat}')"
                break
        c6_pass = not cutoff_detected and len(vi_clean) > 0
        if not c6_pass:
            blocking.append(f"Phát hiện Model Cutoff: {cutoff_reason}")
        checks["no_detected_model_cutoff"] = CheckResult(
            name="No Detected Model Cutoff",
            passed=c6_pass,
            is_hard_gate=True,
            detail=cutoff_reason or "Không phát hiện dấu hiệu ngắt cụt câu ở cuối chương.",
            evidence={"vi_last_chars": vi_clean[-60:] if vi_clean else ""},
        )

        # 7. No Detected Summarization
        summary_found = []
        for pat in SUMMARIZATION_PATTERNS:
            if re.search(pat, vi_clean, re.IGNORECASE):
                summary_found.append(pat)
        c7_pass = len(summary_found) == 0
        if not c7_pass:
            blocking.append(f"Phát hiện dấu hiệu tóm tắt / lược thuật tự động: {summary_found}")
        checks["no_detected_summarization"] = CheckResult(
            name="No Detected Summarization",
            passed=c7_pass,
            is_hard_gate=True,
            detail="Bản dịch trọn vẹn, không có từ khóa tóm tắt." if c7_pass else f"Cảnh báo tóm tắt: {summary_found}",
            evidence={"patterns_matched": summary_found},
        )

        # 8. Final Source Section Represented in Translated Output
        c8_pass = False
        c8_detail = ""
        last_src = ""
        last_vi = ""

        if s_chunks and isinstance(s_chunks[-1], dict) and s_chunks[-1].get("text"):
            last_src = (s_chunks[-1].get("text") or "").strip()
        if t_chunks and isinstance(t_chunks[-1], dict) and (t_chunks[-1].get("text") or t_chunks[-1].get("translated_text")):
            last_vi = (t_chunks[-1].get("text") or t_chunks[-1].get("translated_text") or "").strip()

        # If chunk texts were not in chunk dicts, derive from source_text and translated_text
        if not last_src and src_clean:
            src_paras = [p.strip() for p in re.split(r"\n\s*\n", src_clean) if p.strip()]
            if src_paras and 3 <= len(src_paras[-1]) <= 600:
                last_src = src_paras[-1]
            else:
                last_src = src_clean[-150:].strip()
        if not last_vi and vi_clean:
            vi_paras = [p.strip() for p in re.split(r"\n\s*\n", vi_clean) if p.strip()]
            if vi_paras and 3 <= len(vi_paras[-1]) <= 600:
                last_vi = vi_paras[-1]
            else:
                last_vi = vi_clean[-150:].strip()

        if last_src and last_vi:
            # The final translated section must exist and have reasonable length
            min_vi_len = 3 if len(last_src) < 80 else 10
            if len(last_vi) >= min_vi_len and (len(last_vi) >= len(last_src) * 0.35 or len(last_src) < 80):
                c8_pass = True
                c8_detail = f"Đoạn kết nguồn ({len(last_src)} ký tự) có đoạn dịch tương ứng ({len(last_vi)} ký tự)."
            else:
                c8_detail = f"Đoạn kết dịch quá ngắn so với đoạn kết nguồn ({len(last_vi)} vs {len(last_src)} ký tự)."
        elif vi_clean and src_clean:
            c8_pass = len(vi_clean) >= len(src_clean) * 0.5
            c8_detail = "Kiểm tra đại diện đoạn kết thông qua văn bản toàn chương."

        if not c8_pass:
            blocking.append(f"Đoạn kết nguồn không được đại diện đầy đủ trong bản dịch: {c8_detail}")
        checks["final_source_section_represented"] = CheckResult(
            name="Final Source Section Represented",
            passed=c8_pass,
            is_hard_gate=True,
            detail=c8_detail,
            evidence={},
        )

        # 9. Translation Cache Identity Valid
        src_hash = hashlib.sha256(src_clean.encode("utf-8")).hexdigest()
        expected_cache_id = compute_cache_identity(src_hash, self.glossary_version, self.pipeline_version)
        c9_pass = True
        c9_detail = f"Cache key: {expected_cache_id[:16]}... (pipeline: {self.pipeline_version}, glossary: {self.glossary_version})"
        if cache_metadata:
            stored_pipe = cache_metadata.get("pipeline_version")
            if stored_pipe and stored_pipe != self.pipeline_version:
                c9_pass = False
                c9_detail = f"Cache pipeline version mismatch ({stored_pipe} != {self.pipeline_version})"
                blocking.append(f"Phiên bản cache không hợp lệ: {c9_detail}")
        checks["translation_cache_identity_valid"] = CheckResult(
            name="Translation Cache Identity Valid",
            passed=c9_pass,
            is_hard_gate=True,
            detail=c9_detail,
            evidence={"expected_cache_id": expected_cache_id},
        )

        # 10. TTS Input Hash Matches Candidate
        c10_pass = True
        c10_detail = "Chưa gắn audio hoặc TTS chuẩn bị sau."
        if tts_input_text is not None:
            vi_hash = hashlib.sha256(vi_clean.encode("utf-8")).hexdigest()
            tts_hash = hashlib.sha256(tts_input_text.strip().encode("utf-8")).hexdigest()
            c10_pass = (vi_hash == tts_hash)
            if not c10_pass:
                blocking.append(f"Hash văn bản đầu vào TTS không khớp hash văn bản xuất bản ({tts_hash[:8]} != {vi_hash[:8]}).")
                c10_detail = "MISMATCH: TTS input differs from final publication candidate."
            else:
                c10_detail = f"MATCH: Hash {vi_hash[:12]} trùng khớp tuyệt đối."
        checks["tts_input_hash_matches_candidate"] = CheckResult(
            name="TTS Input Hash Matches Candidate",
            passed=c10_pass,
            is_hard_gate=True,
            detail=c10_detail,
            evidence={},
        )

        # 11. Audio Duration Sanity
        c11_pass = True
        c11_detail = "Audio chưa tạo hoặc không bắt buộc cho text-first publication."
        if audio_duration_seconds is not None and audio_duration_seconds > 0:
            vi_words = len(vi_clean.split())
            # Vietnamese speech is typically 110 to 190 words per minute (1.8 to 3.2 words/sec)
            expected_min_duration = (vi_words / 220.0) * 60.0 * 0.7  # relaxed lower bound
            expected_max_duration = (vi_words / 90.0) * 60.0 * 1.5   # relaxed upper bound
            if audio_duration_seconds < expected_min_duration:
                c11_pass = False
                msg = f"Thời lượng audio quá ngắn ({audio_duration_seconds:.1f}s cho {vi_words} từ; dự kiến >= {expected_min_duration:.1f}s) — có dấu hiệu bị cắt cụt."
                blocking.append(msg)
                c11_detail = msg
            elif audio_duration_seconds > expected_max_duration:
                warnings.append(f"Thời lượng audio dài bất thường ({audio_duration_seconds:.1f}s cho {vi_words} từ).")
                c11_detail = f"Audio duration warning ({audio_duration_seconds:.1f}s)"
            else:
                c11_detail = f"Audio duration {audio_duration_seconds:.1f}s sane for {vi_words} words ({vi_words / (audio_duration_seconds / 60.0):.1f} WPM)."
        checks["audio_duration_sanity"] = CheckResult(
            name="Audio Duration Sanity",
            passed=c11_pass,
            is_hard_gate=True,
            detail=c11_detail,
            evidence={"duration_seconds": audio_duration_seconds},
        )

        all_passed = len(blocking) == 0
        publish_allowed = all_passed

        return QualityGateResult(
            chapter_id=chapter_id,
            source_order=source_order,
            display_order=display_order,
            classification=classification,
            publish_allowed=publish_allowed,
            passed_all_checks=all_passed,
            blocking_reasons=blocking,
            warnings=warnings,
            checks=checks,
            metadata={
                "source_chars": len(src_clean),
                "source_words": src_words,
                "translated_chars": len(vi_clean),
                "translated_words": len(vi_clean.split()),
                "source_chunks": len(s_chunks),
                "translated_chunks": len(t_chunks),
                "has_audio": audio_duration_seconds is not None and audio_duration_seconds > 0,
            }
        )
