"""
Tach chuong TONG QUAT cho van ban tac gia THAT tu do (khong theo mot khuon
mau dinh san) — khac `bulk_import_domain.py::parse_txt`, von CO CHU DICH
NGHIEM NGAT (bat buoc dong `=== Tieu de ===`, loi neu khong khop) cho luong
nhap lai co cau truc da biet truoc. O day nguon la file tac gia tu xuat ra
(Google Docs, Word, mot file .txt viet tay nhieu nam...) — khong the doi
mot dinh dang co dinh, va MOT chuong duy nhat (khong tach duoc) van tot hon
tu choi nhap.
"""
from __future__ import annotations

import re
from typing import List

from server.bulk_import_domain import ParsedChapter, chuan_hoa_noi_dung

#: Khop dau dong dang "Chương 12", "Chapter 12", "Ch. 12", "Ch 12" — chi so
#: (khong ho tro so chu "một"/"one") vi do la truong hop ro rang nhat va it
#: bat nham nhat (mot dong noi dung tinh co bat dau bang "Chapter" trong mot
#: cau van thi hiem, nhung "Chapter" + so thi hau nhu chac chan la tieu de).
_MAU_TIEU_DE_CHUONG = re.compile(
    r"^\s*(?:ch(?:ương|apter|\.)?)\s*[:\-]?\s*(\d+)\b",
    re.IGNORECASE,
)

#: Mot dong "tieu de" khong duoc dai qua muc — mot cau van tinh co bat dau
#: giong mau tren (hiem) van se dai hon nhieu so voi mot tieu de chuong that.
_DO_DAI_TOI_DA_TIEU_DE = 120


def split_into_chapters(text: str, *, fallback_title: str = "Chương 1"
                        ) -> List[ParsedChapter]:
    """Tach `text` thanh danh sach `ParsedChapter` theo cac dong khop mau
    tieu de chuong. Neu KHONG tim thay mau nao, tra ve MOT chuong duy nhat
    chua toan bo noi dung (dung `fallback_title`) — khong bao gio nem loi,
    khac han `bulk_import_domain.py::parse_txt`."""
    van_ban = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    dong_list = van_ban.split("\n")

    diem_bat_dau: List[int] = []
    for i, dong in enumerate(dong_list):
        if len(dong) > _DO_DAI_TOI_DA_TIEU_DE:
            continue
        if _MAU_TIEU_DE_CHUONG.match(dong.strip()):
            diem_bat_dau.append(i)

    if not diem_bat_dau:
        noi_dung = chuan_hoa_noi_dung(van_ban)
        if not noi_dung:
            return []
        return [ParsedChapter(title=fallback_title, content=noi_dung)]

    ra: List[ParsedChapter] = []
    # Van ban TRUOC dong tieu de dau tien (loi mo dau, de tang...) duoc GIU
    # LAI thanh mot "Chương 0" thay vi am tham bo — tac gia that thuong co
    # mot doan loi tua/gioi thieu truoc chuong 1.
    dau = "\n".join(dong_list[:diem_bat_dau[0]])
    if chuan_hoa_noi_dung(dau):
        ra.append(ParsedChapter(title="Lời mở đầu", content=chuan_hoa_noi_dung(dau)))

    for idx, start in enumerate(diem_bat_dau):
        end = diem_bat_dau[idx + 1] if idx + 1 < len(diem_bat_dau) else len(dong_list)
        tieu_de = dong_list[start].strip()
        noi_dung = chuan_hoa_noi_dung("\n".join(dong_list[start + 1:end]))
        ra.append(ParsedChapter(title=tieu_de, content=noi_dung))

    return ra
