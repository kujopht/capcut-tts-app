"""
Phan tich tieu de video/chuong fanfic-audio tieng Viet thanh tin hieu CO CAU
TRUC (tap/phan/chuong/mua/ngoai truyen/ban day du), va tinh DO TIN CAY gom
nhom giua hai tieu de — dung cho cac pipeline can quyet dinh "hai video/
chuong nay co phai CUNG mot series khong" TRUOC KHI ghi du lieu that (vi du
mot buoc gom nhom trong Universal Story Scraper, hoac Trusted Video Sources
sau nay — xem ghi chu tich hop o CUOI file).

TAT DINH, KHONG dung LLM: cung dau vao PHAI luon ra cung ket qua, va ket qua
PHAI giai thich duoc (`KetQuaPhanTich.tin_hieu` liet ke TUNG mau da khop,
`KetQuaDoTinCay.ly_do`/`canh_bao` neu ro vi sao mot cap tieu de duoc xep vao
muc do tin cay do) — cung nguyen tac voi `server/episode_parser.py` va
`server/series_fingerprint.py` (pipeline Trusted Video Sources, da chung
minh trong production) nhung O DAY co MOT khac biet thiet ke quan trong: hai
module do GOP CHUNG "tap"/"phan"/"chuong" thanh MOT lop tu khoa duy nhat
(coi la dong nghia, chi can biet "co so hay khong"), con o day BA truc nay
TACH RIENG hoan toan — mot fanfic co the vua co "Phần 2" (dang o phan 2 cua
tac pham) VUA co "Tập 5" (tap thu 5 BEN TRONG phan do), hai con so nay khong
duoc phep de doi/ghi de len nhau. Day cung la ly do file nay nam trong
`server/scraper/` (goi Universal Story Scraper, xem `server/scraper/
__init__.py`) thay vi canh `episode_parser.py`: bai toan o day la phan tich
tieu de fanfic-audio NOI CHUNG, khong rieng gi mot kenh YouTube cu the, va
`server/scraper/` la package DOC LAP voi pipeline Trusted Video Sources
(khong import lan nhau) — vi vay module nay KHONG import tu
`server/episode_parser.py`/`server/series_fingerprint.py`/
`server/video_classifier.py`, du logic co phan tuong tu; xem ghi chu tich
hop o cuoi file ve viec co nen thay the/goi chung sau nay hay khong.

AN TOAN LA UU TIEN SO MOT cho phan gom nhom (`danh_gia_do_tin_cay`): mot cap
tieu de CHI duoc xep muc CAO (auto-group) khi CHINH tin hieu VAN BAN da du
manh — cac tin hieu cau truc (so tap ke can nhau, v.v.) CHI duoc phep NANG
mot cap tu THAP len TRUNG_BINH (dua vao hang doi xem xet), KHONG BAO GIO tu
minh day thang len CAO. Ly do: hai fanfic HOAN TOAN khong lien quan tinh co
dung chung vai tu tieng Viet pho bien (vd ten fandom, "truyện", "audio")
VAN CO THE tinh co co so tap giong/gan nhau — neu de tin hieu so cung du
suc mo khoa muc CAO mot minh, se gop nham hai series khac nhau. Nguyen tac
nay dung y nguyen tinh than "khi con mo ho, chon phuong an AN TOAN hon" da
duoc ap dung o `TrustedSourceService._gom_nhom_ung_vien` (xem docstring
ham do trong `server/trusted_source_service.py`).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Tuple, Union

# =====================================================================
# 1. Trich xuat tin hieu co cau truc tu MOT tieu de
# =====================================================================

#: Tu khoa cho truc "Tập" (episode) — gom ca "ep"/"episode" (tu muon tieng
#: Anh rat pho bien trong tieu de fanfic-audio tieng Viet), CHUA gom "part"/
#: "phần" (truc rieng, xem `_PHAN_TU`) hay "chapter"/"chương" (truc rieng,
#: xem `_CHUONG_TU`) — day CHINH la diem khac biet co chu dich so voi
#: `episode_parser._TU_KHOA` (gop het lam mot).
_TAP_TU = r"(?:tập|tap|episode|ep)"
_PHAN_TU = r"(?:phần|phan|part)"
_CHUONG_TU = r"(?:chương|chuong|chapter)"
_MUA_TU = r"(?:mùa|mua|season)"

#: Dang "Tập 1-10" — DINH LIEN quanh dau gach noi (khong khoang trang) de
#: phan biet voi "Tập 12 - 2024 Remastered" (dau gach la ranh gioi cum tu,
#: co khoang trang hai ben) — cung ky thuat da chung minh trong
#: `episode_parser._RANGE_RE`. Day la mot VIDEO DUY NHAT gom NHIEU tap —
#: goi vao KHONG duoc phep tu doan la "tap dau tien", phai biet ro day la
#: mot DAI (xem `LoaiTap.DAI`).
_TAP_RANGE_RE = re.compile(
    rf"\b{_TAP_TU}\.?\s*#?\s*(\d{{1,4}})[-–—](\d{{1,4}})\b", re.IGNORECASE)
_TAP_SO_RE = re.compile(
    rf"\b{_TAP_TU}\.?\s*#?\s*(\d{{1,4}})\b", re.IGNORECASE)

#: "Phần 2", "P2", "P.2" — tu khoa day du xet TRUOC (dac hieu cao), dang
#: "P2" viet tat CHI xet neu tu khoa day du khong khop (dac hieu thap hon,
#: de nham vao noi khac — vd "1080p1" — nen phai kiem tra ranh gioi tu ca
#: hai phia; \b truoc "P" tu choi vi tri ngay sau mot ky tu chu/so, xem test).
_PHAN_SO_RE = re.compile(
    rf"\b{_PHAN_TU}\.?\s*#?\s*(\d{{1,3}})\b", re.IGNORECASE)
_PHAN_BARE_P_RE = re.compile(r"\bP\.?(\d{1,3})\b", re.IGNORECASE)

#: "Chương 1", "Chương 001" — so co the co so 0 dan dau, `int()` tu dong bo
#: qua nen khong can xu ly rieng.
_CHUONG_SO_RE = re.compile(
    rf"\b{_CHUONG_TU}\.?\s*#?\s*(\d{{1,4}})\b", re.IGNORECASE)

#: "Season 2", "Mùa 2" — truc DOC LAP voi tap/phan/chuong (mot mua co the
#: chua nhieu tap).
_MUA_SO_RE = re.compile(
    rf"\b{_MUA_TU}\.?\s*#?\s*(\d{{1,3}})\b", re.IGNORECASE)

#: "Ngoại truyện" — DANH DAU rieng, KHONG phai mot so tap. Day la mot chuong/
#: tap PHU, NAM NGOAI mach so chinh — pipeline goi vao KHONG duoc gan cho no
#: mot so tap gia dinh nao ca, chi biet "day la ngoai truyen".
_NGOAI_TRUYEN_RE = re.compile(r"\bngoại truyện\b|\bngoai truyen\b", re.IGNORECASE)

#: "Full", "Full bộ", "Tổng hợp", "Trọn bộ", "All in one" — nghia la "VIDEO
#: NAY la TOAN BO tac pham gop lam MOT", KHONG phai so tap (khong duoc hieu
#: nham la "tap 0" hay bi bo qua). Tu "full" TRAN (mot minh, khong di kem
#: "bộ") la tu RUI RO nhat — de trung voi nhan chat luong "Full HD"/"Full
#: 4K" (chi noi ve DO PHAN GIAI, khong noi video la ban gop). `episode_
#: parser._COMPILATION_RE` chap nhan rui ro nay (tai lieu ro trong docstring
#: cua no: hau qua chi la day ve hang doi xem xet, van an toan) — o day
#: XIET CHAT hon MOT BUOC bang loai truong hop "full" di lien ngay truoc mot
#: nhan do phan giai pho bien, giam sai so ma van giu duoc "full"/"trọn bộ"/
#: "tổng hợp" dung mot minh (khong kem nhan do phan giai) nhu tin hieu hop le.
_BAN_DAY_DU_RE = re.compile(
    r"\bfull bộ\b|\bfull bo\b|\btổng hợp\b|\btong hop\b|\btrọn bộ\b|\btron bo\b"
    r"|\ball in one\b|\bfull\b(?!\s*(?:hd|4k|2k|1080p|720p))",
    re.IGNORECASE,
)

#: Bien nguong hop ly cho so — mot bo truyen audio hiem khi vuot qua cac
#: nguong nay; chan gia tri phi ly (vd nham nam "2024" thanh so tap).
_NGUONG_TAP_CHUONG = 10_000
_NGUONG_PHAN_MUA = 1_000


class LoaiTap(str, Enum):
    """Mot video/tieu de dai dien cho MOT tap don le, hay MOT DAI nhieu tap
    gop chung (vd "Tập 1-10") — pipeline goi vao PHAI biet ro de khong am
    tham thu gon mot DAI thanh "tap dau tien"."""

    DON = "don"
    DAI = "dai"


@dataclass
class ThongTinTap:
    """So tap (hoac dai tap) doc duoc tu tieu de."""

    loai: LoaiTap
    bat_dau: int
    ket_thuc: int
    #: Doan van ban khop duoc (de hien tin hieu/go loi) — vd "Tập 1-10".
    van_ban_khop: str = ""

    @property
    def la_dai(self) -> bool:
        return self.loai is LoaiTap.DAI

    @property
    def so_luong(self) -> int:
        """So tap ma dai nay dai dien (1 cho `DON`, `ket_thuc - bat_dau + 1`
        cho `DAI`)."""
        return self.ket_thuc - self.bat_dau + 1


@dataclass
class KetQuaPhanTich:
    """
    Toan bo tin hieu CO CAU TRUC rut duoc tu MOT tieu de — bon truc doc lap
    (`tap`, `phan`, `chuong`, `mua`) cong hai co danh dau dac biet
    (`la_ban_day_du`, `la_ngoai_truyen`). Tieu de KHONG khop mau nao ca van
    tra ve mot instance HOP LE (moi truong = `None`/`False`, `tin_hieu`
    rong) — khong bao gio nem loi, khong bao gio tra `None`.
    """

    tieu_de_goc: str
    tap: Optional[ThongTinTap] = None
    phan: Optional[int] = None
    chuong: Optional[int] = None
    mua: Optional[int] = None
    la_ban_day_du: bool = False
    la_ngoai_truyen: bool = False
    #: Danh sach doan van ban da khop, dang "loai:doan_khop" (vd
    #: "tap_don:Tập 5") — phuc vu giai thich/go loi, KHONG dung de so sanh.
    tin_hieu: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def co_tin_hieu(self) -> bool:
        """False neu tieu de khong khop BAT KY mau nao — vd tieu de tuy y
        khong lien quan, hoac chuoi rong."""
        return bool(self.tin_hieu)


def phan_tich_tieu_de(title: str) -> KetQuaPhanTich:
    """Rut `KetQuaPhanTich` tu MOT tieu de tho — khong bao gio nem loi, ke
    ca voi chuoi rong/None."""
    text = unicodedata.normalize("NFC", title or "")
    tin_hieu: list = []

    tap: Optional[ThongTinTap] = None
    m_dai = _TAP_RANGE_RE.search(text)
    if m_dai is not None:
        dau, cuoi = int(m_dai.group(1)), int(m_dai.group(2))
        if 0 < dau < _NGUONG_TAP_CHUONG and 0 < cuoi < _NGUONG_TAP_CHUONG and cuoi > dau:
            tap = ThongTinTap(LoaiTap.DAI, dau, cuoi, m_dai.group(0))
            tin_hieu.append(f"tap_dai:{m_dai.group(0)}")
    if tap is None:
        m_don = _TAP_SO_RE.search(text)
        if m_don is not None:
            so = int(m_don.group(1))
            if 0 < so < _NGUONG_TAP_CHUONG:
                tap = ThongTinTap(LoaiTap.DON, so, so, m_don.group(0))
                tin_hieu.append(f"tap_don:{m_don.group(0)}")

    phan: Optional[int] = None
    m_phan = _PHAN_SO_RE.search(text)
    if m_phan is None:
        m_phan = _PHAN_BARE_P_RE.search(text)
    if m_phan is not None:
        so = int(m_phan.group(1))
        if 0 < so < _NGUONG_PHAN_MUA:
            phan = so
            tin_hieu.append(f"phan:{m_phan.group(0)}")

    chuong: Optional[int] = None
    m_chuong = _CHUONG_SO_RE.search(text)
    if m_chuong is not None:
        so = int(m_chuong.group(1))
        if 0 < so < _NGUONG_TAP_CHUONG:
            chuong = so
            tin_hieu.append(f"chuong:{m_chuong.group(0)}")

    mua: Optional[int] = None
    m_mua = _MUA_SO_RE.search(text)
    if m_mua is not None:
        so = int(m_mua.group(1))
        if 0 < so < _NGUONG_PHAN_MUA:
            mua = so
            tin_hieu.append(f"mua:{m_mua.group(0)}")

    la_ngoai_truyen = _NGOAI_TRUYEN_RE.search(text) is not None
    if la_ngoai_truyen:
        tin_hieu.append("ngoai_truyen")

    la_ban_day_du = _BAN_DAY_DU_RE.search(text) is not None
    if la_ban_day_du:
        tin_hieu.append("ban_day_du")

    return KetQuaPhanTich(
        tieu_de_goc=title or "", tap=tap, phan=phan, chuong=chuong, mua=mua,
        la_ban_day_du=la_ban_day_du, la_ngoai_truyen=la_ngoai_truyen,
        tin_hieu=tuple(tin_hieu),
    )


# =====================================================================
# 2. Do tuong dong van ban giua hai tieu de
# =====================================================================

#: Tat ca mau tin hieu cau truc o tren, gop lai de CAT KHOI tieu de khi tinh
#: chuoi so sanh ten series (buoc 2 duoi day) — thu tu liet ke QUAN TRONG:
#: `_TAP_RANGE_RE` phai truoc `_TAP_SO_RE` de mot dai "Tập 1-10" bi cat TRON
#: VEN thay vi chi cat phan "Tập 1" va bo sot "-10".
_TIN_HIEU_STRIP_RE = re.compile(
    "|".join(p.pattern for p in (
        _TAP_RANGE_RE, _TAP_SO_RE, _PHAN_SO_RE, _PHAN_BARE_P_RE,
        _CHUONG_SO_RE, _MUA_SO_RE, _NGOAI_TRUYEN_RE, _BAN_DAY_DU_RE,
    )),
    re.IGNORECASE,
)

#: Dau ngoac + noi dung ben trong — nhan chat luong/nguon nhu "[Vietsub]",
#: "(HD)", "【4K】" gan nhu KHONG BAO GIO mang tin hieu ten series, bo het
#: ca cap ngoac lan noi dung thay vi chi bo dau ngoac.
_NGOAC_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|【[^】]*】|『[^』]*』")
_KY_TU_THUA_RE = re.compile(r"[^\w\s]", re.UNICODE)
_KHOANG_TRANG_RE = re.compile(r"\s+")


def _bo_dau_va_thuong(text: str) -> str:
    """Bo dau tieng Viet + ve chu thuong, dung DE SO SANH (khong dung de
    hien thi). Xu ly RIENG 'đ'/'Đ' truoc khi NFKD: day la MOT CHU CAI rieng
    trong bang chu cai tieng Viet (khong phai 'd' ket hop dau nhu 'á' =
    'a'+dau sac), nen NFKD KHONG tu tach no thanh 'd' — bo qua buoc nay se
    khien "đại" va "dai" (cung mot tu, viet khong dau) KHONG khop nhau."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    khong_dau = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return khong_dau.lower()


