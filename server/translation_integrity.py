"""
Kiem tra TINH VEN cua MOT doan dich (V6 cerebras-groq-translation).

Boi canh: benchmark THAT phat hien Cerebras GPT-OSS 120B tra ve HTTP 200 voi
noi dung THIEU — de sot nguyen van chu Han ("到底是谁") va bo sot mot dong
hoi thoai — trong khi tang provider (`_OpenAICompatFreeProvider`) chi coi
"khac 200" hoac "content rong tuyet doi" la that bai. MOT phan hoi 200 VOI
NOI DUNG khong day du van duoc coi la "thanh cong" theo dinh nghia cu — day
la khoang trong file nay lap.

NGUYEN TAC (yeu cau goc): "Never accept a provider response as successful
merely because HTTP returned 200." Moi kiem tra o day la MOT dieu kien co
THE KIEM CHUNG duoc tu chinh van ban (nguon + dich), khong phai suy doan ve
"chat luong van phong" — cung triet ly voi `translation.phat_hien_canh_bao`
(rieng ham do kiem MOT chuong DA GHEP, danh cho hien thi; file nay kiem
TUNG DOAN, danh cho QUYET DINH retry/fallback tu dong).

THIEN VE IT CANH BAO GIA hon la bo sot mot loi that: moi rule deu co nguong
CHU DICH de KHONG bat loi tren dinh dang/dau cau vo hai (yeu cau goc: "Do not
reject harmless punctuation... Keep the implementation conservative enough
to avoid false positives").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from server.translation import MAU_KY_TU_HAN

#: Cac ky tu danh dau mot dong hoi thoai (mo/dong) thuong gap trong fanfic
#: Trung + ban dich Viet — dung de dem SO LUONG dong thoai, khong phai de
#: doi chieu tung ky tu (dau nhap nhau giua Trung/Viet la BINH THUONG, vd
#: 「」 -> "" khi dich).
_MAU_DAU_THOAI = re.compile(r'["“”「」『』]')

#: Dau ket cau HOAN CHINH — dung de phat hien "cat cut": nguon KET THUC bang
#: mot trong nhung dau nay (cau day du) nhung ban dich lai KHONG ket bang bat
#: ky dau nao trong danh sach TUONG UNG (Viet/Latin) -> nghi ngo bi cat cut
#: giua chung. Gom ca dau dong ngoac/dong ngoac kep vi cau hoi thoai thuong
#: ket bang """ chu khong phai dau cham.
_MAU_KET_CAU_NGUON = re.compile(r"[。！？…」』”]$")
_MAU_KET_CAU_DICH = re.compile(r'[.!?…”’"\'）)\]」』]$')

#: Ty le toi thieu (dich/nguon) — duoi nguong nay voi nguon co it nhat 2 dong
#: coi la "mat noi dung dang ke", KHONG chi la gop 2-3 dong thanh 1 cau cho
#: muot van (dieu do van hoc HOAN TOAN hop le, khong phai loi).
_TY_LE_TOI_THIEU_SO_DONG = 0.5


@dataclass(frozen=True)
class IntegrityIssue:
    """Mot van de tinh ven CU THE, KIEM CHUNG duoc — `code` la nhan may doc
    duoc (dung de test/log), `detail` la mo ta tieng Viet cho nguoi (khong
    bao gio lo noi dung day du cua doan dich/nguon qua log, chi mo ta ngan)."""

    code: str
    detail: str


