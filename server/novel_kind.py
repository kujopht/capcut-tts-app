"""Mot ban ghi trong `novels` la TAC PHAM, hay la ha tang?

VI SAO TEP NAY TON TAI.

Collection `novels` dang chua BON loai thuc the khac nhau, va khong co cot nao
phan biet chung. Do that tren kho san xuat 2026-09-12 (56 ban ghi):

    kho chua Audio Studio   10   <- moi nguoi dung MOT cai, khong bao gio
                                    duoc xuat ban; chi de `POST /api/jobs`
                                    co mot `chapter_id` de bam vao
    ban ghi kiem thu/QA      1
    lan media (`work:`)     14   (13 da xuat ban)
    truyen thong thuong     29
    (trong do farmer gat)    2

Hau qua do duoc: bang quan tri dem "43 ban nhap cho duyet" trong khi chi 11
thu su la truyen co gi de doc. Mot the luon khac 0 la mot the bi bo qua — va
ca gia tri cua mot hang doi kiem duyet nam o cho no VE RONG khi het viec.

DAY KHONG PHAI BAN VA CHO MO HINH DU LIEU. Cot `kind` con thieu la no ky
thuat da biet. Tep nay chi gom LUAT PHAN LOAI vao MOT cho, thay vi de no rai
ra frontend, `creator_service`, va tung bai kiem — ba ban sao chac chan se
lech nhau. Khi `kind` co that, xoa tep nay va doi mot cho.

Phan loai doc THE (`tags`) vi do la tin hieu DUY NHAT hien co. The do chinh
ma san pham dat khi tao ban ghi, khong phai do nguoi dung go.
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence

#: Kho chua rieng cua Audio Studio — xem `web/src/lib/workspace.ts`.
#: Mot cai cho MOI nguoi dung. No CO chuong (moi lan tao audio la mot chuong)
#: nen khong the loc bang "co chuong khong"; chi cai the nay phan biet duoc.
THE_KHO_STUDIO = "audio-studio"

#: Ban ghi do bo kiem/canary sinh ra.
THE_KIEM_THU = ("qa-canary", "test")

#: Do may gat (Story Harvester / farmer) tao ra.
THE_FARMER = "Farmer"

#: Lan media (`content_queue`) — the co dang `work:<ma>`.
TIEN_TO_LAN_MEDIA = "work:"

LOAI_KHO_STUDIO = "workspace"
LOAI_KIEM_THU = "test"
LOAI_FARMER = "farmer"
LOAI_MEDIA = "media"
LOAI_TRUYEN = "story"

#: Nhung loai KHONG phai tac pham — khong bao gio hien o hang doi kiem duyet.
LOAI_HA_TANG = (LOAI_KHO_STUDIO, LOAI_KIEM_THU)


def _the(novel: Any) -> Sequence[str]:
    t = getattr(novel, "tags", None)
    if t is None and isinstance(novel, dict):
        t = novel.get("tags")
    return tuple(t or ())


def loai_ban_ghi(novel: Any) -> str:
    """Phan loai MOT ban ghi. Nhan ca dataclass `Novel` lan dict `to_dict()`.

    Thu tu xet la co y: mot kho chua Studio khong bao gio duoc phep roi vao
    mot loai khac chi vi no tinh co mang them mot the nua.
    """
    tags = set(_the(novel))
    if THE_KHO_STUDIO in tags:
        return LOAI_KHO_STUDIO
    if tags & set(THE_KIEM_THU):
        return LOAI_KIEM_THU
    if THE_FARMER in tags:
        return LOAI_FARMER
    if any(str(x).startswith(TIEN_TO_LAN_MEDIA) for x in tags):
        return LOAI_MEDIA
    return LOAI_TRUYEN


def la_tac_pham(novel: Any) -> bool:
    """Co phai mot TAC PHAM that — thu mot nguoi kiem duyet can nhin?

    Lan media VAN tinh la tac pham: 13 truyen dang song tren trang deu thuoc
    lan do. Chi kho chua va ban ghi kiem thu bi loai.
    """
    return loai_ban_ghi(novel) not in LOAI_HA_TANG


def loc_tac_pham(novels: Iterable[Any]) -> list:
    return [n for n in novels if la_tac_pham(n)]