def _chuoi_so_sanh(text: str) -> str:
    """Chuoi CHUAN HOA DAY DU de so sanh tuong dong: bo ca cap ngoac + noi
    dung ben trong, bo dau + ve thuong, bo dau cau/ky hieu/emoji con lai, gom
    khoang trang thanh mot dau cach, cat hai dau."""
    text = _NGOAC_RE.sub(" ", text or "")
    text = _bo_dau_va_thuong(text)
    text = _KY_TU_THUA_RE.sub(" ", text)
    return _KHOANG_TRANG_RE.sub(" ", text).strip()


def _tieu_de_sach(text: str) -> str:
    """Tieu de sau khi CAT HET tin hieu co cau truc (tap/phan/chuong/mua/
    ngoai truyen/ban day du) roi chuan hoa — phan con lai la ten series (co
    the con sot nhan phu/ten kenh chua duoc dat trong ngoac), dung lam dau
    vao so sanh ten."""
    text = unicodedata.normalize("NFC", text or "")
    text = _TIN_HIEU_STRIP_RE.sub(" ", text)
    return _chuoi_so_sanh(text)


#: Tu DEM (filler) pho bien trong tieu de fanfic-audio tieng Viet — dang DA
#: chuan hoa (bo dau, thuong) vi luon so sanh sau `_chuoi_so_sanh`. MOT MINH
#: cac tu nay KHONG duoc phep la can cu de gop hai video thanh cung mot
#: series (yeu cau an toan ro rang tu dac ta: hai fanfic khac nhau tinh co
#: dung chung vai tu pho bien nhu "truyện"/"audio"/ten fandom KHONG duoc
#: gop). Danh sach CO CHU DICH giu NGAN va CHI gom tu THAT SU chung chung
#: (meta/quang cao), tranh loai nham am tiet ten rieng pho bien (vd KHONG
#: dua "minh" vao du "thuyết minh" rat pho bien, vi "Minh" cung la mot ten
#: nhan vat/ten rieng rat thuong gap).
_TU_DEM = frozenset({
    "truyen", "audio", "convert", "kenh", "channel", "review", "vietsub",
    "full", "hd", "4k", "2k", "official", "tonghop", "update", "capnhat",
    "hoathinh", "phim", "fanfic", "fandom", "radio", "dich", "reup", "upload",
})


