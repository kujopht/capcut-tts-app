"""
Runner to qualify the three target Naruto candidates:
1. 81168 — Naruto: The Outsider's Resolve
2. 156206 — The Cold Between Wars
3. 136586 — Naruto: The Butterfly Effect

Purely READ-ONLY:
- Fetches only first, middle, latest narrative chapters for each.
- Runs extraction QA.
- Runs 600-1000 word translation trial with isolated glossary.
- Computes realistic local factory scale estimates.
- Saves qualification reports.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.candidate_qualifier import CandidateQualifier

TARGETS = [
    ("81168", "Naruto: The Outsider's Resolve"),
    ("156206", "The Cold Between Wars"),
    ("136586", "Naruto: The Butterfly Effect"),
]


def main():
    print("================================================================================")
    print("🎖️ CANDIDATE QUALIFICATION v1 — READ-ONLY EXECUTION")
    print("================================================================================\n")

    qualifier = CandidateQualifier()
    reports = []

    for wid, expected_title in TARGETS:
        print(f"\n>>> Đang thẩm định ứng viên [{wid}] {expected_title}...")
        try:
            rep = qualifier.qualify(wid)
            reports.append(rep)
            print(f"✅ Hoàn tất thẩm định [{wid}]: {rep.title}")
            print(f"   - Số chương lấy mẫu: {len(rep.inspected_chapters)}")
            for ch in rep.inspected_chapters:
                clean_badge = "CLEAN" if ch.crawler_clean else "DIRTY"
                print(f"     * [{ch.order}] {ch.title}: {ch.word_count:,} từ, {ch.paragraph_count} đoạn | Crawler: {clean_badge} | Ending: ...{ch.clean_ending_preview[-40:]}")
            print(f"   - Factual Flags: {rep.factual_flags}")
            print(f"   - Thử nghiệm dịch ({rep.translation_trial.source_excerpt_words} từ):")
            print(f"     * Naturalness: {rep.translation_trial.vietnamese_naturalness}/10 | Edit requirement: {rep.translation_trial.manual_editing_requirement}")
            print(f"   - Ước tính quy mô thực tế:")
            print(f"     * Trung bình: {rep.scale_estimate.sampled_avg_words_per_chapter:,} từ/chương (Tổng: ~{rep.scale_estimate.estimated_total_source_words:,} từ EN)")
            print(f"     * Thời lượng Audio TTS: ~{rep.scale_estimate.estimated_tts_hours} giờ | Dung lượng lưu trữ: ~{rep.scale_estimate.estimated_storage_mb} MB")
            print(f"     * Thời gian sản xuất dự kiến: ~{rep.scale_estimate.approximate_processing_days} ngày tại nhà máy nội bộ")
        except Exception as e:
            print(f"❌ Lỗi khi thẩm định [{wid}]: {e}")

    summary_file = PROJECT_ROOT / "scratch" / "candidates_qualification_summary.json"
    summary_data = [r.model_dump() for r in reports]
    summary_file.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n================================================================================")
    print(f"✅ ĐÃ HOÀN TẤT VÀ LƯU BÁO CÁO 3 ỨNG VIÊN RA: {summary_file}")
    print("================================================================================")


if __name__ == "__main__":
    main()
