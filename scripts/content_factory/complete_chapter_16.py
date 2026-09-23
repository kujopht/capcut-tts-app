"""Completes Chapter 16 of Conan novel, packages it, and syncs to Google Drive.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.content_factory.silent_subprocess
from scripts.content_factory.worker2_text_fanfic import (
    _probe_duration,
    split_sentences_for_transcript,
    synthesize_with_synchronized_transcript,
)

DRIVE_TARGET_BASE = "fanfic-gdrive:FanficWorld/production/works/fanfic-tts"
CH16_DIR = (
    PROJECT_ROOT
    / "raw_spool"
    / "fanfic_tts"
    / "[Detective Conan (Thám tử lừng danh Conan)] DƯỚI TÀNG HOA ANH ĐÀO NĂM ẤY - LỜI NGUYỆN CẦU VÀ BẢN ÁN MÀU ĐEN - Chương 16"
)
CH15_DIR = (
    PROJECT_ROOT
    / "raw_spool"
    / "fanfic_tts"
    / "[Detective Conan (Thám tử lừng danh Conan)] DƯỚI TÀNG HOA ANH ĐÀO NĂM ẤY - LỜI NGUYỆN CẦU VÀ BẢN ÁN MÀU ĐEN - Chương 15"
)


def complete_chapter_16():
    print("=================================================================")
    print("🚀 BẮT ĐẦU HOÀN TẤT CHƯƠNG 16 CHO NHÁNH 2 (CONAN NOVEL)...")
    print("=================================================================")

    if not CH16_DIR.exists():
        print("[-] Không tìm thấy thư mục Chương 16.")
        return

    story_text = (CH16_DIR / "story_vi.txt").read_text(encoding="utf-8")
    sentences = split_sentences_for_transcript(story_text)
    print(f"[*] Tổng số câu: {len(sentences)} câu thoại/dẫn truyện.")

    # Synthesize with CapCut voice "BV421_vivn_streaming" (Nhỏ Ngọt Ngào)
    master_audio, srt_path, json_path = synthesize_with_synchronized_transcript(
        sentences, CH16_DIR, rate=1.0, voice_type="BV421_vivn_streaming"
    )

    dur = _probe_duration(master_audio)
    print(f"[✓] Đã tạo tệp audio master: {dur:.1f}s ({dur/60:.1f} phút)")

    # Copy cover from Chapter 15 if not present
    cover_file = CH16_DIR / "cover.jpg"
    if not cover_file.exists() and (CH15_DIR / "cover.jpg").exists():
        shutil.copy(str(CH15_DIR / "cover.jpg"), str(cover_file))
        print("[✓] Đã gán ảnh bìa đồng bộ từ tuyển tập.")

    # Write metadata.json
    metadata = {
        "title_vi": "Thám Tử Conan: Ánh Hoàng Hôn Sau Cơn Bão Và Lời Nguyện Dưới Tán Hoa",
        "description_vi": "Khói lửa dần lắng xuống tại Giảng đường số 4, để lại những vết thương rỉ máu và một bí mật đen tối dần hé lộ. Kudo Shinichi và Ran Mori dựa vào nhau giữa hoang tàn đổ nát, nơi những cánh hoa anh đào vương đầy bụi tro như chứng nhân cho lời thề sinh tử. Thảm kịch đã qua đi hay chỉ là khúc dạo đầu cho một âm mưu tàn khốc hơn sắp ập tới? Cùng lắng nghe hồi kết đầy cảm xúc của chương 16 độc quyền tại fanfic.world!",
        "summary": "Sau khi thoát khỏi biển lửa tại Giảng đường số 4, Shinichi và Ran cùng nhau đối mặt với những thương tích và manh mối mới về kẻ giấu mặt. Giữa đống tro tàn, lời nguyện ước thời niên thiếu lại một lần nữa vang vọng.",
        "fandom": "Detective Conan",
        "tags": [
            "đồng nhân conan",
            "kudo shinichi",
            "ran mori",
            "shinran",
            "trinh thám",
            "ngọt ngào",
            "hồi phục",
        ],
        "rating": "Teen",
        "author": "Fanfic World AI",
        "source_url": "curated_by_gemini",
        "folder_name": CH16_DIR.name,
        "slug": "detectiveconant-duoi-tang-hoa-anh-c16",
        "title_original": "DƯỚI TÀNG HOA ANH ĐÀO NĂM ẤY: LỜI NGUYỆN CẦU VÀ BẢN ÁN MÀU ĐEN",
        "chapter_index": 16,
        "chapter_total": 28,
        "quality_score": 8.6,
        "evaluation_reasoning": "Văn phong giàu cảm xúc, chuyển biến tâm lý nhân vật sau biến cố được khắc họa sâu sắc, ngôn từ trong sáng phù hợp tiêu chuẩn fanfic.world.",
        "source_author": "Fanfic World AI",
        "source_platform": "Fanfic World AI Studio (Original Novel)",
        "source_status": "Đang ra (Ongoing - Chờ cập nhật)",
        "latest_chapter_scraped": 16,
        "voice_used": "BV421_vivn_streaming",
        "voice_name": "Nhỏ Ngọt Ngào (CapCut)",
        "duration_seconds": round(dur, 3),
        "sentence_count": len(sentences),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    (CH16_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write source.txt
    source_content = (
        f"=== THÔNG TIN NGUỒN GỐC TIỂU THUYẾT (FANFIC.WORLD) ===\n"
        f"Tác phẩm: DƯỚI TÀNG HOA ANH ĐÀO NĂM ẤY: LỜI NGUYỆN CẦU VÀ BẢN ÁN MÀU ĐEN\n"
        f"Fandom: Detective Conan\n"
        f"Tác giả gốc: Fanfic World AI\n"
        f"Nền tảng / Nguồn phát hành: Fanfic World AI Studio (Original Novel)\n"
        f"Đường dẫn gốc (URL): curated_by_gemini\n"
        f"Tình trạng tác phẩm: Đang ra (Ongoing - Chờ cập nhật)\n"
        f"Chương hiện tại: Chương 16 / 28\n"
        f"Giọng lồng tiếng: Nhỏ Ngọt Ngào (CapCut)\n"
        f"Thời điểm thu thập: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Ghi chú fanfic.world: Lưu vết nguồn gốc để phục vụ ghi công (attribution) khi đăng tải lên web.\n"
    )
    (CH16_DIR / "source.txt").write_text(source_content, encoding="utf-8")

    # Sync to Google Drive
    remote = f"{DRIVE_TARGET_BASE}/{CH16_DIR.name}"
    print(f"\n[*] Đang đồng bộ Chương 16 lên Google Drive: {remote}...")
    subprocess.run(["rclone", "copy", str(CH16_DIR), remote], check=True)
    print(f"[✓] Đồng bộ Drive thành công: {remote}")

    print("\n=================================================================")
    print("✅ CHƯƠNG 16 ĐÃ HOÀN TẤT TRỌN VẸN VÀ ĐẨY LÊN GOOGLE DRIVE!")
    print("=================================================================")


if __name__ == "__main__":
    complete_chapter_16()
