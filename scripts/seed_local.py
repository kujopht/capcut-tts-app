#!/usr/bin/env python3
"""
Backend CUC BO co san du lieu mau — de xem va chup giao dien.

Script nay LAM CA HAI VIEC trong MOT tien trinh: nap du lieu vao kho mock roi
chay uvicorn. Ly do phai gop: kho mock song trong bo nho cua tien trinh, nen mot
script seed rieng se nap vao mot tien trinh roi chet, con backend thi van rong.

VA QUAN TRONG HAN: nho vay khong can them mot endpoint "duyet don" nao ca. Cac
thao tac duyet/treo di thang qua `CreatorService` trong cung tien trinh. Mot
endpoint duyet du chi bat o che do mock van la mot cai cong — va cai cong do se
o lai trong ma nguon rat lau sau khi ly do tao ra no bi quen.

TU DUNG neu cau hinh khong phai `mock`. Mot lenh seed lo tay chay trung mot kho
that la thu khong sua lai duoc.

Chay:
    DATA_BACKEND=mock .venv\\Scripts\\python.exe -m scripts.seed_local --port 8100
"""

from __future__ import annotations

import sys
from typing import List

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

MAT_KHAU = "matkhau123"

#: (email, ten hien thi, username, trang thai, so luot nghe, so truyen)
#:
#: Sau tinh huong ma giao dien phai ve KHAC NHAU. Thieu mot cai la mot trang thai
#: khong ai nhin thay truoc khi nguoi that roi vao no.
NGUOI = [
    ("doc@fanfic.local", "Người Đọc Thầm Lặng", "nguoidoc", "none", 0, 0),
    ("cho@fanfic.local", "Hạ Vũ", "havu", "pending", 0, 1),
    ("moi@fanfic.local", "Tân Nguyệt", "tannguyet", "approved", 12, 1),
    ("giua@fanfic.local", "Nam Kujo", "namkujo", "approved", 380, 3),
    ("cao@fanfic.local", "Vọng Thư Nhân", "vongthunhan", "approved", 24_500, 4),
    ("tuchoi@fanfic.local", "Tiểu Mặc", "tieumac", "rejected", 0, 0),
]

TRUYEN = [
    ("Vua Hải Tặc và cơn mưa Grand Line",
     "Luffy lạc khỏi băng Mũ Rơm sau một trận bão. Trên hòn đảo không tên, cậu "
     "gặp một thợ rèn già biết quá nhiều về Thế Kỷ Trống Rỗng.",
     ["One Piece", "Phiêu lưu", "Giả tưởng"]),
    ("Nami và bản đồ của những vì sao",
     "Một tấm hải đồ vẽ bầu trời thay vì mặt biển. Nami nhận ra nó chỉ đúng một "
     "lần mỗi năm.",
     ["One Piece", "Tình cảm"]),
    ("Zoro lạc đường lần thứ một nghìn",
     "Zoro rẽ trái ở ngã ba và tới thẳng một thế giới khác. Truyện kể lại ba "
     "ngày đầu tiên của cậu ở đó.",
     ["One Piece", "Hài hước"]),
    ("Quán trà của Robin",
     "Sau khi mọi chuyện kết thúc, Robin mở một quán trà nhỏ ở một thị trấn "
     "không ai biết tên.",
     ["One Piece", "Đời thường"]),
]


def nap(settings) -> None:
    from server import main as server_main
    from server.creator_service import CreatorService
    from server.domain import AuthorStats, Chapter, Novel, PublishState

    identity = server_main.identity
    store = server_main.store
    svc: CreatorService = server_main.creators

    for i, (email, ten, username, trang_thai, nghe, so_truyen) in enumerate(NGUOI):
        profile = identity.register(email, MAT_KHAU, ten)
        svc.set_username(profile, username)

        if trang_thai != "none":
            svc.apply(
                profile,
                pen_name=ten,
                bio=f"{ten} viết fanfic One Piece bằng tiếng Việt.",
                genres=["One Piece", "Phiêu lưu"],
                intro="Tôi viết fanfic đã vài năm, chủ yếu về băng Mũ Rơm.",
                accepted_rules=True,
            )
        if trang_thai == "approved":
            svc.approve(profile.user_id, note="Ổn.")
        elif trang_thai == "rejected":
            svc.reject(
                profile.user_id,
                note="Phần giới thiệu còn quá ngắn — hãy viết thêm vài dòng về "
                     "truyện bạn định viết, rồi gửi lại giúp mình nhé.",
            )

        # Uy tin: dat THANG vao ban tong hop. Tao 24 nghin ban ghi luot nghe chi
        # de xem mot cai huy hieu la mot phep doi vo ly.
        if nghe:
            store.save_stats(AuthorStats(user_id=profile.user_id,
                                         qualified_listens=nghe,
                                         published_novels=so_truyen))

        for j in range(so_truyen):
            tieu_de, mo_ta, the = TRUYEN[j % len(TRUYEN)]
            novel = store.create_novel(Novel(
                owner_id=profile.user_id,
                title=tieu_de if i == 3 else f"{tieu_de} ({ten})",
                description=mo_ta,
                tags=list(the),
                state=(PublishState.PUBLISHED if trang_thai == "approved"
                       else PublishState.DRAFT),
            ))
            store.create_chapter(Chapter(
                novel_id=novel.novel_id,
                owner_id=profile.user_id,
                title="Chương 1 — Hòn đảo không tên",
                content=(
                    "Mưa rơi suốt ba ngày liền.\n\n"
                    "Luffy tỉnh dậy trên bãi cát đen, mũ rơm vẫn còn trên ngực. "
                    "Cậu ngồi dậy, nhìn quanh. Không có Sunny. Không có Zoro. "
                    "Không có ai cả.\n\n"
                    "— Ơ? — cậu gãi đầu. — Mọi người đâu rồi?\n\n"
                    "Tiếng búa vọng lại từ phía rừng. Đều đặn, kiên nhẫn, như "
                    "thể đã gõ suốt trăm năm."
                ),
                order_index=1,
                state=PublishState.PUBLISHED,
            ))


def main(argv: List[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    port = 8100
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])

    from server.config import load_settings

    settings = load_settings()
    if settings.data_backend != "mock":
        print(f"DỪNG: DATA_BACKEND={settings.data_backend!r}, không phải 'mock'.")
        print("Script này CHỈ chạy với kho trong bộ nhớ.")
        return 2

    nap(settings)

    print(f"Kho mock đã có dữ liệu mẫu. Đăng nhập bằng mật khẩu: {MAT_KHAU}")
    for email, ten, username, tt, nghe, _ in NGUOI:
        print(f"  {email:22} {ten:22} @{username:14} {tt:9} {nghe:>6} lượt nghe")
    print()
    print(f"Backend: http://127.0.0.1:{port}")

    import uvicorn

    uvicorn.run("server.main:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
