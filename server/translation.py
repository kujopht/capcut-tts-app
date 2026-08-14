"""
Chinh sach THUAN cho Novel Translation Studio (V5) — khong I/O, khong Appwrite.

Cung triet ly voi `server/social.py`: MOI hang so/ham kiem tra nam o MOT noi,
ca backend lan test deu doc tu day. Tang service (`translation_service.py`)
goi cac ham nay; tang route (`main.py`) chi doi loi thanh ma HTTP.

KIEN TRUC TONG QUAN:

    van ban nguon (paste/txt/epub/docx)
        -> tach CHUONG (neu la ca cuon)
        -> tach DOAN trong tung chuong (tai dung `desktop_app.text_chunker`)
        -> dich tung doan qua `TranslationProvider`, kem NGU CANH
           (Novel Bible + tom tat chuong truoc)
        -> ghep lai thanh ban dich hoan chinh cua chuong
        -> nguoi dung bien tap
        -> nhap vao truyen nhap (Fanfic World that)
        -> (rieng, khong o day) tao audio bang pipeline TTS CO SAN

KHONG dung tts_jobs — day la mot subsystem RIENG (xem `translation_service.py`
va cac bang `translation_*` trong `MockTranslationStore`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

# =============================================================================
# Trang thai job — MOT may trang thai, ghi o MOT noi.
# =============================================================================


class TranslationJobStatus(str, Enum):
    """
    Vong doi mot job dich.

    So voi `tts_jobs` (chi pending/running/completed/failed): dich mot chuong
    la NHIEU buoc that su khac nhau (khong chi "dang chay"), va nguoi dung can
    thay minh dang o buoc nao — "đang phân tích" khac han "đang dịch" ve mat
    ky vong thoi gian cho.
    """

    QUEUED = "queued"
    ANALYZING = "analyzing"
    GLOSSARY = "glossary"
    TRANSLATING = "translating"
    REVIEWING = "reviewing"
    QA = "qa"
    #: Trang thai PHU, khong nam trong may trang thai tuan tu binh thuong
    #: (`buoc_tiep_theo` khong bao gio tra ve gia tri nay). Job roi vao day
    #: khi TAT CA provider (mien phi) tam thoi het han muc/bi gioi han toc
    #: do — KHONG PHAI mot loi that (Part Q4). Worker nha lease voi thoi
    #: diem "khong nhan lai truoc" (tai su dung dung `lease_expires_at`,
    #: `lease_owner=""` — xem `TranslationService._cho_provider`), nen job
    #: tu duoc thu lai khi vong quet tiep theo qua moc do, KHONG dot mat
    #: luot thu nao (xem `TranslationService.recover_stale_jobs`: loai tru
    #: rieng trang thai nay khoi kiem tra vuot tran so lan thu).
    WAITING_FOR_PROVIDER = "waiting_for_provider"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Trang thai KET THUC — job o day khong bao gio tu doi tiep.
TERMINAL_STATUSES = frozenset({
    TranslationJobStatus.COMPLETED,
    TranslationJobStatus.FAILED,
    TranslationJobStatus.CANCELLED,
})

#: Thu tu TIEN TRINH binh thuong (che do CAN_BANG/VAN_HOC). Che do NHANH bo
#: qua GLOSSARY va REVIEWING — xem `QualityMode`.
_TIEN_TRINH_DAY_DU = (
    TranslationJobStatus.QUEUED,
    TranslationJobStatus.ANALYZING,
    TranslationJobStatus.GLOSSARY,
    TranslationJobStatus.TRANSLATING,
    TranslationJobStatus.REVIEWING,
    TranslationJobStatus.QA,
    TranslationJobStatus.COMPLETED,
)


class QualityMode(str, Enum):
    """Ba che do — xem yeu cau goc muc 9. Anh huong SO BUOC job di qua."""

    NHANH = "nhanh"
    CAN_BANG = "can_bang"
    VAN_HOC = "van_hoc"


def buoc_tiep_theo(hien_tai: TranslationJobStatus,
                   che_do: QualityMode) -> TranslationJobStatus:
    """
    Buoc KE TIEP trong may trang thai, theo che do chat luong.

    Che do NHANH: mot lan dich, bo qua GLOSSARY (dung tu dien co san neu co,
    khong tu xay dung moi) va REVIEWING (khong co lan bien tap van hoc rieng).
    CAN_BANG/VAN_HOC: di qua du cac buoc — VAN_HOC khac CAN_BANG o so PASS
    dich (xem `TranslationService`), khong khac o so buoc trang thai.
    """
    if hien_tai in TERMINAL_STATUSES:
        raise ValueError(f"Job đã kết thúc ở trạng thái {hien_tai.value}, "
                         "không có bước kế tiếp.")
    thu_tu = list(_TIEN_TRINH_DAY_DU)
    if che_do is QualityMode.NHANH:
        thu_tu = [b for b in thu_tu
                 if b not in (TranslationJobStatus.GLOSSARY,
                             TranslationJobStatus.REVIEWING)]
    i = thu_tu.index(hien_tai)
    return thu_tu[i + 1]


# =============================================================================
# The loai + xung ho — du lieu, khong phai code cung
# =============================================================================


class GenrePreset(str, Enum):
    TIEN_HIEP = "tien_hiep"
    HUYEN_HUYEN = "huyen_huyen"
    VO_HIEP = "vo_hiep"
    DO_THI = "do_thi"
    NGON_TINH = "ngon_tinh"
    LICH_SU = "lich_su"
    HE_THONG = "he_thong"
    DONG_NHAN = "dong_nhan"
    KINH_DI = "kinh_di"
    AUTO = "auto"


class NamingMode(str, Enum):
    HAN_VIET = "han_viet"
    PINYIN = "pinyin"
    THUAN_VIET = "thuan_viet"
    FANDOM = "fandom"
    AUTO = "auto"


#: Nhan tieng Viet cho giao dien — MOT nguon, giao dien khong tu dich lai.
GENRE_LABELS: Dict[str, str] = {
    GenrePreset.TIEN_HIEP.value: "Tiên hiệp",
    GenrePreset.HUYEN_HUYEN.value: "Huyền huyễn",
    GenrePreset.VO_HIEP.value: "Võ hiệp",
    GenrePreset.DO_THI.value: "Đô thị",
    GenrePreset.NGON_TINH.value: "Ngôn tình",
    GenrePreset.LICH_SU.value: "Lịch sử",
    GenrePreset.HE_THONG.value: "Hệ thống",
    GenrePreset.DONG_NHAN.value: "Đồng nhân",
    GenrePreset.KINH_DI.value: "Kinh dị",
    GenrePreset.AUTO.value: "Tự động nhận diện",
}

NAMING_LABELS: Dict[str, str] = {
    NamingMode.HAN_VIET.value: "Hán Việt",
    NamingMode.PINYIN.value: "Pinyin",
    NamingMode.THUAN_VIET.value: "Việt hoá ngữ nghĩa",
    NamingMode.FANDOM.value: "Thuật ngữ fandom",
    NamingMode.AUTO.value: "Tự động",
}


#: Tu xung ho tieng Trung can xu ly THEO NGU CANH — KHONG map cung mot dai tu
#: Viet duy nhat. Danh sach nay la DAU VAO cho prompt cua provider that (xem
#: `TranslationProvider`); ban mock dung no de gia lap quyet dinh don gian,
#: co the kiem duoc (gioi/quan he), khong phai ban dich chat luong that.
XUNG_HO_CAN_NGU_CANH: Tuple[str, ...] = (
    "你", "我", "您", "师兄", "师姐", "师弟", "师妹", "师父", "前辈", "道友",
    "公子", "小姐", "本座", "本尊", "本王", "朕", "老夫", "老朽", "奴家",
    "妾身", "晚辈", "属下", "弟子",
)


# =============================================================================
# Novel Bible / glossary
# =============================================================================


class GlossaryCategory(str, Enum):
    CHARACTER = "character"
    PLACE = "place"
    ORGANIZATION = "organization"
    POWER_SYSTEM = "power_system"
    ITEM = "item"
    OTHER = "other"


MAX_GLOSSARY_ORIGINAL = 80
MAX_GLOSSARY_TRANSLATED = 80
MAX_GLOSSARY_NOTE = 500
#: Tran so muc tu dien MOI du an — chan mot van ban rac lam phinh du an vo han.
MAX_GLOSSARY_ENTRIES = 2000


@dataclass
class GlossaryEntry:
    """
    Mot muc trong Novel Bible.

    `locked`: nguoi dung da xac nhan ban dich nay la DUNG — provider (that)
    KHONG duoc tu doi khi dich lai. Day la RANG BUOC BAO MAT o tang du lieu,
    khong chi mot goi y prompt: `TranslationService.apply_glossary` phai loc
    theo co nay TRUOC khi ghi ket qua provider tra ve.
    """

    term_id: str
    project_id: str
    category: GlossaryCategory
    original: str
    translated: str
    #: Bo sung tuy loai: pinyin/han_viet cho nhan vat, cap bac cho to chuc...
    aliases: List[str] = field(default_factory=list)
    note: str = ""
    locked: bool = False
    created_at: str = ""
    updated_at: str = ""


def kiem_glossary_entry(*, original: str, translated: str,
                        note: str = "") -> Tuple[str, str, str]:
    """Kiem + chuan hoa mot muc tu dien. Nem `ValueError` voi ly do doc duoc."""
    goc = (original or "").strip()
    dich = (translated or "").strip()
    note = (note or "").strip()
    if not goc:
        raise ValueError("Thiếu từ gốc.")
    if not dich:
        raise ValueError("Thiếu bản dịch.")
    if len(goc) > MAX_GLOSSARY_ORIGINAL:
        raise ValueError(f"Từ gốc vượt quá {MAX_GLOSSARY_ORIGINAL} ký tự.")
    if len(dich) > MAX_GLOSSARY_TRANSLATED:
        raise ValueError(f"Bản dịch vượt quá {MAX_GLOSSARY_TRANSLATED} ký tự.")
    if len(note) > MAX_GLOSSARY_NOTE:
        raise ValueError(f"Ghi chú vượt quá {MAX_GLOSSARY_NOTE} ký tự.")
    return goc, dich, note


def ap_dung_khoa_glossary(
    de_xuat: Dict[str, str], da_khoa: Sequence[GlossaryEntry],
) -> Dict[str, str]:
    """
    Ghi de moi de xuat cua provider bang gia tri DA KHOA cua nguoi dung.

    `de_xuat`: {original -> translated} provider (that) tra ve cho MOT chuong.
    Day la RAO CHAN CUOI CUNG o tang service — provider co the "quen" khoa
    (mot LLM khong dam bao tuan thu tuyet doi mot rang buoc trong prompt), nen
    ket qua CUOI CUNG phai di qua ham nay truoc khi luu.
    """
    ra = dict(de_xuat)
    for muc in da_khoa:
        if muc.locked and muc.original in ra:
            ra[muc.original] = muc.translated
    return ra


# =============================================================================
# Tach CHUONG tu mot van ban Trung van tho
# =============================================================================


#: Nhan dien tieu de chuong pho bien: "第12章", "第十二章 tieu de", "Chapter 12".
#: KHONG tham vong hoan hao — day la mot goi y phan tich, nguoi dung luon xem
#: lai va gop/tach thu cong o buoc "phan tich" (xem yeu cau goc, Bonus).
_MAU_TIEU_DE_CHUONG = re.compile(
    r"^[ \t]*(?:第\s*[0-9〇一二三四五六七八九十百千]+\s*[章回节卷]"
    r"|[Cc]hapter\s+\d+|[Cc]hương\s+\d+)\b.{0,40}$",
    re.MULTILINE,
)


def tach_chuong(van_ban: str) -> List[str]:
    """
    Tach mot van ban tho thanh danh sach CHUONG, theo tieu de nhan dien duoc.

    Khong tim thay tieu de nao (vd nguoi dung dan mot chuong don le) thi tra
    ve NGUYEN VAN BAN nhu mot chuong duy nhat — day KHONG phai loi, chi la
    "tai lieu nay khong co nhieu chuong de tach".
    """
    sach = (van_ban or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not sach:
        return []
    diem = [m.start() for m in _MAU_TIEU_DE_CHUONG.finditer(sach)]
    if not diem:
        return [sach]
    if diem[0] != 0:
        # Co doan TRUOC tieu de chuong dau tien (loi tua, ten truyen...). LUON
        # giu no lai nhu mot "chuong 0" — KHONG BAO GIO am tham bo noi dung
        # nguoi dung dua vao, du chi la mot dong ngan.
        diem = [0] + diem
    ranh_gioi = diem + [len(sach)]
    chuong = []
    for i in range(len(ranh_gioi) - 1):
        doan = sach[ranh_gioi[i]:ranh_gioi[i + 1]].strip()
        if doan:
            chuong.append(doan)
    return chuong


def tach_doan_trong_chuong(noi_dung_chuong: str, gioi_han_ky_tu: int) -> List[str]:
    """
    Tach MOT chuong thanh cac doan vua tam gui cho provider dich.

    Tai dung `desktop_app.text_chunker.chunk_text`: cung mot bai toan (khong
    cat giua doan van/cau) ma pipeline TTS da giai, khong can viet lai. Import
    o TRONG ham (khong o dau file) de tranh mot phu thuoc module-level giua
    hai subsystem doc lap — chi vay MOT ham thuan, khong vay kien truc.
    """
    from desktop_app.text_chunker import chunk_text

    return chunk_text(noi_dung_chuong, limit=gioi_han_ky_tu)


# =============================================================================
# Uoc luong chi phi/dau vao — khong hardcode gia, chi con so co the do duoc
# =============================================================================


def uoc_luong(van_ban: str) -> Dict[str, int]:
    """Uoc luong THO truoc khi dich — hien cho nguoi dung xem truoc khi bam."""
    sach = (van_ban or "").strip()
    so_chuong = max(1, len(tach_chuong(sach))) if sach else 0
    return {
        "characters": len(sach),
        # ~1.5-2 ky tu Trung/token la mot uoc luong pho bien; khong tuyen bo
        # day la con so chinh xac — chi de nguoi dung co mot cam giac ve quy mo.
        "estimated_tokens": int(len(sach) / 1.6),
        "chapters": so_chuong,
    }


# =============================================================================
# Canh bao QA (Part N muc 18) — kiem tra THAT, khong bia dat
# =============================================================================

#: Bat ky ky tu chu Han nao con sot trong ban dich — dau hieu THAT cua mot
#: doan chua duoc dich (provider bo qua/tra nguyen van goc). Day KHONG phai
#: phat hien "chat luong dich kem" (khong the danh gia duoc tu code), chi la
#: mot bao ve co ban: neu con chu Han thi chac chan CO gi do chua dich.
_MAU_KY_TU_HAN = re.compile(r"[一-鿿]")


#: Ranh gioi doan HIEN THI cho nguoi dung (dong trong) — KHAC voi
#: `tach_doan_trong_chuong` (chia theo KICH THUOC de goi provider, don vi ky
#: thuat cua MOT lan goi API, khong phai don vi nguoi dung nghi la "một đoạn").
_MAU_TACH_DOAN_HIEN_THI = re.compile(r"\n\s*\n")


def tach_doan_hien_thi(van_ban: str) -> List[str]:
    """Tach doan cho editor (Part N): nguoi dung chon MOT doan trong danh
    sach nay va bam "dịch lại đoạn này" — don vi khac voi don vi chia nho de
    goi provider (`tach_doan_trong_chuong`)."""
    sach = (van_ban or "").strip()
    if not sach:
        return []
    return [p.strip() for p in _MAU_TACH_DOAN_HIEN_THI.split(sach) if p.strip()]


def phat_hien_canh_bao(van_ban_dich: str) -> List[str]:
    """Danh sach canh bao THAT cho MOT chuong da dich. Rong = khong phat
    hien gi. Cham co chu dich: it canh bao gia con hon bo sot mot canh bao
    that — moi canh bao o day phai la mot dieu kien co the KIEM CHUNG duoc
    tu chinh van ban, khong phai suy doan ve chat luong."""
    canh_bao: List[str] = []
    if van_ban_dich and _MAU_KY_TU_HAN.search(van_ban_dich):
        canh_bao.append(
            "Còn sót ký tự Hán trong bản dịch — có thể có đoạn chưa được dịch.")
    return canh_bao


# =============================================================================
# Loi
# =============================================================================


class TranslationError(Exception):
    """Loi nghiep vu — tang route doi thanh 400."""


class QuotaExceeded(TranslationError):
    """Vuot tran cau hinh (max_chars/job, max_chapters/job, max_jobs dong thoi)."""


class UnsupportedFormat(TranslationError):
    """Dinh dang tep khong ho tro (Phase 1: txt/epub/docx/paste)."""


class ManualEditWouldBeOverwritten(TranslationError):
    """
    Part N: "Khi regen co the ghi de mot sua tay: CANH BAO TRUOC. KHONG BAO
    GIO am tham pha huy sua tay cua nguoi dung."

    Nem khi mot hanh dong tai sinh (regen doan/chuong, chay lai mot pass) sap
    ghi de noi dung ma ban ghi lich su GAN NHAT cua chuong la mot sua tay
    (`pass_type == "manual"`). Tang route doi thanh 409 — frontend hien hop
    thoai xac nhan, goi lai CUNG request voi `force=true` neu nguoi dung dong y.
    """
