"""Consolidates local raw_spool/youtube_audio folders into matching 9 Series Albums.
"""

import os
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LOCAL_BASE = Path(__file__).resolve().parents[2] / "raw_spool" / "youtube_audio"

# Map the 40 local folders to the clean 9 Series Albums
LOCAL_ALBUM_MAPPING = {
    # 1. Hải Quân Thần Thoại - Huyễn Thú Ứng Long (10 tập)
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 01": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 1),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 02": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 2),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 03": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 3),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 04": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 4),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 05": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 5),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 06": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 6),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 07": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 7),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 08": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 8),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 09": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 9),
    "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả - Phần 10": ("[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả", 10),

    # 2. Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks (7 tập)
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 1),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 2),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 3),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 04": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 4),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 05": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 5),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 06": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 6),
    "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc - Phần 07": ("[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc", 7),

    # 3. Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái (6 tập)
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 1),
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 2),
    "[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 3),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 01": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 4),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 02": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 5),
    "[One Piece] Kỷ Nguyên Rocks - Quyền Năng Phấn Toái Rung Chuyển Biển Cả - Phần 03": ("[One Piece] Kỷ Nguyên Rocks - Ta Nắm Giữ Quyền Năng Phấn Toái", 6),

    # 4. Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý (5 tập)
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 01": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 1),
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 02": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 2),
    "[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý - Phần 03": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 3),
    "[One Piece] Hỏa Quyền Trọng Sinh - Ta Bái Sư Xích Khuyển, Nghịch Chuyển Vận Mệnh - Phần 01": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 4),
    "[One Piece] Hỏa Quyền Trọng Sinh - Ta Bái Sư Xích Khuyển, Nghịch Chuyển Vận Mệnh - Phần 02": ("[One Piece] Hỏa Quyền Trùng Sinh - Ta Chọn Khoác Lên Áo Choàng Công Lý", 5),

    # 5. Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ (3 tập)
    "[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ - Phần 01": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 1),
    "[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ - Phần 02": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 2),
    "[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ - Phần 03": ("[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ", 3),

    # 6. Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki (3 tập)
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki - Phần 01": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 1),
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki - Phần 02": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 2),
    "[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki - Phần 03": ("[One Piece (Đồng Nhân) - Đô Thị Dị Năng] Kỷ Nguyên Trái Ác Quỷ - Thức Tỉnh Tam Sắc Haki", 3),

    # 7. Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên (2 tập)
    "[Doraemon (Đồng Nhân - Crossover)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên - Phần 01": ("[Doraemon (Đồng Nhân)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên", 1),
    "[Doraemon (Đồng Nhân - Crossover)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên - Phần 02": ("[Doraemon (Đồng Nhân)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên", 2),

    # 8. Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần (2 tập)
    "[Đô Thị Dị Năng - One Piece (Crossover)] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần - Phần 01": ("[Đô Thị Dị Năng - One Piece] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần", 1),
    "[Đô Thị Dị Năng - One Piece (Crossover)] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần - Phần 02": ("[Đô Thị Dị Năng - One Piece] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần", 2),

    # 9. Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan (2 tập)
    "[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan - Phần 01": ("[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan", 1),
    "[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan - Phần 02": ("[One Piece x Dragon Ball] Kỷ Nguyên Rocks - Ta Thức Tỉnh Huyết Mạch Siêu Saiyan", 2),
}


def run_local_consolidation():
    print("=================================================================")
    print("📁 BẮT ĐẦU CHUẨN HOÁ LOCAL raw_spool/youtube_audio VÀO 9 ALBUM...")
    print("=================================================================")

    albums_created = set()

    for old_name, (album_title, ep_num) in LOCAL_ALBUM_MAPPING.items():
        src_dir = LOCAL_BASE / old_name
        if not src_dir.exists():
            print(f"[-] Bỏ qua (không tìm thấy): {old_name}")
            continue

        album_dir = LOCAL_BASE / album_title
        album_dir.mkdir(parents=True, exist_ok=True)

        ep_dir = album_dir / f"Tập {ep_num:02d}"
        if ep_dir.exists():
            shutil.rmtree(ep_dir, ignore_errors=True)

        print(f"[+] Di chuyển: {old_name}\n     ➜ {album_title}/Tập {ep_num:02d}...")
        try:
            shutil.move(str(src_dir), str(ep_dir))
        except Exception as e:
            print(f"[!] Lỗi khi di chuyển: {e}")
            continue

        # Copy cover to album root if not already there
        album_cover = album_dir / "cover.jpg"
        ep_cover = ep_dir / "cover.jpg"
        if not album_cover.exists() and ep_cover.exists():
            shutil.copy(str(ep_cover), str(album_cover))

        albums_created.add(album_title)

    print("\n=================================================================")
    print(f"✅ ĐÃ CHUẨN HOÁ XONG {len(albums_created)} ALBUM TRÊN LOCAL SPOOL!")
    print("=================================================================")


if __name__ == "__main__":
    run_local_consolidation()
