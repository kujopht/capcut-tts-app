#!/usr/bin/env python3
"""
Cong nhan cac tac gia DA CO truoc khi he thong duyet ton tai.

VI SAO BAT BUOC PHAI CHAY: moi ho so dang ton tai deu co `author_status = "none"`,
ke ca nguoi da xuat ban muoi truyen. Neu bat co `FAS_AUTHOR_GATE` truoc khi chay
script nay, moi tac gia hien co se mat quyen xuat ban chuong tiep theo cua chinh
truyen ho dang viet — mot loi khoa nguoi dung ra khoi cong viec cua ho, va no am
tham: ho bam "Xuat ban" va nhan mot loi 403.

THU TU TRIEN KHAI DUNG:

    1. trien khai ma nguon (co TAT — khong ai thay gi doi)
    2. chay `python -m scripts.setup_appwrite`      (tao thuoc tinh/bang V2)
    3. chay `python -m scripts.grandfather_authors`  (che thu, KHONG ghi gi)
    4. doc ke hoach, roi `--apply`
    5. doi soat vai ho so bang tay
    6. moi dat `FAS_AUTHOR_GATE=1`

MAC DINH LA CHE THU. Khong co `--apply` thi script nay khong ghi mot byte nao.

An toan khi chay lai: nguoi da `approved` bi bo qua, nguoi dang bi `suspended`
KHONG bao gio bi lat lai — treo la mot quyet dinh cua nguoi, migration khong duoc
ghi de len no.

Chay:
    .venv\\Scripts\\python.exe -m scripts.grandfather_authors
    .venv\\Scripts\\python.exe -m scripts.grandfather_authors --apply
"""

from __future__ import annotations

import sys
from typing import List

# Console Windows mac dinh la cp1252 — xem ghi chu o `setup_appwrite.py`.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: List[str]) -> int:
    ap_dung = "--apply" in argv
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    from server.adapters import build_identity, build_metadata_store
    from server.config import load_settings
    from server.creator_service import CreatorService

    settings = load_settings()
    identity = build_identity(settings)
    store = build_metadata_store(settings)
    service = CreatorService(identity, store)

    print(f"Backend dữ liệu : {settings.data_backend}")
    print(f"Chế độ          : {'ÁP DỤNG THẬT' if ap_dung else 'chạy thử (không ghi gì)'}")
    print()

    ket_qua = service.grandfather_existing_authors(dry_run=not ap_dung)

    for hang in ket_qua["plan"]:
        print(f"  {hang['user_id']:24} {hang['novels']:>3} truyện  ->  {hang['action']}")
    print()
    print(f"Chủ sở hữu có truyện đã xuất bản : {ket_qua['candidates']}")
    print(f"  đã là tác giả                  : {ket_qua['already_approved']}")
    print(f"  SẼ CÔNG NHẬN                   : {ket_qua['would_approve']}")
    print(f"  bỏ qua — đang bị tạm dừng      : {ket_qua['skipped_suspended']}")
    print(f"  bỏ qua — không tìm thấy hồ sơ  : {ket_qua['missing_profile']}")
    if ket_qua["unclassified"]:
        # Mot nhanh moi duoc them ma quen dem. Bao ra thay vi de no bien mat.
        print(f"  KHÔNG PHÂN LOẠI ĐƯỢC          : {ket_qua['unclassified']}")

    if ket_qua["missing_profile"]:
        print()
        print("CẢNH BÁO: có truyện đã xuất bản mà không đọc được hồ sơ chủ sở hữu.")
        print("Xem lại những dòng `bo_qua_khong_tim_thay_ho_so` ở trên trước khi")
        print("chạy --apply: đó có thể là tài khoản đã xoá, hoặc một lỗi đọc.")

    if not ap_dung:
        print()
        print("Chưa ghi gì cả. Thêm --apply để áp dụng thật.")
    else:
        print()
        print("Đã áp dụng. Kiểm tra lại vài hồ sơ bằng tay trước khi bật "
              "FAS_AUTHOR_GATE=1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
