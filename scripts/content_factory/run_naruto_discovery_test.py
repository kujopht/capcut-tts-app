"""
Initial Discovery Test for Naruto — Content Factory v2.

Purely READ-ONLY:
- Discovers 10–20 Naruto candidates from RoyalRoad.
- Applies deterministic pre-filters.
- Evaluates eligible candidates with Gemini semantic scoring.
- Selects 3 recommended candidates for OWNER REVIEW only.
- Does NOT translate chapters.
- Does NOT synthesize TTS.
- Does NOT touch production database or R2.
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

from scripts.content_factory.discovery_engine import DiscoveryEngine
from scripts.content_factory.discovery_models import CandidateState, DeterministicFilterConfig
from scripts.content_factory.discovery_store import DiscoveryStore


def run_test():
    print("================================================================================")
    print("🚀 CONTENT FACTORY V2 — DISCOVERY MODE v1 TEST: 'Naruto'")
    print("🔒 SECURITY NOTICE: Purely READ-ONLY. Zero writes to production, R2, or audio.")
    print("================================================================================\n")

    store = DiscoveryStore()
    engine = DiscoveryEngine(store=store)

    # 1. Search RoyalRoad
    print("🔍 [Step 1] Đang tìm kiếm RoyalRoad cho từ khóa 'Naruto'...")
    candidates = engine.search_royalroad("Naruto", max_results=18)
    print(f"-> Thu thập thành công {len(candidates)} ứng viên từ RoyalRoad search.\n")

    cfg = store.load_filter_config()
    prod_ids = engine.get_production_work_ids()

    # 2. Deterministic Filtering
    print("⚙️ [Step 2] Áp dụng Bộ Lọc Tiêu Chuẩn (Deterministic Filters):")
    print(f"   - Min chapters: {cfg.min_chapters}")
    print(f"   - Min words: {cfg.min_words:,}")
    print(f"   - Max days abandoned: {cfg.max_days_abandoned}")
    print(f"   - Production exclusion: {cfg.reject_already_in_production}")
    print(f"   - Production works already known: {prod_ids}\n")

    passed_candidates = []
    rejected_candidates = []

    for cand in candidates:
        res = engine.apply_deterministic_filters(cand, config=cfg, prod_work_ids=prod_ids)
        store.upsert_candidate(cand)
        if res.passed:
            passed_candidates.append(cand)
        else:
            rejected_candidates.append(cand)

    print(f"-> Kết quả lọc: {len(passed_candidates)} VƯỢT QUA, {len(rejected_candidates)} BỊ LOẠI.")
    for r in rejected_candidates:
        print(f"   ⛔ [REJECTED] {r.title[:45]}... (ID: {r.source_work_id}) -> Lý do: {'; '.join(r.rejection_reasons)}")
    print()

    # 3. Gemini Semantic Evaluation (Conservative Concurrency)
    print("🤖 [Step 3] Tiến hành Đánh Giá Ngữ Nghĩa bằng Gemini Flash (Metadata & Synopsis only)...")
    evaluated_candidates = []

    for idx, cand in enumerate(passed_candidates, start=1):
        print(f"   [{idx}/{len(passed_candidates)}] Đang chấm điểm: {cand.title[:40]} (ID: {cand.source_work_id})...")
        try:
            ev = engine.evaluate_candidate_with_gemini(cand)
            cand.state = CandidateState.INSPECTED
            store.upsert_candidate(cand)
            evaluated_candidates.append(cand)
            print(f"       => Điểm: {cand.overall_score:.1f}/10 | Story: {ev.story_quality:.1f} | Fandom: {ev.fandom_fit:.1f} | Trans: {ev.translation_value:.1f}")
        except Exception as e:
            print(f"       ⚠️ Lỗi đánh giá: {e}")
            evaluated_candidates.append(cand)

    print("\n================================================================================")
    print("📊 TỔNG HỢP KẾT QUẢ DISCOVERY MODE CHO 'Naruto'")
    print("================================================================================")
    print(f"{'Điểm':<6} | {'ID':<8} | {'Trạng Thái':<9} | {'Chương':<7} | {'Ước Lượng Từ':<13} | {'Đánh Giá / Rủi Ro':<35} | {'Tiêu Đề'}")
    print("-" * 135)

    # Sort by overall score descending
    all_sorted = sorted(candidates, key=lambda c: c.overall_score, reverse=True)
    for c in all_sorted:
        sc = f"{c.overall_score:.1f}" if c.overall_score > 0 else "—"
        st = c.status.upper()
        chs = f"{c.chapter_count:,}"
        wds = f"~{c.estimated_word_count:,}"
        risk = c.rejection_reasons[0] if c.rejection_reasons else (c.gemini_eval.risks[:32] if c.gemini_eval else "Chưa đánh giá")
        print(f"{sc:<6} | {c.source_work_id:<8} | {st:<9} | {chs:<7} | {wds:<13} | {risk:<35} | {c.title}")

    # 4. Top 3 Recommended Candidates for Owner Review
    eligible_for_rec = [c for c in evaluated_candidates if c.deterministic_passed]
    eligible_for_rec.sort(key=lambda c: c.overall_score, reverse=True)
    top_3 = eligible_for_rec[:3]

    print("\n================================================================================")
    print("🌟 TOP 3 ỨNG VIÊN ĐƯỢC ĐỀ XUẤT CHO OWNER REVIEW (CHỈ LÀ GỢI Ý, KHÔNG TỰ ĐỘNG CHỌN)")
    print("================================================================================")
    for i, c in enumerate(top_3, start=1):
        ev = c.gemini_eval
        print(f"\n[{i}] 📖 {c.title}")
        print(f"    - URL: {c.url}")
        print(f"    - Source Work ID: {c.source_work_id} | Tác giả: {c.author}")
        print(f"    - Fandom: {c.fandom} | Trạng thái: {c.status} | Cập nhật cuối: {c.last_update[:19]}")
        print(f"    - Quy mô: {c.chapter_count} chương (~{c.estimated_word_count:,} từ) | Rating: {c.rating}/5 ({c.followers:,} followers)")
        print(f"    - Ước tính sản xuất: ~{c.estimated_tts_hours:.1f} giờ audio TTS | Chi phí LLM Flash: ~${c.estimated_translation_cost_usd:.2f} USD")
        if ev:
            print(f"    - ĐIỂM TỔNG HỢP: {c.overall_score:.1f} / 10")
            print(f"      [Cốt truyện: {ev.story_quality:.1f} | Hợp Fandom: {ev.fandom_fit:.1f} | Giá trị dịch: {ev.translation_value:.1f} | Độc đáo: {ev.catalog_uniqueness:.1f} | Tiến độ: {ev.update_health:.1f}]")
            print(f"    - Lý do đề xuất: {ev.reasons}")
            print(f"    - Rủi ro cần lưu ý: {ev.risks}")

    # Output JSON report
    report_data = {
        "query": "Naruto",
        "total_discovered": len(candidates),
        "deterministic_passed": len(passed_candidates),
        "deterministic_rejected": len(rejected_candidates),
        "top_3_recommendations": [
            {
                "source_work_id": c.source_work_id,
                "title": c.title,
                "url": c.url,
                "overall_score": c.overall_score,
                "chapter_count": c.chapter_count,
                "estimated_words": c.estimated_word_count,
                "rating": c.rating,
                "followers": c.followers,
                "reasons": c.gemini_eval.reasons if c.gemini_eval else "",
                "risks": c.gemini_eval.risks if c.gemini_eval else "",
            }
            for c in top_3
        ],
        "candidates": [c.model_dump() for c in all_sorted],
    }

    out_json = PROJECT_ROOT / "scratch" / "naruto_discovery_test_results.json"
    out_json.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Đã xuất báo cáo chi tiết ra: {out_json}")


if __name__ == "__main__":
    run_test()