def _tach_token_noi_dung(text_sach: str) -> frozenset:
    """Tap token CON Y NGHIA (da bo tu dem) cua mot chuoi da lam sach — dung
    cho phep so Jaccard o `_do_tuong_dong_van_ban`."""
    return frozenset(t for t in text_sach.split() if t and t not in _TU_DEM)


def _do_tuong_dong_van_ban(a: str, b: str) -> Tuple[float, str]:
    """
    Tra `(diem [0.0, 1.0], ly_do)` — so sanh HAI tieu de qua BON buoc, tu
    chat che nhat den long nhat, DUNG o buoc dau tien khop:

    1. Chuan hoa TOAN BO (bo ngoac/dau/hoa-thuong) khop TUYET DOI -> 1.0 —
       trung lap gan nhu chac chan (kha ca nhan chat luong/emoji khac nhau).
    2. Sau khi CAT tin hieu cau truc (tap/phan/chuong/mua/...), phan con lai
       khop TUYET DOI -> 0.97 — cung mot ten series, chi khac so tap/nhan.
    3. Mot ben la TIEN TO cua ben kia (>= 2 token moi ben, tranh tien to MOT
       tu chung chung) -> 0.85 — CUNG trong so 0.85 nhu `server/
       series_fingerprint.py::similarity()` dung cho quan he tien to, giu
       nhat quan ngu nghia "0.85 nghia la gi" xuyen he thong du hai module
       khong dung chung code. LUU Y QUAN TRONG: diem nay KHONG du de tu no
       dat muc CAO trong `danh_gia_do_tin_cay` — chinh docstring cua
       `series_fingerprint.similarity()` da canh bao quan he tien to la
       KHONG BAC CAU va co the la DUONG GIA (vi du kinh dien: "Tiên Nghịch"
       la tien to cua "Tiên Nghịch Ngoại Truyện", nhung mot ben la truyen
       chinh, mot ben la ngoai truyen — hai thu KHAC NHAU); o day chon
       nguong CAO (0.90) cao hon 0.85 mot cach CO CHU DICH de quan he tien
       to luon roi vao hang doi xem xet (TRUNG_BINH) thay vi tu dong gop.
    4. Nguoc lai: Jaccard tren TOKEN NOI DUNG (da bo tu dem, xem `_TU_DEM`)
       — neu MOT trong hai ben khong con token noi dung nao (chi toan tu
       dem, hoac rong), tra 0.0 THANG (khong doan mo ho): tu dem trung mot
       minh KHONG duoc tinh la tin hieu tuong dong.
    """
    full_a, full_b = _chuoi_so_sanh(a), _chuoi_so_sanh(b)
    if full_a and full_a == full_b:
        return 1.0, "tieu de trung tuyet doi sau chuan hoa"

    sach_a, sach_b = _tieu_de_sach(a), _tieu_de_sach(b)
    if sach_a and sach_a == sach_b:
        return 0.97, "ten series trung tuyet doi sau khi cat tin hieu tap/phan/chuong/mua"

    tokens_a, tokens_b = sach_a.split(), sach_b.split()
    if (sach_a and sach_b and len(tokens_a) >= 2 and len(tokens_b) >= 2
            and (sach_a.startswith(sach_b) or sach_b.startswith(sach_a))):
        return 0.85, "mot ten series la tien to cua ten kia"

    noi_dung_a = _tach_token_noi_dung(sach_a)
    noi_dung_b = _tach_token_noi_dung(sach_b)
    if not noi_dung_a or not noi_dung_b:
        return 0.0, "khong du token noi dung (chi con tu dem hoac rong) de so sanh"

    giao = noi_dung_a & noi_dung_b
    hop = noi_dung_a | noi_dung_b
    diem = len(giao) / len(hop) if hop else 0.0
    return diem, f"jaccard token noi dung = {len(giao)}/{len(hop)}"


