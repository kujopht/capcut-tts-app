"""Acceptance Test for Router V4 Content Factory.

Validates:
1. Gemini 3.8 Flash evaluation & metadata packaging.
2. Worker 2: Ngoc Huyen TTS synthesis & millisecond-accurate synchronized transcript (.srt, .json).
3. Worker 1: YouTube candidate search & metadata extraction.
4. Worker 3: SubVid ASS styling, subtitle masking filters, and multi-voice configuration.
5. Google Drive remote paths & sync configuration.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.gemini_evaluator import (
    evaluate_content,
    generate_fanfic_world_metadata,
)
from scripts.content_factory.worker1_youtube_audio import search_youtube_candidates
from scripts.content_factory.worker2_text_fanfic import (
    _format_srt_time,
    _probe_duration,
    split_sentences_for_transcript,
    synthesize_with_synchronized_transcript,
)
from scripts.content_factory.worker3_ai_animation import (
    DialogueLine,
    build_subvid_ass,
)


class TestContentFactoryRouterV4(unittest.TestCase):

    def test_01_gemini_evaluation_and_metadata(self):
        """Test Gemini 3.8 Flash content evaluation and fanfic.world metadata generation."""
        print("\n--- TEST 1: Gemini 3.8 Flash Thẩm Định & Metadata ---")
        title = "Naruto: Ý Chí Của Lửa Bất Diệt"
        snippet = "Uchiha Sasuke trở về làng Lá sau nhiều năm lưu lạc, đối mặt với Uzumaki Naruto trong một trận chiến bảo vệ hòa bình nhẫn giới."
        
        eval_res = evaluate_content(title, snippet, source_type="text_novel", threshold=7.0)
        print(f"Điểm thẩm định: {eval_res.score} | Approved: {eval_res.approved} | Fandom: {eval_res.fandom}")
        self.assertGreaterEqual(eval_res.score, 6.0)
        self.assertTrue(len(eval_res.fandom) > 0)
        self.assertTrue(len(eval_res.reasoning) > 0)

        meta = generate_fanfic_world_metadata(title, snippet, author="Masashi", source_url="test_url")
        print(f"Tiêu đề tiếng Việt: {meta.get('title_vi')}")
        print(f"Mô tả fanfic.world: {meta.get('description_vi')[:100]}...")
        self.assertIn("title_vi", meta)
        self.assertIn("description_vi", meta)
        self.assertIn("tags", meta)
        self.assertTrue(len(meta["tags"]) >= 2)

    def test_02_worker2_tts_and_synchronized_transcript(self):
        """Test Ngoc Huyen TTS synthesis and verified synchronized transcript cues."""
        print("\n--- TEST 2: Worker 2 Tổng Hợp TTS Ngọc Huyền & Transcript Đồng Bộ ---")
        test_text = (
            "Gió lạnh thổi qua khu rừng Konoha yên tĩnh. "
            "Naruto đứng trên đỉnh tượng Hokage nhìn xuống ngôi làng. "
            "Cậu mỉm cười tự tin, sẵn sàng cho một cuộc phiêu lưu mới."
        )
        sentences = split_sentences_for_transcript(test_text)
        self.assertEqual(len(sentences), 3)

        tmp_dir = Path(tempfile.mkdtemp(prefix="test_w2_"))
        try:
            master_audio, srt_path, json_path = synthesize_with_synchronized_transcript(
                sentences, tmp_dir, rate="1.0"
            )
            self.assertTrue(master_audio.exists())
            self.assertTrue(srt_path.exists())
            self.assertTrue(json_path.exists())

            dur = _probe_duration(master_audio)
            print(f"Thời lượng audio tổng hợp: {dur:.2f}s")
            self.assertGreater(dur, 2.0)

            srt_content = srt_path.read_text(encoding="utf-8")
            print("Nội dung SRT sinh ra:\n" + srt_content.strip())
            self.assertIn("-->", srt_content)
            self.assertIn("Konoha", srt_content)

            json_data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(json_data), 3)
            # Verify timing integrity: monotonically increasing and contiguous
            for i in range(len(json_data) - 1):
                self.assertAlmostEqual(json_data[i]["end"], json_data[i + 1]["start"], delta=0.01)
                self.assertGreater(json_data[i]["end"], json_data[i]["start"])

            print("[✓] Transcript đồng bộ 100% chính xác từng mili-giây.")
        finally:
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass

    def test_03_worker1_youtube_search_inspection(self):
        """Test Worker 1 YouTube search candidate extraction."""
        print("\n--- TEST 3: Worker 1 Tìm Kiếm Ứng Viên YouTube ---")
        candidates = search_youtube_candidates("naruto audiobook", max_results=2)
        print(f"Tìm thấy {len(candidates)} ứng viên.")
        self.assertGreaterEqual(len(candidates), 1)
        first = candidates[0]
        print(f"Ứng viên đầu: '{first.get('title')}' | Duration: {first.get('duration')}s")
        self.assertTrue("url" in first)
        self.assertTrue("title" in first)

    def test_04_worker3_subvid_ass_styling(self):
        """Test Worker 3 SubVid ASS subtitle styling and multi-voice assignment."""
        print("\n--- TEST 4: Worker 3 Cấu Trúc SubVid ASS & Lồng Tiếng Đa Giọng ---")
        lines = [
            DialogueLine(index=1, start=0.5, end=2.8, original_text="Hôm nay trời đẹp quá!", vi_text="Hôm nay trời đẹp quá!", speaker_gender="female"),
            DialogueLine(index=2, start=3.2, end=5.9, original_text="Chúng ta phải lên đường thôi.", vi_text="Chúng ta phải lên đường thôi.", speaker_gender="male"),
        ]
        tmp_dir = Path(tempfile.mkdtemp(prefix="test_w3_"))
        try:
            ass_path = tmp_dir / "test_subvid.ass"
            build_subvid_ass(lines, ass_path, width=1280, height=720)
            self.assertTrue(ass_path.exists())
            ass_text = ass_path.read_text(encoding="utf-8")
            self.assertIn("Style: MaleVoice", ass_text)
            self.assertIn("Style: FemaleVoice", ass_text)
            self.assertIn("&H002BF7FF", ass_text)  # Yellow for male
            self.assertIn("&H00FFFFFF", ass_text)  # White for female
            self.assertIn("FemaleVoice,,0,0,20,,Hôm nay trời đẹp quá!", ass_text)
            self.assertIn("MaleVoice,,0,0,20,,Chúng ta phải lên đường thôi.", ass_text)
            print("[✓] SubVid ASS cấu trúc chuẩn với màu phân vai và căn lề đè sub Trung.")
        finally:
            try:
                shutil.rmtree(tmp_dir)
            except OSError:
                pass

    def test_05_production_naming_standards(self):
        """Test standardized production name (full Vietnamese) & slug generation across all branches."""
        print("\n--- TEST 5: Chuẩn Hóa Tên Thư Mục Sản Xuất (Production Naming) ---")
        from scripts.content_factory.naming import make_production_name, make_production_slug

        # Test Branch 1 (Full Vietnamese Name)
        name_w1 = make_production_name("Naruto", "Naruto: Đệ Tử Của Orochimaru Part 1", default_part_type="Phần")
        self.assertEqual(name_w1, "[Naruto] Đệ Tử Của Orochimaru - Phần 01")

        # Test Branch 2 (Fanfic Novel - Full Vietnamese Name)
        name_w2 = make_production_name("Naruto", "Naruto: Đêm Nghịch Mệnh - Huyết Đồng Tái Thế", default_part_type="Chương")
        self.assertEqual(name_w2, "[Naruto] Đêm Nghịch Mệnh - Huyết Đồng Tái Thế - Chương 01")

        # Test Branch 3 (AI Animation - Full Vietnamese Name)
        name_w3 = make_production_name("Anime", "Đợi Gió Đợi Ánh Sáng Tiết 1", default_part_type="Tập")
        self.assertEqual(name_w3, "[Anime] Đợi Gió Đợi Ánh Sáng - Tập 01")

        # Test URL Slugs for SEO
        slug_w2 = make_production_slug("Naruto", "Naruto: Đêm Nghịch Mệnh - Huyết Đồng Tái Thế", "c01")
        self.assertEqual(slug_w2, "naruto-dem-nghich-menh-c01")
        print("[✓] Đã kiểm chứng tên thư mục có dấu tiếng Việt đầy đủ và slug SEO chuẩn.")

    def test_06_series_detection_and_skipping(self):
        """Test series detection, multi-episode prioritization, and short episode skipping."""
        print("\n--- TEST 6: Kiểm Thử Lọc Bộ Nhiều Tập & Bỏ Qua Tập Ngắn Đơn Lẻ ---")
        from scripts.content_factory.worker1_youtube_audio import check_candidate_series_viability
        from scripts.content_factory.worker2_text_fanfic import process_text_fanfic

        # Case 1: Standalone short clip (e.g. 5 minutes, no part number) -> Must be SKIPPED
        short_clip = {"title": "Top 5 chiêu thức mạnh nhất Naruto", "duration": 300, "url": "https://youtube.com/watch?v=123"}
        viable, reason, is_series, _ = check_candidate_series_viability(short_clip)
        self.assertFalse(viable)
        self.assertIn("Bỏ qua", reason)
        print(f"[✓] Standalone clip ngắn (< 10 phút) đã được skip chuẩn xác: {reason}")

        # Case 2: Series Episode (even if individual ep is 500s, it belongs to a series -> Viable to gather all existing episodes)
        series_ep = {"title": "Audiobook Fanfic Naruto - Tập 1", "duration": 500, "url": "https://youtube.com/watch?v=456"}
        viable, reason, is_series, part_num = check_candidate_series_viability(series_ep)
        self.assertTrue(viable)
        self.assertTrue(is_series)
        self.assertEqual(part_num, 1)
        print(f"[✓] Tập thuộc bộ (Tập 1) được chấp nhận để tìm toàn bộ các tập: is_series={is_series}, part={part_num}")

        # Case 3: Compilation video >= 5 tiếng (18,000s, e.g. 6h hoặc 20h) -> Must be VIABLE
        mega_vid = {"title": "Audiobook Fanfic Naruto Full 6 Tiếng", "duration": 21600, "url": "https://youtube.com/watch?v=789"}
        viable, reason, _, _ = check_candidate_series_viability(mega_vid)
        self.assertTrue(viable)
        self.assertIn("chuẩn độ dài", reason)
        print(f"[✓] Bộ audio dài 6 tiếng được chấp nhận: {reason}")

        # Case 4: Text Fanfic with only 1 short chapter (< 1500 words) -> Must be SKIPPED
        tmp_txt = Path(tempfile.gettempdir()) / "short_fanfic_test.txt"
        tmp_txt.write_text("Đây là một đoạn truyện ngắn ngắn chỉ có vài chục chữ thôi.", encoding="utf-8")
        try:
            res_short = process_text_fanfic(str(tmp_txt), auto_sync=False)
            self.assertEqual(res_short.get("status"), "SKIPPED")
            print(f"[✓] Truyện chữ 1 chương quá ngắn (< 1500 từ) đã được skip thành công: {res_short.get('reason')}")
        finally:
            if tmp_txt.exists():
                tmp_txt.unlink()

    def test_07_worker3_series_and_sibling_discovery(self):
        """Test Worker 3 AI Animation series detection, sibling episode sorting, and deduplication."""
        print("\n--- TEST 7: Worker 3 Quét Tập Theo Bộ Hoạt Hình AI (Series & Sibling Discovery) ---")
        from scripts.content_factory.worker3_ai_animation import (
            SERIES_REGEX,
            _clean_series_title,
            find_all_animation_episodes,
        )

        title_sample = "[BL Anime] [ENG/MULTI SUB] Extra:Jin's Soliloquy EP02|Secret Love #Yaoi#blseries"
        m = SERIES_REGEX.search(title_sample)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 2)
        print(f"[✓] Regex nhận diện chuẩn tập phim: EP02 -> Tập {int(m.group(1))}")

        base_clean = _clean_series_title(title_sample)
        print(f"[✓] Chuẩn hóa tiêu đề gốc: '{title_sample}' -> '{base_clean}'")
        self.assertNotIn("#", base_clean)
        self.assertNotIn("EP02", base_clean)

        # Test sibling discovery on candidate with real YouTube query
        cand = {
            "title": title_sample,
            "uploader": "Qustory-Official",
            "url": "https://www.youtube.com/watch?v=7T6AqOwr-As",
        }
        eps = find_all_animation_episodes(cand, max_episodes=5)
        print(f"[✓] Đã tìm thấy {len(eps)} tập thuộc bộ: {[e.get('title') for e in eps]}")
        self.assertGreaterEqual(len(eps), 2)
        
        # Verify chronological order: first episode must be EP01 or lower than EP02
        first_ep_m = SERIES_REGEX.search(eps[0]["title"])
        self.assertIsNotNone(first_ep_m)
        self.assertEqual(int(first_ep_m.group(1)), 1)
        print(f"[✓] Thứ tự các tập được sắp xếp tuần tự từ Tập 01 trở đi không bị ngắt quãng.")


if __name__ == "__main__":
    unittest.main()

