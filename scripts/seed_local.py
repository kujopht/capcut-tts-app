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
    # Quan tri. Chi la mot nguoi dung binh thuong — quyen den tu BIEN MOI TRUONG
    # `FAS_ADMIN_USER_IDS`, ma script nay dat sau khi biet `user_id` that.
    ("admin@fanfic.local", "Quản Trị Viên", "quantri", "none", 0, 0),
    ("doc@fanfic.local", "Người Đọc Thầm Lặng", "nguoidoc", "none", 0, 0),
    ("cho@fanfic.local", "Hạ Vũ", "havu", "pending", 0, 1),
    ("moi@fanfic.local", "Tân Nguyệt", "tannguyet", "approved", 12, 1),
    ("giua@fanfic.local", "Nam Kujo", "namkujo", "approved", 380, 3),
    ("cao@fanfic.local", "Vọng Thư Nhân", "vongthunhan", "approved", 24_500, 4),
    ("tuchoi@fanfic.local", "Tiểu Mặc", "tieumac", "rejected", 0, 0),
    ("treo@fanfic.local", "Dạ Hành", "dahanh", "suspended", 95, 2),
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
        if trang_thai in ("approved", "suspended"):
            svc.approve(profile.user_id, note="Ổn.")
        if trang_thai == "suspended":
            # Treo CHI chan xuat ban moi. Truyen da dang van cong khai — day cung
            # la mot tinh huong phai nhin duoc tren giao dien quan tri.
            svc.suspend(profile.user_id,
                        note="Tạm dừng để rà soát một chương bị báo cáo.")
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
                # Tac gia BI TREO van giu truyen da xuat ban — do la ca diem cua
                # persona nay: giao dien quan tri phai cho thay treo KHONG go
                # noi dung xuong.
                state=(PublishState.PUBLISHED
                       if trang_thai in ("approved", "suspended")
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


#: Bai dang mo cho bang tin. (email tac gia, noi dung, gan truyen dau tien?)
BAI = [
    ("cao@fanfic.local",
     "Chương 12 đã lên! Lần này Luffy gặp lại người thợ rèn già — và ông ấy "
     "không còn là người nữa.", True),
    ("giua@fanfic.local",
     "Mọi người thích đọc fanfic vào lúc nào trong ngày? Mình toàn viết lúc "
     "2 giờ sáng nên tò mò ai đọc lúc đó không 😅", False),
    ("moi@fanfic.local",
     "Truyện đầu tiên của mình vừa được duyệt! Run quá. Mong mọi người góp ý "
     "nhẹ tay.", False),
    ("doc@fanfic.local",
     "Vừa nghe xong chương 1 của 'Quán trà của Robin' bằng giọng đọc mới. "
     "Ai chưa thử tính năng audio thì thử đi, đọc truyện lúc rửa bát tiện "
     "cực kỳ.", False),
    ("cao@fanfic.local",
     "Một mẹo nhỏ cho ai mới viết: đừng tả cơn bão. Hãy tả cái mũ rơm ướt "
     "sũng dán vào ngực Luffy. Chi tiết nhỏ kể chuyện to.", False),
]


def nap_xa_hoi(settings) -> None:
    """
    Du lieu moi cua tang xa hoi: theo doi, bai, thich, binh luan, bao cao.

    Chay SAU `nap()` vi no tra cuu nguoi va truyen theo du lieu da mo. Moi thao
    tac di qua `SocialService` that — khong ghi thang vao kho — nen thong bao,
    bo dem va nhat ky sinh ra dung nhu khi nguoi that bam.
    """
    from server import main as server_main

    identity = server_main.identity
    store = server_main.store
    social = server_main.social

    ho_so = {}
    for email, *_ in NGUOI:
        token = identity.login(email, MAT_KHAU)
        ho_so[email] = identity.profile_from_token(token)

    # Do thi theo doi: nguoi doc theo doi cac tac gia; tac gia theo doi nhau.
    theo_doi = [
        ("doc@fanfic.local", "cao@fanfic.local"),
        ("doc@fanfic.local", "giua@fanfic.local"),
        ("doc@fanfic.local", "moi@fanfic.local"),
        ("moi@fanfic.local", "cao@fanfic.local"),
        ("giua@fanfic.local", "cao@fanfic.local"),
        ("cho@fanfic.local", "cao@fanfic.local"),
        ("cao@fanfic.local", "giua@fanfic.local"),
    ]
    for nguon, dich in theo_doi:
        social.follow_user(ho_so[nguon], ho_so[dich].user_id)

    # Nguoi doc theo doi truyen dau tien cua tac gia hang cao.
    truyen_cao = store.list_novels(owner_id=ho_so["cao@fanfic.local"].user_id,
                                   published_only=True)
    if truyen_cao:
        social.follow_story(ho_so["doc@fanfic.local"], truyen_cao[0].novel_id)
        social.follow_story(ho_so["moi@fanfic.local"], truyen_cao[0].novel_id)

    # Bai dang. Bai "cap nhat truyen" gan truyen that cua tac gia do.
    bai_ids = []
    for email, chu, gan_truyen in BAI:
        nguoi = ho_so[email]
        if gan_truyen:
            truyen = store.list_novels(owner_id=nguoi.user_id,
                                       published_only=True)
            bai = social.create_post(nguoi, text=chu, kind="story_update",
                                     novel_id=truyen[0].novel_id)
        else:
            bai = social.create_post(nguoi, text=chu)
        bai_ids.append((email, bai["post_id"]))

    # Thich va binh luan vao bai dau tien (cua tac gia hang cao).
    _, bai_dau = bai_ids[0]
    for email in ("doc@fanfic.local", "moi@fanfic.local", "giua@fanfic.local"):
        social.like_post(ho_so[email], bai_dau)
    goc = social.create_comment(ho_so["doc@fanfic.local"], bai_dau,
                                text="Đợi chương này cả tuần! Ông thợ rèn là "
                                     "người của Thế Kỷ Trống Rỗng đúng không?")
    social.create_comment(ho_so["cao@fanfic.local"], bai_dau,
                          text="Đọc tiếp sẽ biết 😉",
                          parent_id=goc["comment_id"])
    social.create_comment(ho_so["moi@fanfic.local"], bai_dau,
                          text="Giọng văn chương này khác hẳn mấy chương đầu, "
                               "thích lắm.")

    # Mot bao cao dang mo — de hang doi kiem duyet co thu de nhin.
    _, bai_hoi = bai_ids[1]
    social.report(ho_so["doc@fanfic.local"], target_kind="post",
                  target_id=bai_hoi, reason="other",
                  detail="Không vi phạm gì, chỉ thử nút báo cáo (dữ liệu mồi).")

    print(f"  {len(theo_doi)} lượt theo dõi, {len(BAI)} bài, "
          f"3 lượt thích, 3 bình luận, 1 báo cáo đang mở")


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
    nap_xa_hoi(settings)

    # Quyen quan tri den tu CAU HINH, khong tu du lieu. `user_id` cua ban mock
    # duoc sinh ngau nhien moi lan chay, nen phai dat sau khi tao xong ho so.
    #
    # `replace` chu khong phai phep gan: `Settings` la frozen dataclass, va do la
    # co y — cau hinh khong duoc doi giua duong chay.
    from dataclasses import replace as _replace
    from server import main as server_main

    admin = server_main.identity.profile_by_username("quantri")
    server_main.settings = _replace(server_main.settings,
                                    admin_user_ids=(admin.user_id,))
    print()
    print(f"Quản trị: admin@fanfic.local  (user_id {admin.user_id})")
    print("Quyền đến từ FAS_ADMIN_USER_IDS — không phải từ một cột trong bảng.")

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