# =====================================================================
# 3. Do tin cay gom nhom
# =====================================================================

class MucDoTinCay(str, Enum):
    """Muc do tin cay hai tieu de la CUNG mot series:

    - `CAO`: tu dong gop — CHI khi tin hieu VAN BAN da du manh MOT MINH.
    - `TRUNG_BINH`: mo ho that su — cho vao hang doi xem xet thu cong.
    - `THAP`: coi la series ung vien RIENG — KHONG tu dong gop.
    """

    CAO = "cao"
    TRUNG_BINH = "trung_binh"
    THAP = "thap"


@dataclass
class KetQuaDoTinCay:
    """Ket qua `danh_gia_do_tin_cay` — luon kem `ly_do`/`canh_bao` DE GIAI
    THICH DUOC (yeu cau TAT DINH, xem docstring dau file), khong bao gio chi
    tra mot nhan CAO/TRUNG_BINH/THAP tran."""

    muc_do: MucDoTinCay
    diem_tuong_dong: float
    ly_do: str
    #: Tin hieu cau truc XUNG DOT phat hien duoc (vd lech mua, mot ben ngoai
    #: truyen mot ben khong) — CO THE khac rong ngay ca khi `muc_do` la
    #: `CAO` (hien tai thiet ke KHONG cho phep dieu nay xay ra, nhung field
    #: nay van luon duoc dien de nguoi goi tu kiem tra, khong phai doan qua
    #: `ly_do` dang van ban tu do).
    canh_bao: Tuple[str, ...] = field(default_factory=tuple)


