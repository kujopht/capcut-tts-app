"""KẾ HOẠCH THỰC THI — DAG có phiên bản — V0.9, §3 và §10.

MỘT KẾ HOẠCH KHÔNG PHẢI MỘT DANH SÁCH. Yêu cầu §3 nói thẳng *"Do not make
everything sequential"* và *"Represent dependency structure explicitly"*, nên
cấu trúc ở đây là một DAG có kiểm chu trình, và `cac_lop()` trả về các LỚP
chạy song song được. Một danh sách phẳng sẽ chạy ba việc đọc độc lập nối
đuôi nhau, và người dùng trả giá bằng thời gian thật.

MỘT BẢN SỬA KẾ HOẠCH KHÔNG ĐƯỢC GHI ĐÈ LỊCH SỬ (§10). `KeHoachThucThi` là
bất biến sau khi dựng; lập lại kế hoạch sinh ra bản v2 kèm `ly_do_sua`,
`thay_doi` và `bang_chung_gay_ra`. Bản cũ ở lại trong sổ. Đây không phải sự
cẩn thận thừa: câu hỏi "vì sao nó bỏ bước chạy test?" chỉ trả lời được nếu
bản trước còn đó để so.

XUNG ĐỘT TÀI NGUYÊN DÙNG LẠI `locks.tranh_chap`, không có bản sao ở đây. Luật
READ/READ sống chung, READ/WRITE và WRITE/WRITE loại trừ đã được V0.6.1 đo và
khoá bằng bài kiểm; một bản sao sẽ lệch khỏi nó và hai tầng sẽ bất đồng về
việc gì chạy song song được.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from scripts.control_center.execution.y_dinh import khong_suy_nghi
from scripts.control_center.locks import chuan_mode, tranh_chap
from scripts.control_center.model import LockKind


class KeHoachLoi(ValueError):
    """Kế hoạch không dùng được. FAIL CLOSED — không có 'gần đúng'."""


class CheDoGhi(str, Enum):
    DOC = "READ"
    GHI = "WRITE"

    @property
    def mode_khoa(self) -> str:
        return "read" if self is CheDoGhi.DOC else "write"


class CachKiem(str, Enum):
    """Cách kiểm định một bước. Danh sách ĐÓNG.

    Đóng có chủ đích: `kiem_dinh.py` có một bộ chạy TẤT ĐỊNH cho mỗi giá trị,
    và một tên lạ sẽ không có bộ chạy nào — tức là một bước tự nhận "đã kiểm"
    mà không ai kiểm. Muốn thêm cách kiểm thì thêm ở CẢ HAI chỗ.
    """

    TEP_TON_TAI = "TEP_TON_TAI"
    CHUOI_TRONG_TEP = "CHUOI_TRONG_TEP"
    GIT_CO_THAY_DOI = "GIT_CO_THAY_DOI"
    GIT_TRONG_PHAM_VI = "GIT_TRONG_PHAM_VI"
    TEST_DA_CHAY = "TEST_DA_CHAY"
    UNITTEST_MODULE = "UNITTEST_MODULE"
    BIEN_DICH_PYTHON = "BIEN_DICH_PYTHON"
    CO_ARTIFACT = "CO_ARTIFACT"
    #: Chỉ dùng khi phán đoán NGỮ NGHĨA thật sự cần — xem §7. Đắt, và không
    #: tất định, nên nó không bao giờ là cách kiểm DUY NHẤT của một bước ghi.
    REVIEWER = "REVIEWER"

    @property
    def tat_dinh(self) -> bool:
        return self is not CachKiem.REVIEWER


@dataclass(frozen=True)
class BuocKeHoach:
    """Một bước. Bất biến — dựng một lần, không sửa tại chỗ."""

    buoc_id: str
    tieu_de: str
    muc_tieu: str
    phu_thuoc: Tuple[str, ...] = ()
    #: Năng lực bộ lập lịch phải thoả (`router_v4.capabilities`).
    nang_luc: Tuple[str, ...] = ()
    #: (LockKind, tài nguyên, chế độ) — cùng hình dạng `PlannedTask.resources`.
    tai_nguyen: Tuple[Tuple[LockKind, str, str], ...] = ()
    che_do_ghi: CheDoGhi = CheDoGhi.DOC
    artifact_mong_doi: Tuple[str, ...] = ()
    tieu_chi_dat: Tuple[str, ...] = ()
    #: (CachKiem, tham số) — tham số CÓ KIỂU, không bao giờ là chuỗi lệnh.
    cach_kiem: Tuple[Tuple[CachKiem, Dict], ...] = ()
    rui_ro: str = "LOW"
    #: Lớp vai/model mong muốn: "re" | "thuong" | "manh" | "" (để bộ định
    #: tuyến tự quyết). KHÔNG phải một tên model — xem `reasoning/vai.py`.
    lop_model: str = ""
    task_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.buoc_id or "").strip():
            raise KeHoachLoi("BuocKeHoach: thiếu `buoc_id`")
        if not str(self.muc_tieu or "").strip():
            raise KeHoachLoi(f"{self.buoc_id}: thiếu `muc_tieu`")
        if self.buoc_id in self.phu_thuoc:
            raise KeHoachLoi(f"{self.buoc_id}: phụ thuộc chính nó")

    @property
    def ghi(self) -> bool:
        return self.che_do_ghi is CheDoGhi.GHI

    @property
    def co_kiem_tat_dinh(self) -> bool:
        return any(c.tat_dinh for c, _ in self.cach_kiem)

    def to_dict(self) -> Dict:
        return {"buoc_id": self.buoc_id, "tieu_de": self.tieu_de,
                "muc_tieu": self.muc_tieu,
                "phu_thuoc": list(self.phu_thuoc),
                "nang_luc": list(self.nang_luc),
                "tai_nguyen": [[k.value, r, m] for k, r, m in self.tai_nguyen],
                "che_do_ghi": self.che_do_ghi.value,
                "artifact_mong_doi": list(self.artifact_mong_doi),
                "tieu_chi_dat": list(self.tieu_chi_dat),
                "cach_kiem": [[c.value, dict(p)] for c, p in self.cach_kiem],
                "rui_ro": self.rui_ro, "lop_model": self.lop_model,
                "task_id": self.task_id}

    @classmethod
    def tu_dict(cls, d: Dict) -> "BuocKeHoach":
        d = dict(d or {})
        return cls(
            buoc_id=str(d.get("buoc_id") or ""),
            tieu_de=str(d.get("tieu_de") or ""),
            muc_tieu=str(d.get("muc_tieu") or ""),
            phu_thuoc=tuple(d.get("phu_thuoc") or ()),
            nang_luc=tuple(d.get("nang_luc") or ()),
            tai_nguyen=tuple((LockKind(k), str(r), chuan_mode(m))
                             for k, r, m in (d.get("tai_nguyen") or ())),
            che_do_ghi=CheDoGhi(d.get("che_do_ghi") or "READ"),
            artifact_mong_doi=tuple(d.get("artifact_mong_doi") or ()),
            tieu_chi_dat=tuple(d.get("tieu_chi_dat") or ()),
            cach_kiem=tuple((CachKiem(c), dict(p or {}))
                            for c, p in (d.get("cach_kiem") or ())),
            rui_ro=str(d.get("rui_ro") or "LOW"),
            lop_model=str(d.get("lop_model") or ""),
            task_id=str(d.get("task_id") or ""))


@dataclass(frozen=True)
class TieuChiNghiemThu:
    """MỘT tiêu chí nghiệm thu của CẢ lần thực thi — §8.

    Đây là cơ chế khiến câu *"4 agents returned DONE -> success"* KHÔNG đủ.
    Một tiêu chí không buộc được vào phép kiểm nào thì `cach_kiem` rỗng, và
    `kiem_dinh.py` báo `THIEU_BANG_CHUNG` cho nó — nó KHÔNG mặc nhiên đạt vì
    mọi bước con đều xong.

    `bat_buoc=False` dành cho tiêu chí "nên có": nó vẫn được chấm và vẫn
    hiện trong báo cáo, nhưng không một mình đánh hỏng cả lần thực thi.
    """

    mo_ta: str
    cach_kiem: Tuple[Tuple["CachKiem", Dict], ...] = ()
    bat_buoc: bool = True

    def __post_init__(self) -> None:
        if not str(self.mo_ta or "").strip():
            raise KeHoachLoi("TieuChiNghiemThu: thiếu `mo_ta`")

    @property
    def co_kiem_tat_dinh(self) -> bool:
        return any(c.tat_dinh for c, _ in self.cach_kiem)

    def to_dict(self) -> Dict:
        return {"mo_ta": self.mo_ta,
                "cach_kiem": [[c.value, dict(p)] for c, p in self.cach_kiem],
                "bat_buoc": self.bat_buoc}

    @classmethod
    def tu_dict(cls, d: Dict) -> "TieuChiNghiemThu":
        d = dict(d or {})
        return cls(mo_ta=str(d.get("mo_ta") or ""),
                   cach_kiem=tuple((CachKiem(c), dict(p or {}))
                                   for c, p in (d.get("cach_kiem") or ())),
                   bat_buoc=bool(d.get("bat_buoc", True)))


# ------------------------------------------------------------------- DAG ----

def kiem_dag(buoc: Sequence[BuocKeHoach]) -> None:
    """Kiểm trùng mã, phụ thuộc lạ và CHU TRÌNH. Ném `KeHoachLoi`.

    Chu trình phải bị bắt Ở ĐÂY chứ không lúc chạy: một DAG có vòng sẽ làm
    `cac_lop()` trả về ít bước hơn số bước có, và bộ điều phối sẽ ngồi chờ
    một phụ thuộc không bao giờ xong — trông y hệt một agent treo.
    """
    ma = [b.buoc_id for b in buoc]
    trung = sorted({x for x in ma if ma.count(x) > 1})
    if trung:
        raise KeHoachLoi(f"mã bước trùng: {trung}")
    biet = set(ma)
    for b in buoc:
        la = sorted(set(b.phu_thuoc) - biet)
        if la:
            raise KeHoachLoi(f"{b.buoc_id}: phụ thuộc không tồn tại: {la}")

    mau: Dict[str, int] = {x: 0 for x in ma}        # 0 trang, 1 xam, 2 den
    canh = {b.buoc_id: tuple(b.phu_thuoc) for b in buoc}
    duong: List[str] = []

    def tham(x: str) -> None:
        if mau[x] == 2:
            return
        if mau[x] == 1:
            i = duong.index(x)
            raise KeHoachLoi("kế hoạch có CHU TRÌNH: "
                             + " -> ".join(duong[i:] + [x]))
        mau[x] = 1
        duong.append(x)
        for y in canh[x]:
            tham(y)
        duong.pop()
        mau[x] = 2

    for x in ma:
        tham(x)


def cac_lop(buoc: Sequence[BuocKeHoach]) -> List[List[str]]:
    """Các LỚP chạy song song được, theo thứ tự tô-pô. Kiểm DAG trước.

    Lớp `i` chỉ phụ thuộc vào các lớp `< i`, nên mọi bước trong một lớp là
    độc lập VỀ PHỤ THUỘC. Chúng vẫn có thể đụng nhau về TÀI NGUYÊN — đó là
    việc của `nhom_song_song`.
    """
    kiem_dag(buoc)
    con = {b.buoc_id: set(b.phu_thuoc) for b in buoc}
    ra: List[List[str]] = []
    xong: Set[str] = set()
    while con:
        lop = sorted(x for x, p in con.items() if not (p - xong))
        if not lop:                                 # khong the xay ra sau kiem_dag
            raise KeHoachLoi("không tiến được — DAG hỏng")
        ra.append(lop)
        xong |= set(lop)
        for x in lop:
            con.pop(x)
    return ra


def nhom_song_song(buoc: Sequence[BuocKeHoach], ung_vien: Iterable[str],
                   *, toi_da: int = 0) -> List[str]:
    """Tập con của `ung_vien` chạy CÙNG LÚC được — §17.

    READ/READ sống chung. READ/WRITE và WRITE/WRITE giao nhau thì loại trừ.
    Dùng `locks.tranh_chap`, cùng luật mà `LockManager` sẽ cưỡng chế lúc
    chạy thật — nên bộ điều phối không bao giờ đề nghị một tổ hợp mà tầng
    khoá sẽ từ chối ngay sau đó.

    Duyệt theo thứ tự `ung_vien` (bộ gọi đã xếp ưu tiên), nên kết quả TẤT
    ĐỊNH: cùng đầu vào cho cùng đầu ra.
    """
    theo_ma = {b.buoc_id: b for b in buoc}
    chon: List[BuocKeHoach] = []
    for x in ung_vien:
        b = theo_ma.get(x)
        if b is None:
            continue
        if any(_dung_nhau(b, c) for c in chon):
            continue
        chon.append(b)
        if toi_da and len(chon) >= toi_da:
            break
    return [b.buoc_id for b in chon]


def _dung_nhau(a: BuocKeHoach, b: BuocKeHoach) -> bool:
    for ka, ra, ma in a.tai_nguyen:
        for kb, rb, mb in b.tai_nguyen:
            if ka is kb and tranh_chap(ka, ra, ma, rb, mb):
                return True
    return False


# ------------------------------------------------------------- ke hoach ----

@dataclass
class KeHoachThucThi:
    """Một BẢN kế hoạch. Bản mới không ghi đè bản cũ — §10."""

    execution_id: str
    phien_ban: int = 1
    buoc: Tuple[BuocKeHoach, ...] = ()
    #: Tiêu chí nghiệm thu của CẢ lần thực thi — §8. Sống ở kế hoạch chứ
    #: không ở từng bước, vì mục tiêu gốc là thứ phải đạt, không phải tổng
    #: các bước con.
    nghiem_thu: Tuple[TieuChiNghiemThu, ...] = ()
    ly_do_sua: str = ""
    thay_doi: Tuple[str, ...] = ()
    bang_chung_gay_ra: Tuple[str, ...] = ()
    dang_hieu_luc: bool = True
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.phien_ban < 1:
            raise KeHoachLoi("phiên bản kế hoạch bắt đầu từ 1")
        if self.phien_ban > 1 and not str(self.ly_do_sua or "").strip():
            raise KeHoachLoi(
                f"v{self.phien_ban}: thiếu `ly_do_sua`. Một bản sửa không có "
                f"lý do là một bản ghi đè lịch sử — xem §10.")
        self.ly_do_sua = khong_suy_nghi(self.ly_do_sua, toi_da=1200)
        self.thay_doi = tuple(khong_suy_nghi(x, toi_da=300)
                              for x in self.thay_doi if str(x or "").strip())
        self.bang_chung_gay_ra = tuple(
            str(x)[:200] for x in self.bang_chung_gay_ra if str(x or "").strip())
        kiem_dag(self.buoc)

    # ------------------------------------------------------------ truy van --

    @property
    def ma_buoc(self) -> Tuple[str, ...]:
        return tuple(b.buoc_id for b in self.buoc)

    def buoc_theo_ma(self, ma: str) -> Optional[BuocKeHoach]:
        return next((b for b in self.buoc if b.buoc_id == ma), None)

    @property
    def lop(self) -> List[List[str]]:
        return cac_lop(self.buoc)

    @property
    def co_buoc_ghi(self) -> bool:
        return any(b.ghi for b in self.buoc)

    def san_sang(self, xong: Iterable[str]) -> List[str]:
        """Bước có MỌI phụ thuộc đã xong. Không xét tài nguyên ở đây."""
        d = set(xong)
        return [b.buoc_id for b in self.buoc
                if b.buoc_id not in d and not (set(b.phu_thuoc) - d)]

    def to_dict(self) -> Dict:
        return {"execution_id": self.execution_id,
                "phien_ban": self.phien_ban,
                "buoc": [b.to_dict() for b in self.buoc],
                "nghiem_thu": [t.to_dict() for t in self.nghiem_thu],
                "lop": self.lop,
                "ly_do_sua": self.ly_do_sua,
                "thay_doi": list(self.thay_doi),
                "bang_chung_gay_ra": list(self.bang_chung_gay_ra),
                "dang_hieu_luc": self.dang_hieu_luc,
                "created_at": self.created_at}

    @classmethod
    def tu_dict(cls, d: Dict) -> "KeHoachThucThi":
        d = dict(d or {})
        return cls(execution_id=str(d.get("execution_id") or ""),
                   phien_ban=int(d.get("phien_ban") or 1),
                   buoc=tuple(BuocKeHoach.tu_dict(x)
                              for x in (d.get("buoc") or ())),
                   nghiem_thu=tuple(TieuChiNghiemThu.tu_dict(x)
                                    for x in (d.get("nghiem_thu") or ())),
                   ly_do_sua=str(d.get("ly_do_sua") or ""),
                   thay_doi=tuple(d.get("thay_doi") or ()),
                   bang_chung_gay_ra=tuple(d.get("bang_chung_gay_ra") or ()),
                   dang_hieu_luc=bool(d.get("dang_hieu_luc", True)),
                   created_at=float(d.get("created_at") or time.time()))

    def ban_moi(self, *, buoc: Sequence[BuocKeHoach], ly_do: str,
                thay_doi: Sequence[str] = (),
                bang_chung: Sequence[str] = (),
                nghiem_thu: Optional[Sequence[TieuChiNghiemThu]] = None
                ) -> "KeHoachThucThi":
        """Bản kế tiếp. Bản này KHÔNG bị sửa — chỉ mất `dang_hieu_luc`.

        `nghiem_thu` mặc định GIỮ NGUYÊN của bản cũ, và đó là một rào: lập
        lại kế hoạch để đi vòng qua một tiêu chí nghiệm thu đang hỏng chính
        là cách biến §9 thành một vòng lặp tự khen. Muốn đổi tiêu chí thì
        phải truyền tường minh, và `so_sanh_ban` sẽ nêu nó ra.
        """
        if not str(ly_do or "").strip():
            raise KeHoachLoi("lập lại kế hoạch phải nói VÌ SAO — §10")
        return KeHoachThucThi(
            execution_id=self.execution_id, phien_ban=self.phien_ban + 1,
            buoc=tuple(buoc),
            nghiem_thu=(tuple(nghiem_thu) if nghiem_thu is not None
                        else self.nghiem_thu),
            ly_do_sua=ly_do, thay_doi=tuple(thay_doi),
            bang_chung_gay_ra=tuple(bang_chung), dang_hieu_luc=True)

    def render(self) -> str:
        d = [f"KẾ HOẠCH v{self.phien_ban} — {len(self.buoc)} bước, "
             f"{len(self.lop)} lớp"]
        if self.ly_do_sua:
            d.append(f"  (sửa vì: {self.ly_do_sua})")
        for i, lop in enumerate(self.lop, 1):
            song = " ‖ ".join(lop) if len(lop) > 1 else lop[0]
            d.append(f"  lớp {i}: {song}")
        for b in self.buoc:
            pt = f" ← {', '.join(b.phu_thuoc)}" if b.phu_thuoc else ""
            d.append(f"  • [{b.buoc_id}] {b.tieu_de or b.muc_tieu[:60]} "
                     f"({b.che_do_ghi.value}){pt}")
        return "\n".join(d)


def so_sanh_ban(cu: KeHoachThucThi, moi: KeHoachThucThi) -> List[str]:
    """Khác nhau giữa hai bản, bằng chữ. Đi vào `thay_doi` của bản mới."""
    a, b = set(cu.ma_buoc), set(moi.ma_buoc)
    ra: List[str] = []
    for x in sorted(b - a):
        ra.append(f"THÊM bước {x}")
    for x in sorted(a - b):
        ra.append(f"BỎ bước {x}")
    for x in sorted(a & b):
        p, q = cu.buoc_theo_ma(x), moi.buoc_theo_ma(x)
        if p is None or q is None:
            continue
        if p.muc_tieu != q.muc_tieu:
            ra.append(f"ĐỔI mục tiêu bước {x}")
        if set(p.phu_thuoc) != set(q.phu_thuoc):
            ra.append(f"ĐỔI phụ thuộc bước {x}: "
                      f"{sorted(p.phu_thuoc)} -> {sorted(q.phu_thuoc)}")
        if p.cach_kiem != q.cach_kiem:
            ra.append(f"ĐỔI cách kiểm bước {x}")
    # TIEU CHI NGHIEM THU doi thi phai NEU RA — xem `ban_moi`.
    ta = {t.mo_ta for t in cu.nghiem_thu}
    tb = {t.mo_ta for t in moi.nghiem_thu}
    for x in sorted(tb - ta):
        ra.append(f"THÊM tiêu chí nghiệm thu: {x[:80]}")
    for x in sorted(ta - tb):
        ra.append(f"BỎ tiêu chí nghiệm thu: {x[:80]}  (!)")
    return ra
