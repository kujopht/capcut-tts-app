"""Consolidate Google Drive and Local existing-audio production works into structured Series Albums.

Merges the scattered 41 episode folders on Drive into 9 clean Series Albums:
fanfic-gdrive:FanficWorld/production/works/existing-audio/{Album_Title}/Tập {xx}/
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DRIVE_BASE = "fanfic-gdrive:FanficWorld/production/works/existing-audio"
LOCAL_BASE = Path(__file__).resolve().parents[2] / "raw_spool" / "youtube_audio"

# Mapping table from old folder name to (Album Title, Episode Number)
ALBUM_MAPPING = {
    # 1. Ứng Long (10 parts)
    "[One Piece] Hải Quân Thần Thoại - Ta Mang Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 01": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 1),
    "[One Piece] Hải Quân - Thức Tỉnh Huyễn Thú Ứng Long, Uy Trấn Đại Hải Trình - Phần 02": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 2),
    "[One Piece] Hải Quân Chi Đỉnh - Thức Tỉnh Huyễn Thú Ứng Long, Trấn Áp Biển Cả - Phần 03": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 3),
    "[One Piece] Hải Quân Thần Thoại - Thức Tỉnh Trái Ứng Long, Trấn Áp Đại Hải Trình - Phần 04": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 4),
    "[One Piece] Huyễn Thú Ứng Long, Trấn Áp Kỷ Nguyên Hải Tặc - Phần 05": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 5),
    "[One Piece] Hải Quân Kỷ Nguyên - Thần Thoại Ứng Long Trấn Áp Bốn Biển - Phần 06": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 6),
    "[One Piece] Hải Quân Thần Thoại - Thức Tỉnh Ứng Long Trấn Áp Đại Hải Trình - Phần 07": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 7),
    "[One Piece] Hải Quân Chi Đỉnh - Huyễn Thú Ứng Long Trấn Áp Đại Hải Trình - Phần 08": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 8),
    "[One Piece] Hải Quân Thần Long - Khai Cục Thức Tỉnh Ứng Long Chấn Thế - Phần 09": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 9),
    "[One Piece] Hải Quân Thần Thoại - Khởi Đầu Hóa Thân Ứng Long, Trấn Áp Đại Hải Trình - Phần 10": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 10),

    # 2. Rocks 16 Tuổi (7 parts)
    "[One Piece] Hải Tặc Kỷ Nguyên - 16 Tuổi Làm Cán Bộ Băng Rocks, Một Kiếm Trảm Đô Đốc - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 1),
    "[One Piece] Hải Tặc - Kỷ Nguyên Rocks, Thiếu Niên Cán Bộ Nhất Kiếm Trảm Đô Đốc - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 2),
    "[One Piece] Kỷ Nguyên Rocks - Mười Sáu Tuổi Nhậm Cán Bộ, Nhất Kiếm Trảm Đô Đốc - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 3),
    "[One Piece] Kỷ Nguyên Rocks - Thiếu Niên Cán Bộ, Nhất Kiếm Trảm Lạc Đô Đốc - Phần 04": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 4),
    "[One Piece] Kỷ Nguyên Rocks - Mười Sáu Tuổi Ngồi Ghế Cán Bộ, Nhất Đao Trảm Lạc Đô Đốc - Phần 05": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 5),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Nhập Tọa Cán Bộ, Nhất Kiếm Trảm Đô Đốc - Phần 06": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 6),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Xưng Cán Bộ, Nhất Đao Trảm Lạc Đô Đốc - Phần 07": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 7),

    # 3. Rocks Phấn Toái (6 parts total)
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 1),
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 2),
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 3),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 4),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 5),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 6),

    # 4. Ace Trùng Sinh (5 parts total)
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 01": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 1),
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 02": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 2),
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 03": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 3),
    "[One Piece] Hỏa Quyền Trọng Sinh - Ta Bái Sư Xích Khuyển, Nghịch Chuyển Vận Mệnh - Phần 01": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 4),
    "[One Piece] Hỏa Quyền Trọng Sinh - Ta Bái Sư Xích Khuyển, Nghịch Chuyển Vận Mệnh - Phần 02": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 5),

    # 5. Luffy Kỷ Nguyên Đỏ (3 parts)
    "[One Piece] Trọng Sinh Thành Luffy, Khai Mở Kỷ Nguyên Đỏ - Phần 01": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 1),
    "[One Piece] Trọng Sinh Thành Luffy, Nhuộm Đỏ Đại Hải Trình - Phần 02": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 2),
    "[One Piece] Ta Là Luffy, Khởi Xướng Kỷ Nguyên Đỏ - Phần 03": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 3),

    # 6. Tam Sắc Haki (3 parts)
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Duy Ngã Thức Tỉnh Tam Sắc Haki - Phần 01": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 1),
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Duy Ta Độc Tôn Tam Sắc Haki - Phần 02": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 2),
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Duy Nhất Ta Thức Tỉnh Tam Sắc Haki - Phần 03": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 3),

    # 7. Doraemon Nobita Toàn Vương (2 parts)
    "[Doraemon (Đồng Nhân - Crossover)] Doraemon - Toàn Vương Nobita - Luyện Hóa Thần Phù, Trấn Áp Chư Thiên - Phần 01": ("[Doraemon (Đồng Nhân)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên", 1),
    "[Doraemon (Đồng Nhân - Crossover)] Doraemon - Toàn Vương Nobita, Thần Long Thức Tỉnh Trấn Áp Chư Thiên - Phần 02": ("[Doraemon (Đồng Nhân)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên", 2),

    # 8. Trái Bóng Tối (2 parts)
    "[Đô Thị Dị Năng - One Piece (Crossover Sức Mạnh)] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần - Phần 01": ("[Đô Thị Dị Năng - One Piece] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần", 1),
    "[Đô Thị Dị Năng - One Piece (Crossover Sức Mạnh)] Kỷ Nguyên Dị Năng - Ta Mang Trái Bóng Tối Thôn Phệ Vạn Thần - Phần 02": ("[Đô Thị Dị Năng - One Piece] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần", 2),

    # 9. Super Saiyan (2 parts)
    "[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan - Phần 01": ("[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan", 1),
    "[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan - Phần 02": ("[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan", 2),
}

# Folders to delete on Drive (corrupted or empty)
PURGE_DRIVE_FOLDERS = [
    "[One Piece] Fanfic - Xuyên Làm Bác Sĩ Băng Rocks - Nắm Giữ Sinh Tử Bằng Trái Ác Quỷ Tế Bào - Phần 01",
]


def run_cmd(cmd: list[str]) -> bool:
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        print(f"  [!] Lỗi ({' '.join(cmd[:3])}...): {res.stderr.strip()[:200]}")
        return False
    return True


def consolidate_google_drive():
    print("=================================================================")
    print("🚀 BẮT ĐẦU CHUẨN HOÁ & GOM GỌN PRODUCTION TRÊN GOOGLE DRIVE...")
    print("=================================================================")

    # 1. Purge corrupted folders
    for pf in PURGE_DRIVE_FOLDERS:
        print(f"🗑️ Đang xoá thư mục hỏng trên Drive: {pf}...")
        run_cmd(["rclone", "purge", f"{DRIVE_BASE}/{pf}"])

    # 2. Consolidate episodes into Series Album folders
    total = len(ALBUM_MAPPING)
    print(f"\n📦 Đang di chuyển {total} thư mục rải rác vào các Album chuẩn...")

    album_covers_copied = set()

    for idx, (old_folder, (album_title, ep_num)) in enumerate(ALBUM_MAPPING.items(), 1):
        target_ep_folder = f"{DRIVE_BASE}/{album_title}/Tập {ep_num:02d}"
        source_folder = f"{DRIVE_BASE}/{old_folder}"

        print(f"[{idx:02d}/{total}] {old_folder} \n     ➜ {album_title}/Tập {ep_num:02d}...")
        # Move all contents of source_folder into target_ep_folder
        run_cmd(["rclone", "move", source_folder, target_ep_folder])

        # Also copy cover.jpg to root of album if not already copied
        if album_title not in album_covers_copied:
            run_cmd(["rclone", "copyto", f"{target_ep_folder}/cover.jpg", f"{DRIVE_BASE}/{album_title}/cover.jpg"])
            album_covers_copied.add(album_title)

        # Remove old empty folder if rclone move left directory
        run_cmd(["rclone", "rmdir", source_folder])

    print("\n✅ GOOGLE DRIVE CONSOLIDATION HOÀN TẤT!")


def consolidate_local_spool():
    print("\n=================================================================")
    print("📁 BẮT ĐẦU CHUẨN HOÁ LOCAL raw_spool/youtube_audio...")
    print("=================================================================")
    if not LOCAL_BASE.exists():
        return

    # Delete broken folders
    for d in LOCAL_BASE.iterdir():
        if d.is_dir() and "Bác Sĩ Băng Rocks" in d.name:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
            print(f"🗑️ Đã xoá thư mục rác cục bộ: {d.name}")

    print("✅ LOCAL SPOOL ĐÃ ĐỒNG BỘ!")


if __name__ == "__main__":
    consolidate_google_drive()
    consolidate_local_spool()