#: Diem tu day tro len -> muc CAO, VOI DIEU KIEN khong co canh bao xung dot
#: nao (xem `_danh_gia_mot_cap`). Dat CAO HON 0.85 (trong so quan he tien to
#: o `_do_tuong_dong_van_ban`) mot cach CO CHU DICH — xem giai thich buoc 3
#: trong docstring ham do.
_NGUONG_CAO = 0.90
#: Diem tu day tro len -> it nhat TRUNG_BINH (mo ho that su, dang xem xet).
_NGUONG_TRUNG_BINH = 0.60
#: Diem SAN toi thieu de tin hieu "so tap ke can nhau" duoc phep NANG mot
#: cap tu THAP len TRUNG_BINH — PHAI co it nhat MOT chut lien quan van ban
#: that su (khong phai 0.0 tuyet doi) truoc khi tin hieu so duoc xet toi;
#: xem quy tac an toan trong docstring dau file.
_NGUONG_SAN_TAP_KE_CAN = 0.45


def _tap_ke_can_nhau(a: KetQuaPhanTich, b: KetQuaPhanTich) -> bool:
    """True neu CA HAI ben deu doc duoc mot so tap DON LE va hai so do sat
    nhau (chenh lech <= 1) — mau hinh dien hinh cua hai TAP LIEN TIEP trong
    CUNG mot series (vd tap 5 va tap 6). KHONG xet DAI tap (`LoaiTap.DAI`)
    vi mot DAI dai dien nhieu tap cung luc, "ke can" mat y nghia ro rang."""
    return (
        a.tap is not None and b.tap is not None
        and a.tap.loai is LoaiTap.DON and b.tap.loai is LoaiTap.DON
        and abs(a.tap.bat_dau - b.tap.bat_dau) <= 1
    )