def kiem_tra_tinh_ven(nguon: str, dich: str) -> List[IntegrityIssue]:
    """
    Kiem tra MOT doan dich (nguon Trung -> dich Viet) — tra ve danh sach
    RONG neu khong phat hien van de gi (hop le). KHONG bao gio nem loi — day
    la ham THUAN, tang goi (`TranslationService`) tu quyet dinh lam gi voi
    ket qua (retry/fallback/chap nhan).

    Goi voi CA doan khong phai dich Trung->Viet (vd pass editor/QA, dau vao
    da la tieng Viet) van AN TOAN: nguon khong co chu Han thi rule (3) khong
    bao gio kich hoat (khong the "con sot" cai chua bao gio co).
    """
    van_de: List[IntegrityIssue] = []
    sach_dich = (dich or "").strip()
    sach_nguon = (nguon or "").strip()

    # 1) Rong/qua ngan mot cach bat thuong — RONG da duoc `TranslationProvider`
    # tu chan o tang duoi (nem loi truoc khi ve toi day), nhung kiem lai o
    # day CHO CHAC (rao chan kep, vd mot provider tuong lai khong tuan thu).
    if not sach_dich:
        van_de.append(IntegrityIssue("empty", "Bản dịch rỗng."))
        return van_de  # cac rule sau vo nghia voi chuoi rong, dung som

    # 2) Con sot ky tu Han — CHI kich hoat khi NGUON THAT SU co chu Han de
    # "con sot" (tranh bao gio flag sai mot pass editor/QA tren van ban da
    # la tieng Viet tu dau, dau vao khong co chu Han nao ca).
    if MAU_KY_TU_HAN.search(sach_nguon) and MAU_KY_TU_HAN.search(sach_dich):
        so_ky_tu = len(MAU_KY_TU_HAN.findall(sach_dich))
        van_de.append(IntegrityIssue(
            "han_residue",
            f"Còn sót {so_ky_tu} ký tự Hán chưa dịch trong bản dịch."))

    # 3) Thieu noi dung/dong thoai dang ke — CHI khi nguon co it nhat 2 dong
    # (mot dong duy nhat khong co gi de "mat ty le" so sanh) VA ty le dong
    # dich/nguon THAP HON HAN nguong — gop 2-3 dong thanh 1 cau van hoc BINH
    # THUONG se khong roi xuong duoi nguong nay.
    dong_nguon = [d for d in sach_nguon.split("\n") if d.strip()]
    dong_dich = [d for d in sach_dich.split("\n") if d.strip()]
    if len(dong_nguon) >= 2:
        ty_le = len(dong_dich) / len(dong_nguon)
        if ty_le < _TY_LE_TOI_THIEU_SO_DONG:
            van_de.append(IntegrityIssue(
                "paragraph_loss",
                f"Bản dịch chỉ có {len(dong_dich)}/{len(dong_nguon)} dòng so với nguồn "
                "— có thể đã mất nội dung."))

    # 4) Thieu dong thoai — nguon co dau thoai (co hoi thoai) nhung ban dich
    # KHONG CON dau thoai nao — dau hieu ca doan hoi thoai bi bo qua/tom tat
    # thay vi dich day du. So dem CHENH LECH mot chut (vd 「」 -> "" lam thay
    # doi so luong ky tu dau MOT chut) la BINH THUONG, khong flag; chi flag
    # khi nguon CO dau thoai ma dich HOAN TOAN KHONG CON dau thoai nao.
    if _MAU_DAU_THOAI.search(sach_nguon) and not _MAU_DAU_THOAI.search(sach_dich):
        van_de.append(IntegrityIssue(
            "missing_dialogue",
            "Nguồn có lời thoại nhưng bản dịch không còn dấu thoại nào — "
            "có thể lời thoại đã bị bỏ qua."))

    # 5) Cat cut o cuoi — nguon KET THUC bang mot dau cau HOAN CHINH nhung
    # dich thi KHONG, va dich KHONG PHAI dang do dau bang mot dau thoai MO
    # (truong hop do da duoc rule 4 xu ly rieng) — nghi ngo bi cat cut giua
    # chung (het token/mang loi giua response).
    if (_MAU_KET_CAU_NGUON.search(sach_nguon)
            and not _MAU_KET_CAU_DICH.search(sach_dich)):
        van_de.append(IntegrityIssue(
            "truncated",
            "Nguồn kết thúc trọn câu nhưng bản dịch không kết thúc bằng dấu "
            "câu hoàn chỉnh — có thể bị cắt cụt giữa chừng."))

    return van_de


def tom_tat_van_de(van_de: List[IntegrityIssue]) -> str:
    """Chuoi NGAN mo ta cac van de — dung trong thong diep loi/log, KHONG
    BAO GIO chua noi dung day du cua doan dich (chi ma + mo ta ngan cua tung
    van de, da tu lam sach o `IntegrityIssue.detail`)."""
    return "; ".join(v.detail for v in van_de)
