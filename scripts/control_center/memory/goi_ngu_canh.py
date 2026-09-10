"""Bộ máy ngữ cảnh — từ ký ức KHÔNG GIỚI HẠN ra một gói HỮU HẠN.

ĐIỀU DUY NHẤT PHẢI ĐÚNG: kích thước gói **độc lập** với kích thước lịch sử.
Một dự án 200 nghìn sự kiện và một dự án 20 sự kiện cho ra gói cùng trần.
Có bài kiểm ép điều này bằng số: nạp lịch sử lớn hơn một cửa sổ ngữ cảnh,
rồi đo gói.

TRẦN TÍNH BẰNG TOKEN, ĐO BẰNG BYTE. `uoc_token()` chia byte UTF-8 cho
`BPT` và kẹp `≤ số byte` — với BPE mức byte đó là chặn trên toán học,
không cần tokenizer. Trần mặc định của khối ký ức là **2 500 token**: nhắc
nhở Leader còn phải chứa hướng dẫn, ảnh chụp, khối sống và hội thoại, và
phiên `agy` có `RecyclePolicy.max_chars = 60 000` — một khối ký ức phình
ra là tự đốt ngân sách của phiên.

CHỌN GÌ. Điểm = **CỘNG** ba thành phần đã min-max trong tập ứng viên
(Generative Agents, Park et al. 2023 — phép cộng, không phải phép nhân;
nhân thì một thành phần 0 giết cả điểm):

    độ mới      = 0.995 ^ (giờ kể từ lần chạm cuối)
    quan trọng  = quan_trong / 10
    liên quan   = hạng FTS (bm25) đã đảo dấu và chuẩn hoá

XẾP Ở ĐÂU. Đầu và cuối gói nhận điểm cao, giữa nhận điểm thấp — đường
cong chữ U của "lost in the middle" (Liu et al. 2023): thứ ở giữa 20 tài
liệu bị đọc kém hơn cả khi không đưa vào. Và câu hỏi được lặp lại ở CUỐI
gói (query-aware contextualization).

KHÔNG có LLM trong đường này. Chọn lọc là tất định, không tốn quota, không
phi xác định, và lặp lại được trong bài kiểm.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.control_center.memory.model import (DiemDung, KyUc, LoaiKyUc,
                                                 VienNang, tuoc_moc, uoc_token)


@dataclass
class NganSach:
    """Trần token cho từng phần của khối ký ức. Tổng ≤ `tong`."""
    tong: int = 2500
    vien_nang: int = 700
    diem_dung: int = 600
    truy_hoi: int = 1000
    chi_muc: int = 200
    #: Một bản ghi vượt mức này thì vào gói dưới dạng CON TRỎ (mã + tiêu
    #: đề), không phải nội dung — Claude Code cũng đổi sang đường dẫn khi
    #: một tệp vượt 5 000 token.
    inline_toi_da: int = 400
    #: Dự trữ cho dòng tiêu đề mà `service.khoi_cho_leader` thêm lên đầu,
    #: để CẢ khối (tiêu đề + thân) vẫn ≤ `tong`.
    du_tru_tieu_de: int = 100


@dataclass
class MucChon:
    ky_uc: KyUc
    diem: float
    do_moi: float
    lien_quan: float
    con_tro: bool = False       # chi ma + tieu de, khong noi dung

    def to_dict(self) -> Dict:
        return {"ma": self.ky_uc.ma, "loai": self.ky_uc.loai.value,
                "tieu_de": self.ky_uc.tieu_de, "diem": round(self.diem, 4),
                "do_moi": round(self.do_moi, 4),
                "lien_quan": round(self.lien_quan, 4),
                "tuoi": round(self.ky_uc.tuoi), "con_tro": self.con_tro}


@dataclass
class GoiNguCanh:
    project_id: str
    cau: str
    vien_nang: Optional[VienNang]
    diem_dung: Optional[DiemDung]
    chon: List[MucChon] = field(default_factory=list)
    bo_qua: int = 0                    # ung vien khong vao goi
    tong_ung_vien: int = 0
    lich_su_so_su_kien: int = 0        # de bai kiem chung minh doc lap
    token_uoc: int = 0
    token_tran: int = 0
    che_do_tim: str = ""
    ts: float = field(default_factory=time.time)
    _van: str = ""

    def render(self) -> str:
        return self._van

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id, "cau": self.cau,
                "vien_nang_phien_ban": (self.vien_nang.phien_ban
                                        if self.vien_nang else 0),
                "diem_dung": self.diem_dung.ma if self.diem_dung else "",
                "chon": [m.to_dict() for m in self.chon],
                "bo_qua": self.bo_qua, "tong_ung_vien": self.tong_ung_vien,
                "lich_su_so_su_kien": self.lich_su_so_su_kien,
                "token_uoc": self.token_uoc, "token_tran": self.token_tran,
                "che_do_tim": self.che_do_tim, "ts": self.ts}


# ----------------------------------------------------------------- điểm ----

def _minmax(xs: Sequence[float]) -> List[float]:
    if not xs:
        return []
    lo, hi = min(xs), max(xs)
    if hi - lo < 1e-12:
        return [1.0 for _ in xs]
    return [(x - lo) / (hi - lo) for x in xs]


def tuoi_chu(giay: float) -> str:
    g = max(0, int(giay))
    if g < 90:
        return f"{g}s trước"
    if g < 5400:
        return f"{g // 60} phút trước"
    if g < 172800:
        return f"{g // 3600} giờ trước"
    return f"{g // 86400} ngày trước"


def _cat_token(van: str, tran: int) -> str:
    """Cắt theo trần token (đo bằng byte) — giữ PHẦN ĐẦU, vì kết luận
    được viết ở đầu mỗi bản ghi."""
    if uoc_token(van) <= tran:
        return van
    b = van.encode("utf-8")
    muc = max(1, int(tran * 2.5) - 16)
    ra = b[:muc].decode("utf-8", "ignore")
    return ra.rstrip() + " …"


class BoMayNguCanh:
    """Dựng gói ngữ cảnh từ một provider. Không ném."""

    def __init__(self, provider, ngan_sach: Optional[NganSach] = None):
        self.p = provider
        self.ns = ngan_sach or NganSach()

    # -- cham diem ----------------------------------------------------------

    def cham_diem(self, ung_vien: List[Tuple[KyUc, float]],
                  now: Optional[float] = None) -> List[MucChon]:
        if not ung_vien:
            return []
        now = now or time.time()
        do_moi = [0.995 ** (max(0.0, now - k.ts_cham) / 3600.0)
                  for k, _ in ung_vien]
        qt = [k.quan_trong / 10.0 for k, _ in ung_vien]
        # `hang` cua FTS la bm25 (am, cang am cang tot) -> dao dau.
        lq = _minmax([-h for _, h in ung_vien])
        dm = _minmax(do_moi)
        qtn = _minmax(qt)
        ra = []
        for i, (k, _) in enumerate(ung_vien):
            diem = 1.0 * dm[i] + 1.0 * qtn[i] + 1.0 * lq[i]
            # Het han (qua TTL) van duoc phep vao, nhung bi phat: no la
            # lich su xa, khong phai boi canh gan.
            if k.het_han:
                diem *= 0.6
            ra.append(MucChon(ky_uc=k, diem=diem, do_moi=do_moi[i],
                              lien_quan=lq[i]))
        ra.sort(key=lambda m: m.diem, reverse=True)
        return ra

    # -- dung goi -----------------------------------------------------------

    def dung(self, cau: str, *, gom_gan_day: int = 12,
             gom_quyet_dinh: bool = True) -> GoiNguCanh:
        pid = getattr(self.p, "project_id", "")
        ok, che_do = self.p.san_sang()
        goi = GoiNguCanh(project_id=pid, cau=cau, vien_nang=None,
                         diem_dung=None, token_tran=self.ns.tong,
                         che_do_tim=che_do if ok else "KHÔNG SẴN")
        if not ok:
            goi._van = ""
            return goi
        try:
            return self._dung(goi, cau, gom_gan_day, gom_quyet_dinh)
        except Exception as exc:                            # noqa: BLE001
            goi.che_do_tim = f"lỗi dựng gói: {type(exc).__name__}: {exc}"[:200]
            goi._van = ""
            return goi

    def _dung(self, goi: GoiNguCanh, cau: str, gom_gan_day: int,
              gom_quyet_dinh: bool) -> GoiNguCanh:
        goi.vien_nang = self.p.vien_nang()
        goi.diem_dung = self.p.nap_diem_dung()
        try:
            # `dem()` chu khong phai `thong_ke()`: cai sau quet toan ven ca
            # so, khong thuoc ve duong nong cua mot luot chat.
            goi.lich_su_so_su_kien = int(self.p.dem().get("su_kien", 0))
        except Exception:                                   # noqa: BLE001
            goi.lich_su_so_su_kien = 0

        # Ung vien: truy hoi theo cau + gan day + quyet dinh hieu luc.
        # KHONG bao gio la "tat ca".
        ung: Dict[str, Tuple[KyUc, float]] = {}
        for k, h in self.p.tim(cau, limit=60):
            ung.setdefault(k.ma, (k, h))
        for k in self.p.liet_ke(limit=gom_gan_day):
            ung.setdefault(k.ma, (k, 0.0))       # hang 0 = khong do lien quan
        if gom_quyet_dinh:
            for qd in self.p.cac_quyet_dinh(chi_hieu_luc=True, limit=20):
                k = self.p.ky_uc(qd.ky_uc_ma)
                if k:
                    ung.setdefault(k.ma, (k, 0.0))
        goi.tong_ung_vien = len(ung)
        xep = self.cham_diem(list(ung.values()))

        # Dong goi theo ngan sach.
        phan: List[str] = []
        dung = 0
        vn_van = self._van_vien_nang(goi.vien_nang)
        if vn_van:
            phan.append(vn_van); dung += uoc_token(vn_van)
        dd_van = self._van_diem_dung(goi.diem_dung)
        if dd_van:
            phan.append(dd_van); dung += uoc_token(dd_van)

        than = self.ns.tong - self.ns.du_tru_tieu_de
        con = max(0, min(self.ns.truy_hoi, than - dung - self.ns.chi_muc))
        chon: List[MucChon] = []
        roi: List[MucChon] = []
        for m in xep:
            # Quyet dinh CON TRO theo do dai GOC cua ban ghi, khong theo dong
            # da cat: `_dong()` cat ve `inline_toi_da`, nen do sau khi cat
            # thi khong bao gio vuot va khong ban ghi nao thanh con tro.
            if uoc_token(m.ky_uc.noi_dung) > self.ns.inline_toi_da:
                m.con_tro = True
            dong = self._dong(m)
            t = uoc_token(dong)
            if t <= con:
                chon.append(m); con -= t
            else:
                roi.append(m)
        goi.chon = chon
        goi.bo_qua = len(roi)

        if chon:
            # Chu U: cao o dau va cuoi, thap o giua.
            sap = _dau_cuoi(chon)
            dong_ra = [self._dong(m) for m in sap]
            phan.append("KÝ ỨC LIÊN QUAN (mỗi dòng: mã · loại · tuổi · nguồn):\n"
                        + "\n".join(dong_ra))
            for m in chon:
                self.p.cham(m.ky_uc.ma)
        if roi:
            chi = ", ".join(f"{m.ky_uc.ma}" for m in roi[:8])
            phan.append(f"({len(roi)} bản ghi liên quan khác không vào gói vì "
                        f"trần token — lấy theo mã: {chi}"
                        + (" …" if len(roi) > 8 else "") + ")")
        # Lap lai cau hoi o CUOI goi (query-aware contextualization).
        if cau.strip():
            phan.append(f"(câu đang trả lời: {tuoc_moc(cau)[:200]})")
        van = "\n\n".join(p for p in phan if p)
        goi._van = _cat_token(van, self.ns.tong - self.ns.du_tru_tieu_de)
        goi.token_uoc = uoc_token(goi._van)
        return goi

    # -- render tung phan ---------------------------------------------------

    def _van_vien_nang(self, vn: Optional[VienNang]) -> str:
        if vn is None or vn.rong():
            return ""
        d = [f"VIÊN NANG DỰ ÁN (phiên bản {vn.phien_ban}, cập nhật "
             f"{tuoi_chu(time.time() - vn.ts)}):"]
        if vn.muc_tieu:
            d.append(f"  mục tiêu: {vn.muc_tieu}")
        if vn.kien_truc:
            d.append(f"  kiến trúc: {vn.kien_truc}")
        if vn.moc_hien_tai:
            d.append(f"  mốc hiện tại: {vn.moc_hien_tai}")
        if vn.quyet_dinh_hieu_luc:
            d.append("  quyết định hiệu lực: " + ", ".join(vn.quyet_dinh_hieu_luc[:8]))
        if vn.rang_buoc:
            d.append("  ràng buộc: " + " | ".join(vn.rang_buoc[:6]))
        if vn.van_de_da_biet:
            d.append("  vấn đề đã biết: " + " | ".join(vn.van_de_da_biet[:6]))
        if vn.moc_gan_day:
            d.append("  mốc gần đây: " + " | ".join(vn.moc_gan_day[:5]))
        return _cat_token(tuoc_moc("\n".join(d)), self.ns.vien_nang)

    def _van_diem_dung(self, dd: Optional[DiemDung]) -> str:
        if dd is None:
            return ""
        d = [f"ĐIỂM DỪNG GẦN NHẤT ({dd.ma}, {tuoi_chu(time.time() - dd.ts)}, "
             f"lý do: {dd.ly_do}):"]
        if dd.muc_tieu:
            d.append(f"  đang làm: {dd.muc_tieu}")
        if dd.da_xong:
            d.append("  đã xong: " + " | ".join(dd.da_xong[:8]))
        if dd.gia_thuyet:
            d.append(f"  giả thuyết: {dd.gia_thuyet}")
        if dd.tep_da_sua:
            d.append("  tệp đã sửa: " + ", ".join(dd.tep_da_sua[:10]))
        if dd.kiem_thu:
            d.append(f"  kiểm thử: {dd.kiem_thu}")
        if dd.chua_xong:
            d.append("  chưa xong: " + " | ".join(dd.chua_xong[:8]))
        if dd.bang_chung:
            d.append("  bằng chứng: " + ", ".join(dd.bang_chung[:6]))
        return _cat_token(tuoc_moc("\n".join(d)), self.ns.diem_dung)

    def _dong(self, m: MucChon) -> str:
        k = m.ky_uc
        dau = f"[{k.ma} · {k.loai.value} · {tuoi_chu(k.tuoi)} · {k.tin_cay.value}]"
        if m.con_tro:
            return f"{dau} {tuoc_moc(k.tieu_de or k.noi_dung[:80])} (dài — lấy theo mã)"
        than = tuoc_moc((k.tieu_de + ": " if k.tieu_de else "") + k.noi_dung)
        than = " ".join(than.split())
        return _cat_token(f"{dau} {than}", self.ns.inline_toi_da)


def _dau_cuoi(xep: List[MucChon]) -> List[MucChon]:
    """Xếp chữ U: điểm cao nhất ở đầu và cuối, thấp ở giữa."""
    if len(xep) <= 2:
        return list(xep)
    dau: List[MucChon] = []
    cuoi: List[MucChon] = []
    for i, m in enumerate(xep):
        (dau if i % 2 == 0 else cuoi).append(m)
    return dau + list(reversed(cuoi))