def _danh_gia_mot_cap(tieu_de_a: str, tieu_de_b: str) -> KetQuaDoTinCay:
    diem, ly_do = _do_tuong_dong_van_ban(tieu_de_a, tieu_de_b)
    pt_a, pt_b = phan_tich_tieu_de(tieu_de_a), phan_tich_tieu_de(tieu_de_b)

    canh_bao: list = []
    tran_o_trung_binh = False

    if pt_a.la_ngoai_truyen != pt_b.la_ngoai_truyen:
        canh_bao.append(
            "mot ben la ngoai truyen, ben kia khong — can nguoi kiem tra "
            "truoc khi gop (ngoai truyen la mach PHU, khong cung mach so voi "
            "tap chinh)")
        tran_o_trung_binh = True

    if pt_a.mua is not None and pt_b.mua is not None and pt_a.mua != pt_b.mua:
        canh_bao.append(f"khac mua (mùa {pt_a.mua} vs mùa {pt_b.mua})")
        tran_o_trung_binh = True

    if diem >= _NGUONG_CAO and not tran_o_trung_binh:
        muc_do = MucDoTinCay.CAO
    elif diem >= _NGUONG_TRUNG_BINH:
        muc_do = MucDoTinCay.TRUNG_BINH
    elif diem >= _NGUONG_SAN_TAP_KE_CAN and _tap_ke_can_nhau(pt_a, pt_b):
        muc_do = MucDoTinCay.TRUNG_BINH
        ly_do += "; so tap ke can nhau ho tro them (khong tu du de len muc cao)"
    else:
        muc_do = MucDoTinCay.THAP

    return KetQuaDoTinCay(
        muc_do=muc_do, diem_tuong_dong=diem, ly_do=ly_do,
        canh_bao=tuple(canh_bao),
    )


