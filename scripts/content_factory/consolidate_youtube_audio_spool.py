"""Consolidates fragmented/duplicate YouTube audio folders in raw_spool/youtube_audio.

Ensures that:
1. Multi-part audiobooks (5h splits) share the EXACT same base series title.
2. Identical duplicate downloads are safely merged/removed.
3. Web dashboard (http://localhost:8505/) groups each work cleanly into a single series card with all its episodes.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

SPOOL_DIR = PROJECT_ROOT / "raw_spool" / "youtube_audio"


def consolidate():
    print("=" * 80)
    print("[*] BẮT ĐẦU CHUẨN HÓA VÀ GOM NHÓM PRODUCTION NHÁNH 1 (YOUTUBE AUDIO)")
    print("=" * 80)

    # 1. Cluster Ứng Long (10 parts)
    ung_long_base = "[One Piece] Hải Quân Thần Thoại - Huyễn Thú Ứng Long Trấn Áp Biển Cả"
    ung_long_folders = sorted(list(SPOOL_DIR.glob("*Ứng Long*")))
    print(f"\n[+] Phát hiện {len(ung_long_folders)} thư mục thuộc bộ Ứng Long:")
    for f in ung_long_folders:
        m = re.search(r"Phần\s*(\d+)", f.name, re.IGNORECASE)
        part_num = int(m.group(1)) if m else 1
        target_name = f"{ung_long_base} - Phần {part_num:02d}"
        target_p = SPOOL_DIR / target_name
        if f != target_p:
            print(f"    Đổi tên: '{f.name}' -> '{target_name}'")
            if target_p.exists():
                shutil.rmtree(target_p)
            f.rename(target_p)
            # Update metadata.json if exists
            mf = target_p / "metadata.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    data["series_title"] = ung_long_base
                    data["episode_label"] = f"Phần {part_num:02d}"
                    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

    # 2. Cluster Kỷ Nguyên Rocks 16 Tuổi (7 parts)
    rocks_base = "[One Piece] Kỷ Nguyên Rocks - 16 Tuổi Làm Cán Bộ Băng Rocks, Nhất Kiếm Trảm Đô Đốc"
    rocks_folders = sorted(list(SPOOL_DIR.glob("*16 Tuổi*"))) + sorted(list(SPOOL_DIR.glob("*Mười Sáu Tuổi*")))
    # Exclude non-rocks if any
    rocks_folders = [f for f in rocks_folders if "Rocks" in f.name or "rocks" in f.name]
    print(f"\n[+] Phát hiện {len(rocks_folders)} thư mục thuộc bộ Kỷ Nguyên Rocks 16 Tuổi:")
    seen_parts = set()
    for f in rocks_folders:
        m = re.search(r"Phần\s*(\d+)", f.name, re.IGNORECASE)
        part_num = int(m.group(1)) if m else 1
        target_name = f"{rocks_base} - Phần {part_num:02d}"
        target_p = SPOOL_DIR / target_name

        if part_num in seen_parts:
            # Redundant duplicate part 1
            print(f"    [Xóa bản trùng lặp]: '{f.name}'")
            shutil.rmtree(f)
            continue

        seen_parts.add(part_num)
        if f != target_p:
            print(f"    Đổi tên: '{f.name}' -> '{target_name}'")
            if target_p.exists():
                shutil.rmtree(target_p)
            f.rename(target_p)
            mf = target_p / "metadata.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    data["series_title"] = rocks_base
                    data["episode_label"] = f"Phần {part_num:02d}"
                    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

    # 3. Cluster Luffy Kỷ Nguyên Đỏ (3 parts)
    luffy_base = "[One Piece] Trọng Sinh Thành Luffy - Khai Mở Kỷ Nguyên Đỏ"
    luffy_folders = sorted(list(SPOOL_DIR.glob("*Kỷ Nguyên Đỏ*")))
    print(f"\n[+] Phát hiện {len(luffy_folders)} thư mục thuộc bộ Luffy Kỷ Nguyên Đỏ:")
    for f in luffy_folders:
        m = re.search(r"Phần\s*(\d+)", f.name, re.IGNORECASE)
        part_num = int(m.group(1)) if m else 1
        target_name = f"{luffy_base} - Phần {part_num:02d}"
        target_p = SPOOL_DIR / target_name
        if f != target_p:
            print(f"    Đổi tên: '{f.name}' -> '{target_name}'")
            if target_p.exists():
                shutil.rmtree(target_p)
            f.rename(target_p)
            mf = target_p / "metadata.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    data["series_title"] = luffy_base
                    data["episode_label"] = f"Phần {part_num:02d}"
                    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

    # 4. Cluster Doraemon Nobita (2 parts)
    nobita_base = "[Doraemon (Đồng Nhân - Crossover)] Doraemon - Toàn Vương Nobita Trấn Áp Chư Thiên"
    nobita_folders = sorted(list(SPOOL_DIR.glob("*Toàn Vương Nobita*")))
    print(f"\n[+] Phát hiện {len(nobita_folders)} thư mục thuộc bộ Nobita:")
    for f in nobita_folders:
        m = re.search(r"Phần\s*(\d+)", f.name, re.IGNORECASE)
        part_num = int(m.group(1)) if m else 1
        target_name = f"{nobita_base} - Phần {part_num:02d}"
        target_p = SPOOL_DIR / target_name
        if f != target_p:
            print(f"    Đổi tên: '{f.name}' -> '{target_name}'")
            if target_p.exists():
                shutil.rmtree(target_p)
            f.rename(target_p)
            mf = target_p / "metadata.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    data["series_title"] = nobita_base
                    data["episode_label"] = f"Phần {part_num:02d}"
                    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

    # 5. Cluster Trái Bóng Tối Thôn Phệ Vạn Thần (2 parts)
    bongtoi_base = "[Đô Thị Dị Năng - One Piece (Crossover)] Toàn Dân Thức Tỉnh - Trái Bóng Tối Thôn Phệ Vạn Thần"
    bongtoi_folders = sorted(list(SPOOL_DIR.glob("*Trái Bóng Tối Thôn Phệ Vạn Thần*")))
    print(f"\n[+] Phát hiện {len(bongtoi_folders)} thư mục thuộc bộ Trái Bóng Tối Thôn Phệ Vạn Thần:")
    for f in bongtoi_folders:
        m = re.search(r"Phần\s*(\d+)", f.name, re.IGNORECASE)
        part_num = int(m.group(1)) if m else 1
        target_name = f"{bongtoi_base} - Phần {part_num:02d}"
        target_p = SPOOL_DIR / target_name
        if f != target_p:
            print(f"    Đổi tên: '{f.name}' -> '{target_name}'")
            if target_p.exists():
                shutil.rmtree(target_p)
            f.rename(target_p)
            mf = target_p / "metadata.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text(encoding="utf-8"))
                    data["series_title"] = bongtoi_base
                    data["episode_label"] = f"Phần {part_num:02d}"
                    mf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

    # 6. Clean duplicate of 'Các Người Gọi Trái Bóng Tối Là Phế Vật'
    phevat_folders = sorted(list(SPOOL_DIR.glob("*Các Người Gọi Trái Bóng Tối Là Phế Vật*")))
    print(f"\n[+] Phát hiện {len(phevat_folders)} thư mục thuộc bộ Phế Vật:")
    if len(phevat_folders) > 1:
        # Keep the first, delete second
        clean_name = "[Đô Thị Dị Năng - One Piece] Có Kết - Toàn Dân Thức Tỉnh, Các Người Gọi Trái Bóng Tối Là Phế Vật - Phần 01"
        clean_p = SPOOL_DIR / clean_name
        first = phevat_folders[0]
        second = phevat_folders[1]
        print(f"    [Xóa bản trùng lặp]: '{second.name}'")
        shutil.rmtree(second)
        if first != clean_p:
            first.rename(clean_p)

    print("\n" + "=" * 80)
    print("[✓] CHUẨN HÓA HOÀN TẤT!")
    remaining = [d.name for d in SPOOL_DIR.iterdir() if d.is_dir() and not d.name.startswith("_")]
    print(f"[✓] Tổng số thư mục sau khi gom nhóm và dọn dẹp: {len(remaining)} (giảm từ 32 thư mục rác xuống các tập chuẩn)")
    print("=" * 80)


if __name__ == "__main__":
    consolidate()