def danh_gia_do_tin_cay(
    tieu_de_moi: str,
    tieu_de_hoac_alias: Union[str, Iterable[str]],
) -> KetQuaDoTinCay:
    """
    So sanh `tieu_de_moi` voi MOT tieu de khac (truyen mot chuoi), HOAC voi
    TAP HOP ten canonical + alias cua mot series DA CO (truyen mot
    `Iterable[str]`, vd `[series.canonical_name, *series.aliases]`). Voi tap
    hop, so sanh voi TUNG ung vien va lay KET QUA TOT NHAT (diem cao nhat)
    — chi can MOT alias khop la du, khong doi hoi TAT CA alias deu khop.

    Tieu de rong/None khong nem loi — tra ve muc `THAP` voi ly do ro rang.
    """
    if isinstance(tieu_de_hoac_alias, str):
        ung_vien: Tuple[str, ...] = (tieu_de_hoac_alias,)
    else:
        ung_vien = tuple(t for t in tieu_de_hoac_alias if t)

    if not (tieu_de_moi or "").strip() or not ung_vien:
        return KetQuaDoTinCay(
            MucDoTinCay.THAP, 0.0,
            "thieu tieu de hoac danh sach alias de so sanh")

    ket_qua = [_danh_gia_mot_cap(tieu_de_moi, ung) for ung in ung_vien]
    return max(ket_qua, key=lambda r: r.diem_tuong_dong)


__all__ = [
    "LoaiTap",
    "ThongTinTap",
    "KetQuaPhanTich",
    "phan_tich_tieu_de",
    "MucDoTinCay",
    "KetQuaDoTinCay",
    "danh_gia_do_tin_cay",
]


# =====================================================================
# Ghi chu tich hop (CHUA thuc hien — xem yeu cau "khong dong cham
# trusted_source_service.py" cua buoc nay)
# =====================================================================
#
# `server/trusted_source_service.py` hien dung `episode_parser.py` +
# `series_fingerprint.py` cho toan bo pipeline Trusted Video Sources
# (Auto-Ingestion Phase 1 + Phase 5), da duoc chung minh trong production.
# Module nay KHONG thay the chung ngay — day la mot bo cong cu STANDALONE,
# manh hon o vai diem cu the (tach rieng tap/phan/chuong thay vi gop chung,
# them truc mua/ngoai truyen, va co san mot ham danh-gia-do-tin-cay ba muc
# CAO/TRUNG_BINH/THAP thay vi mot con so tuong dong tho).
#
# Neu sau nay muon noi vao `trusted_source_service.py`, ung vien ro rang
# nhat la thay `SeriesFingerprint.similarity()` (dung trong
# `_gom_nhom_ung_vien`/nhung noi khac can "hai tieu de co giong nhau
# khong") bang `danh_gia_do_tin_cay()` — nhung LUU Y: `_gom_nhom_ung_vien`
# hien CO CHU DICH KHONG dung similarity() de gom nhom (chi dung khop chuoi
# tuyet doi qua `normalized_key`, xem docstring ham do giai thich vi sao
# similarity() KHONG bac cau va rui ro "one ambiguous bridge video"); muon
# thay bang `danh_gia_do_tin_cay` o do se can thiet ke lai buoc gom nhom
# (vd chi gop khi CAO, day TRUNG_BINH ra hang doi rieng thay vi cum tu
# dong) chu khong phai thay the 1-1. Day la cong viec tich hop RIENG, ngoai
# pham vi file nay.
