"""TẦNG KIỂM ĐỊNH — tất định trước, ngữ nghĩa sau — V0.9, §7 và §8.

BA LUẬT, và cả ba đều là phản ứng với một chế độ hỏng có thật:

1. **TẤT ĐỊNH TRƯỚC.** Một bài kiểm chạy xong, một tệp có tồn tại hay không,
   `git` có thấy thay đổi hay không — những thứ đó trả lời được mà không cần
   một model nào. Gọi Reviewer để hỏi "code này có đúng không?" trong khi
   `python -m unittest` trả lời được là vừa đắt vừa kém tin.
2. **MÔI GIỚI CÓ KIỂU, KHÔNG NHẬN CHUỖI LỆNH.** Cùng khuôn `probe_van_hanh.
   py` của V0.7: API nhận tham số đã kiểm, tự dựng `argv`, và không có đường
   nào cho một chuỗi tuỳ ý trở thành lệnh. Một `cach_kiem` có trường
   `"lenh": "rm -rf /"` sẽ bị BỎ QUA vì không bộ chạy nào đọc trường đó.
3. **KIỂM THEO MỤC TIÊU GỐC, KHÔNG THEO TỔNG CÁC BƯỚC** (§8). Bốn việc con
   cùng báo DONE không chứng minh "sửa xong đồng thời đa agent". Nên
   `kiem_dinh_thuc_thi` chấm `KeHoachThucThi.nghiem_thu` — và một tiêu chí
   không có phép kiểm nào là `THIEU_BANG_CHUNG`, KHÔNG phải `DAT`.

VÀ MỘT ĐIỀU NỮA (§7): *"Do not pretend model agreement is deterministic
proof."* Reviewer đồng ý thì cao nhất cũng chỉ tới `SUY_GIAM` khi nó không
độc lập được về họ model — `hoi_dong.py` của V0.8 đã đo và báo điều đó, và ở
đây ta chỉ chuyển tiếp sự thật đó chứ không làm đẹp nó.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from scripts.control_center.execution.ke_hoach import (BuocKeHoach, CachKiem,
                                                       CheDoGhi,
                                                       KeHoachThucThi,
                                                       TieuChiNghiemThu)
from scripts.control_center.execution.ket_qua import (HopDongKetQua,
                                                      MucBangChung,
                                                      TrangThaiXacMinh,
                                                      du_bang_chung)
from scripts.control_center.execution.y_dinh import YDinhThucThi, khong_suy_nghi
from scripts.control_center.probe_van_hanh import la_tep_bi_mat
from scripts.router_v3.tien_trinh import an_cua_so

#: Trần thời gian cho MỘT phép kiểm tất định. Một phép kiểm treo là một lần
#: thực thi treo, và §9 không có cách nào cứu nó nếu nó không bao giờ trả về.
HAN_GIAY = 300.0

#: Tên module bài kiểm được phép chạy. KHÔNG phải một chuỗi lệnh: tham số đi
#: qua `_ten_module_hop_le` rồi được ghép vào `argv` cố định.
import re as _re
_TEN_MODULE = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _boc_an_cua_so(argv: Sequence[str], *, cwd: str,
                   han_giay: float) -> "subprocess.CompletedProcess":
    """MỘT chỗ duy nhất trong module này sinh tiến trình con — V0.4 §14b.

    Bọc một lần thay vì thêm `**an_cua_so()` ở từng điểm gọi, và đó là hình
    dạng MẠNH HƠN: một phép kiểm thêm về sau được phủ tự động, không phụ
    thuộc người viết có nhớ hay không. `test_control_center_ux_v04` nhận ra
    khuôn này bằng chính tên hàm — nó bắt được cả một *runner được tiêm*
    (`self._chay([...])`), nên một bản quét đúng sẽ báo động nếu ai đó gọi
    thẳng `subprocess.run` ở đây về sau.

    Không có cửa sổ console nào được nhấp lên: bản `--noconsole` chạy đúng
    những lệnh này mỗi lần kiểm định một bước, và mỗi lần nhấp là một lần
    giành focus của người dùng.
    """
    return subprocess.run(list(argv), cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=han_giay, **an_cua_so())


class KiemLoi(RuntimeError):
    """Phép kiểm không chạy được vì THAM SỐ sai. Khác hẳn "kiểm xong, hỏng"."""


@dataclass
class KetQuaKiem:
    """MỘT phép kiểm, kèm nguồn gốc đủ để dựng lại phán quyết."""

    cach: str
    dat: bool
    chi_tiet: str = ""
    tham_so: Dict = field(default_factory=dict)
    tat_dinh: bool = True
    giay: float = 0.0
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {"cach": self.cach, "dat": self.dat,
                "chi_tiet": khong_suy_nghi(self.chi_tiet, toi_da=1200),
                "tham_so": dict(self.tham_so), "tat_dinh": self.tat_dinh,
                "giay": round(self.giay, 2), "ts": self.ts}


class MoiGioiKiem:
    """Chạy phép kiểm TẤT ĐỊNH trong một kho. Không nhận chuỗi lệnh.

    `repo` là gốc duy nhất mọi đường dẫn được phép chạm. `_trong_kho` so theo
    ĐOẠN sau `resolve()`, nên `../../etc/passwd` và một symlink trỏ ra ngoài
    đều bị chặn — cùng lý do `attachments.py` kiểm containment sau
    `resolve()` chứ không trước.
    """

    def __init__(self, repo: str, *, python: str = "",
                 han_giay: float = HAN_GIAY) -> None:
        self.repo = Path(repo).resolve()
        self.python = python or sys.executable
        self.han_giay = float(han_giay)

    # ------------------------------------------------------------- ho tro --

    def _trong_kho(self, duong: str) -> Path:
        p = (self.repo / str(duong or "")).resolve()
        a = [x.lower() for x in p.parts]
        b = [x.lower() for x in self.repo.parts]
        if a[:len(b)] != b:
            raise KiemLoi(f"đường dẫn ra ngoài kho: {duong!r}")
        if la_tep_bi_mat(p.as_posix()):
            raise KiemLoi(
                f"{duong!r} có hình dạng TỆP BÍ MẬT — phép kiểm không bao giờ "
                f"đọc nội dung loại tệp này (danh sách CẤM thắng danh sách "
                f"cho phép)")
        return p

    def _chay(self, argv: Sequence[str]) -> Tuple[int, str]:
        """Chạy một `argv` ĐÃ DỰNG SẴN. Mọi điểm gọi đi qua `_boc_an_cua_so`."""
        try:
            r = _boc_an_cua_so(argv, cwd=str(self.repo),
                               han_giay=self.han_giay)
        except subprocess.TimeoutExpired:
            return 124, f"quá hạn {self.han_giay:.0f}s"
        except OSError as exc:
            return 127, f"không chạy được: {exc}"
        out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        return int(r.returncode), out[-4000:]

    # -------------------------------------------------------- phep kiem ----

    def tep_ton_tai(self, *, duong: str = "", bam: str = "",
                    **_) -> KetQuaKiem:
        p = self._trong_kho(duong)
        co = p.exists()
        ct = f"{duong}: {'CÓ' if co else 'KHÔNG CÓ'}"
        if co and bam:
            thuc = hashlib.sha256(p.read_bytes()).hexdigest()
            co = thuc.lower().startswith(str(bam).lower())
            ct = f"{duong}: sha256={thuc[:16]}… (mong {str(bam)[:16]}…)"
        return KetQuaKiem("TEP_TON_TAI", co, ct, {"duong": duong, "bam": bam})

    def chuoi_trong_tep(self, *, duong: str = "", chuoi: str = "",
                        it_nhat: int = 1, **_) -> KetQuaKiem:
        p = self._trong_kho(duong)
        if not str(chuoi or ""):
            raise KiemLoi("CHUOI_TRONG_TEP: thiếu `chuoi`")
        if not p.exists():
            return KetQuaKiem("CHUOI_TRONG_TEP", False, f"{duong}: không có tệp",
                              {"duong": duong})
        n = p.read_text(encoding="utf-8", errors="replace").count(str(chuoi))
        return KetQuaKiem("CHUOI_TRONG_TEP", n >= int(it_nhat or 1),
                          f"{duong}: gặp {n} lần (cần ≥ {it_nhat})",
                          {"duong": duong, "it_nhat": it_nhat})

    def git_co_thay_doi(self, *, so_voi: str = "", **_) -> KetQuaKiem:
        """Cây làm việc CÓ đổi so với `so_voi` (mặc định: HEAD + chưa theo dõi).

        `so_voi` đi vào `argv` như MỘT phần tử, không nối chuỗi, nên nó không
        thể mang thêm cờ. Và nó phải trông như một tham chiếu git.
        """
        moc = str(so_voi or "HEAD").strip()
        if not _re.match(r"^[A-Za-z0-9_./@^~-]{1,80}$", moc):
            raise KiemLoi(f"GIT_CO_THAY_DOI: tham chiếu lạ {so_voi!r}")
        ma, out = self._chay(["git", "status", "--porcelain"])
        if ma != 0:
            return KetQuaKiem("GIT_CO_THAY_DOI", False, f"git lỗi: {out[:300]}",
                              {"so_voi": moc})
        ban = [x for x in out.splitlines() if x.strip()]
        if ban:
            return KetQuaKiem("GIT_CO_THAY_DOI", True,
                              f"{len(ban)} mục chưa commit", {"so_voi": moc})
        ma, out = self._chay(["git", "diff", "--name-only", moc])
        d = [x for x in out.splitlines() if x.strip()] if ma == 0 else []
        return KetQuaKiem("GIT_CO_THAY_DOI", bool(d),
                          (f"{len(d)} tệp đổi so với {moc}" if d
                           else f"KHÔNG thay đổi nào so với {moc}"),
                          {"so_voi": moc})

    def git_trong_pham_vi(self, *, pham_vi: Sequence[str] = (),
                          so_voi: str = "HEAD", **_) -> KetQuaKiem:
        """Mọi tệp đổi có nằm trong `pham_vi` không. Rỗng = không đổi gì cũng đạt."""
        pv = [str(x).replace("\\", "/").strip("/").lower()
              for x in (pham_vi or ()) if str(x or "").strip()]
        ma, out = self._chay(["git", "status", "--porcelain"])
        tep = [x[3:].strip().replace("\\", "/").lower()
               for x in out.splitlines() if len(x) > 3] if ma == 0 else []
        ngoai = [t for t in tep
                 if pv and not any(t == p or t.startswith(p + "/") for p in pv)]
        del so_voi
        return KetQuaKiem("GIT_TRONG_PHAM_VI", not ngoai,
                          ("mọi thay đổi trong phạm vi" if not ngoai
                           else f"{len(ngoai)} tệp NGOÀI phạm vi: "
                                + ", ".join(ngoai[:8])),
                          {"pham_vi": list(pv)})

    def unittest_module(self, *, module: str = "", **_) -> KetQuaKiem:
        """`python -m unittest <module>` — `module` phải là một tên module.

        Đây là chỗ dễ biến thành một cửa chạy lệnh tuỳ ý nhất trong cả v0.9,
        nên `_TEN_MODULE` chặn mọi thứ không phải `a.b.c`: không khoảng
        trắng, không `;`, không `-`, không đường dẫn.
        """
        m = str(module or "").strip()
        if not _TEN_MODULE.match(m):
            raise KiemLoi(f"UNITTEST_MODULE: {module!r} không phải tên module")
        ma, out = self._chay([self.python, "-m", "unittest", m, "-v"])
        return KetQuaKiem("UNITTEST_MODULE", ma == 0,
                          (out.strip().splitlines() or ["(không có đầu ra)"])[-1],
                          {"module": m})

    def bien_dich_python(self, *, duong: Sequence[str] = (), **_) -> KetQuaKiem:
        dd = [str(self._trong_kho(x)) for x in (duong or ["scripts"])]
        ma, out = self._chay([self.python, "-m", "compileall", "-q"] + dd)
        return KetQuaKiem("BIEN_DICH_PYTHON", ma == 0,
                          out[-600:] or "biên dịch sạch",
                          {"duong": [str(x) for x in (duong or ["scripts"])]})

    # ------------------------------------------------------------ dieu phoi --

    #: `CachKiem` -> phương thức. Danh sách ĐÓNG, khớp enum. Một giá trị enum
    #: không có ở đây sẽ ném ở `chay()` thay vì lặng lẽ "đạt".
    BO_CHAY: Dict[CachKiem, str] = {
        CachKiem.TEP_TON_TAI: "tep_ton_tai",
        CachKiem.CHUOI_TRONG_TEP: "chuoi_trong_tep",
        CachKiem.GIT_CO_THAY_DOI: "git_co_thay_doi",
        CachKiem.GIT_TRONG_PHAM_VI: "git_trong_pham_vi",
        CachKiem.UNITTEST_MODULE: "unittest_module",
        CachKiem.BIEN_DICH_PYTHON: "bien_dich_python",
    }

    def chay(self, cach: CachKiem, tham_so: Optional[Dict] = None, *,
             ket_qua: Optional[HopDongKetQua] = None) -> KetQuaKiem:
        """Chạy MỘT phép kiểm. Ném `KiemLoi` khi tham số sai.

        `TEST_DA_CHAY` và `CO_ARTIFACT` đọc từ hợp đồng kết quả chứ không
        chạm đĩa — chúng là phép kiểm trên LỜI KHAI đã được đối soát, và
        tách chúng ra khỏi `BO_CHAY` làm rõ điều đó.
        """
        t0 = time.time()
        tp = dict(tham_so or {})
        if cach is CachKiem.REVIEWER:
            raise KiemLoi("REVIEWER không phải phép kiểm tất định — "
                          "xem `kiem_dinh_ngu_nghia`")
        if cach is CachKiem.TEST_DA_CHAY:
            k = _test_da_chay(ket_qua, tp)
        elif cach is CachKiem.CO_ARTIFACT:
            k = _co_artifact(ket_qua, tp)
        else:
            ten = self.BO_CHAY.get(cach)
            if ten is None:
                raise KiemLoi(f"không có bộ chạy cho {cach.value} — "
                              f"thêm cách kiểm phải thêm ở CẢ HAI chỗ")
            k = getattr(self, ten)(**tp)
        k.giay = time.time() - t0
        return k


def _test_da_chay(kq: Optional[HopDongKetQua], tp: Dict) -> KetQuaKiem:
    it_nhat = int(tp.get("it_nhat") or 1)
    if kq is None:
        return KetQuaKiem("TEST_DA_CHAY", False, "không có hợp đồng kết quả", tp)
    t = kq.tests_run or {}
    try:
        qua = int(t.get("passed") or 0)
        hong = int(t.get("failed") or 0)
    except (TypeError, ValueError):
        return KetQuaKiem("TEST_DA_CHAY", False,
                          f"`tests` không đọc được: {t!r}", tp)
    dat = hong == 0 and qua >= it_nhat
    return KetQuaKiem("TEST_DA_CHAY", dat,
                      f"{qua} đạt / {hong} hỏng (cần ≥ {it_nhat} đạt, 0 hỏng)",
                      tp)


def _co_artifact(kq: Optional[HopDongKetQua], tp: Dict) -> KetQuaKiem:
    ten = [str(x) for x in (tp.get("ten") or ()) if str(x or "").strip()]
    if kq is None:
        return KetQuaKiem("CO_ARTIFACT", False, "không có hợp đồng kết quả", tp)
    co = [x.lower() for x in list(kq.artifacts) + list(kq.files_changed)]
    thieu = [a for a in ten
             if not any(a.lower() in c or c.endswith(a.lower()) for c in co)]
    return KetQuaKiem("CO_ARTIFACT", not thieu,
                      ("đủ artifact" if not thieu
                       else "thiếu: " + ", ".join(thieu[:8])), tp)


# ------------------------------------------------------------ kiem mot buoc --

def kiem_dinh_buoc(buoc: BuocKeHoach, kq: Optional[HopDongKetQua], *,
                   moi_gioi: Optional[MoiGioiKiem] = None
                   ) -> Tuple[TrangThaiXacMinh, List[KetQuaKiem]]:
    """Phán quyết cho MỘT bước. Bằng chứng trước, phép kiểm sau.

    Thứ tự có nghĩa: một bước không đủ bằng chứng thì chạy phép kiểm cũng vô
    ích — ta sẽ kiểm một thay đổi không tồn tại và có thể "đạt" nhờ trạng
    thái sẵn có của cây. Đây đúng là cách một DONE giả lọt qua một tầng kiểm
    định trông có vẻ nghiêm.
    """
    ds: List[KetQuaKiem] = []
    if kq is None:
        return TrangThaiXacMinh.THIEU_BANG_CHUNG, ds
    if not kq.ok:
        return TrangThaiXacMinh.KHONG_DAT, ds
    pq = du_bang_chung(kq, buoc)
    if pq.muc is MucBangChung.MAU_THUAN:
        ds.append(KetQuaKiem("BANG_CHUNG", False, pq.ly_do))
        return TrangThaiXacMinh.KHONG_DAT, ds
    if pq.muc is MucBangChung.CHUA_DU:
        ds.append(KetQuaKiem("BANG_CHUNG", False, pq.ly_do,
                             {"thieu": list(pq.thieu)}))
        return TrangThaiXacMinh.THIEU_BANG_CHUNG, ds
    ds.append(KetQuaKiem("BANG_CHUNG", True, pq.ly_do))

    can = [(c, p) for c, p in buoc.cach_kiem if c.tat_dinh]
    if can and moi_gioi is None:
        ds.append(KetQuaKiem(
            "MOI_GIOI", False,
            "bước khai có phép kiểm tất định nhưng không có môi giới để chạy",
            tat_dinh=True))
        return TrangThaiXacMinh.THIEU_BANG_CHUNG, ds
    for c, p in can:
        try:
            ds.append(moi_gioi.chay(c, p, ket_qua=kq))    # type: ignore[union-attr]
        except KiemLoi as exc:
            ds.append(KetQuaKiem(c.value, False, f"THAM SỐ SAI: {exc}", p))
    if any(not k.dat for k in ds):
        return TrangThaiXacMinh.KHONG_DAT, ds
    # BUOC GHI PHAI CO IT NHAT MOT PHEP KIEM TAT DINH.
    #
    # Khong co dong nay thi mot ke hoach quen khai `cach_kiem` se cho moi buoc
    # ghi di thang toi DAT chi vi worker noi `ok` va co tep doi — tuc la ta
    # quay lai dung cho V0.8 dung.
    if buoc.ghi and not can:
        ds.append(KetQuaKiem(
            "KIEM_TAT_DINH", False,
            "bước GHI không khai phép kiểm tất định nào — chưa xác minh được",
            tat_dinh=True))
        return TrangThaiXacMinh.THIEU_BANG_CHUNG, ds
    return TrangThaiXacMinh.DAT, ds


# ------------------------------------------------------- kiem ca lan chay --

@dataclass
class ChamTieuChi:
    """Một tiêu chí nghiệm thu đã được chấm."""

    mo_ta: str
    trang_thai: TrangThaiXacMinh
    bat_buoc: bool = True
    kiem: Tuple[KetQuaKiem, ...] = ()
    ghi_chu: str = ""

    def to_dict(self) -> Dict:
        return {"mo_ta": self.mo_ta, "trang_thai": self.trang_thai.value,
                "bat_buoc": self.bat_buoc,
                "kiem": [k.to_dict() for k in self.kiem],
                "ghi_chu": self.ghi_chu}


@dataclass
class BaoCaoKiemDinh:
    """Phán quyết cho CẢ lần thực thi — §8."""

    execution_id: str
    trang_thai: TrangThaiXacMinh = TrangThaiXacMinh.CHUA_KIEM
    buoc_dat: Tuple[str, ...] = ()
    buoc_hong: Tuple[str, ...] = ()
    buoc_thieu_bang_chung: Tuple[str, ...] = ()
    tieu_chi: Tuple[ChamTieuChi, ...] = ()
    doc_lap: Optional[bool] = None
    ly_do: str = ""
    giay: float = 0.0

    @property
    def dat(self) -> bool:
        return self.trang_thai.dat

    def to_dict(self) -> Dict:
        return {"execution_id": self.execution_id,
                "trang_thai": self.trang_thai.value, "dat": self.dat,
                "buoc_dat": list(self.buoc_dat),
                "buoc_hong": list(self.buoc_hong),
                "buoc_thieu_bang_chung": list(self.buoc_thieu_bang_chung),
                "tieu_chi": [t.to_dict() for t in self.tieu_chi],
                "doc_lap": self.doc_lap, "ly_do": self.ly_do,
                "giay": round(self.giay, 2)}

    def render(self) -> str:
        d = [f"KIỂM ĐỊNH: {self.trang_thai.value} — {self.ly_do}"]
        if self.buoc_dat:
            d.append(f"  bước đạt: {', '.join(self.buoc_dat)}")
        if self.buoc_thieu_bang_chung:
            d.append("  bước THIẾU BẰNG CHỨNG: "
                     + ", ".join(self.buoc_thieu_bang_chung))
        if self.buoc_hong:
            d.append(f"  bước HỎNG: {', '.join(self.buoc_hong)}")
        for t in self.tieu_chi:
            d.append(f"  [{t.trang_thai.value}] {t.mo_ta}"
                     + ("" if t.bat_buoc else "  (không bắt buộc)"))
            for k in t.kiem:
                d.append(f"      {'✓' if k.dat else '✗'} {k.cach}: {k.chi_tiet}")
        if self.doc_lap is False:
            d.append("  (!) phản biện KHÔNG độc lập về họ model — SUY GIẢM")
        return "\n".join(d)


def kiem_dinh_thuc_thi(y: YDinhThucThi, kh: KeHoachThucThi,
                       ket_qua_buoc: Dict[str, Optional[HopDongKetQua]], *,
                       moi_gioi: Optional[MoiGioiKiem] = None,
                       phan_bien: Optional[Dict] = None) -> BaoCaoKiemDinh:
    """Chấm CẢ lần thực thi theo MỤC TIÊU GỐC — §8.

    `phan_bien` (tuỳ chọn) là kết quả một lượt Reviewer đã chạy ở tầng trên:
    `{"phan_xu": "ACCEPT|REVISE|REJECT", "doc_lap": bool, "ly_do": str}`.
    Tầng này KHÔNG tự gọi model — nó nhận phán xử rồi hợp nhất, cùng lý do
    `hoi_dong.py` tách khỏi `engine.py`: một tầng chấm điểm mà tự gọi mạng
    thì không kiểm được bằng bài kiểm tất định.
    """
    t0 = time.time()
    dat: List[str] = []
    hong: List[str] = []
    thieu: List[str] = []
    for b in kh.buoc:
        tt, _ = kiem_dinh_buoc(b, ket_qua_buoc.get(b.buoc_id),
                               moi_gioi=moi_gioi)
        if tt is TrangThaiXacMinh.DAT:
            dat.append(b.buoc_id)
        elif tt is TrangThaiXacMinh.THIEU_BANG_CHUNG:
            thieu.append(b.buoc_id)
        else:
            hong.append(b.buoc_id)

    kq_bat_ky = next((k for k in ket_qua_buoc.values() if k is not None), None)
    cham: List[ChamTieuChi] = []
    for tc in kh.nghiem_thu:
        cham.append(_cham_tieu_chi(tc, moi_gioi, kq_bat_ky, ket_qua_buoc))

    # TIEU CHI CUA NGUOI DUNG MA KE HOACH KHONG BUOC VAO PHEP KIEM NAO.
    #
    # Day la cho §8 co rang thuc su: `y.tieu_chi_dat` den TU CAU NGUOI DUNG
    # GO. Neu bo lap ke hoach khong dung mot `TieuChiNghiemThu` nao cho no
    # thi no KHONG duoc bien mat — no hien ra la THIEU_BANG_CHUNG.
    da_phu = {t.mo_ta.strip().lower() for t in kh.nghiem_thu}
    for mo in y.tieu_chi_dat:
        if mo.strip().lower() in da_phu:
            continue
        cham.append(ChamTieuChi(
            mo_ta=mo, trang_thai=TrangThaiXacMinh.THIEU_BANG_CHUNG,
            ghi_chu=("người dùng nêu tiêu chí này nhưng kế hoạch không buộc "
                     "nó vào phép kiểm nào — KHÔNG tự coi là đạt")))

    tt, ly = _tong_hop(dat, hong, thieu, cham, kh, phan_bien)
    return BaoCaoKiemDinh(
        execution_id=y.execution_id, trang_thai=tt, buoc_dat=tuple(dat),
        buoc_hong=tuple(hong), buoc_thieu_bang_chung=tuple(thieu),
        tieu_chi=tuple(cham),
        doc_lap=(None if not phan_bien else bool(phan_bien.get("doc_lap"))),
        ly_do=ly, giay=time.time() - t0)


def _cham_tieu_chi(tc: TieuChiNghiemThu, moi_gioi: Optional[MoiGioiKiem],
                   kq: Optional[HopDongKetQua],
                   ket_qua_buoc: Dict[str, Optional[HopDongKetQua]]
                   ) -> ChamTieuChi:
    tat = [(c, p) for c, p in tc.cach_kiem if c.tat_dinh]
    if not tat:
        return ChamTieuChi(
            tc.mo_ta, TrangThaiXacMinh.THIEU_BANG_CHUNG, tc.bat_buoc,
            ghi_chu=("không có phép kiểm tất định nào buộc vào tiêu chí này"
                     + (" — chờ phán xử Reviewer"
                        if any(c is CachKiem.REVIEWER for c, _ in tc.cach_kiem)
                        else "")))
    if moi_gioi is None:
        return ChamTieuChi(tc.mo_ta, TrangThaiXacMinh.THIEU_BANG_CHUNG,
                           tc.bat_buoc,
                           ghi_chu="không có môi giới kiểm để chạy")
    ds: List[KetQuaKiem] = []
    for c, p in tat:
        # Mot phep kiem doc LOI KHAI (`TEST_DA_CHAY`, `CO_ARTIFACT`) o muc
        # NGHIEM THU phai nhin CA lan chay, khong chi mot buoc: nen ta gop
        # loi khai cua moi buoc lai truoc khi cham.
        nguon = kq if c not in (CachKiem.TEST_DA_CHAY, CachKiem.CO_ARTIFACT) \
            else _gop_ket_qua(ket_qua_buoc)
        try:
            ds.append(moi_gioi.chay(c, p, ket_qua=nguon))
        except KiemLoi as exc:
            ds.append(KetQuaKiem(c.value, False, f"THAM SỐ SAI: {exc}", p))
    return ChamTieuChi(
        tc.mo_ta,
        TrangThaiXacMinh.DAT if all(k.dat for k in ds)
        else TrangThaiXacMinh.KHONG_DAT,
        tc.bat_buoc, tuple(ds))


def _gop_ket_qua(ket_qua_buoc: Dict[str, Optional[HopDongKetQua]]
                 ) -> Optional[HopDongKetQua]:
    """Gộp lời khai của MỌI bước thành một hợp đồng để chấm ở mức nghiệm thu."""
    co = [k for k in ket_qua_buoc.values() if k is not None]
    if not co:
        return None
    art: List[str] = []
    tep: List[str] = []
    qua = hong = 0
    ran = False
    for k in co:
        art += list(k.artifacts)
        tep += list(k.files_changed)
        t = k.tests_run or {}
        try:
            qua += int(t.get("passed") or 0)
            hong += int(t.get("failed") or 0)
        except (TypeError, ValueError):
            pass
        ran = ran or bool(t.get("ran"))
    return HopDongKetQua(
        task_id="(gộp)", status="ok", summary="(gộp lời khai mọi bước)",
        artifacts=tuple(art), files_changed=tuple(tep),
        tests_run={"ran": ran, "passed": qua, "failed": hong})


def _tong_hop(dat: Sequence[str], hong: Sequence[str], thieu: Sequence[str],
              cham: Sequence[ChamTieuChi], kh: KeHoachThucThi,
              phan_bien: Optional[Dict]) -> Tuple[TrangThaiXacMinh, str]:
    if hong:
        return (TrangThaiXacMinh.KHONG_DAT,
                f"{len(hong)} bước hỏng: {', '.join(hong[:6])}")
    if thieu:
        return (TrangThaiXacMinh.THIEU_BANG_CHUNG,
                f"{len(thieu)} bước chưa chứng minh được: "
                f"{', '.join(thieu[:6])}")
    bb = [t for t in cham if t.bat_buoc]
    xau = [t for t in bb if t.trang_thai is TrangThaiXacMinh.KHONG_DAT]
    if xau:
        return (TrangThaiXacMinh.KHONG_DAT,
                f"{len(xau)}/{len(bb)} tiêu chí nghiệm thu BẮT BUỘC không đạt: "
                + "; ".join(t.mo_ta[:60] for t in xau[:3]))
    mo = [t for t in bb if t.trang_thai is TrangThaiXacMinh.THIEU_BANG_CHUNG]
    if mo:
        return (TrangThaiXacMinh.THIEU_BANG_CHUNG,
                f"{len(mo)}/{len(bb)} tiêu chí nghiệm thu BẮT BUỘC chưa có "
                f"bằng chứng: " + "; ".join(t.mo_ta[:60] for t in mo[:3]))
    if not bb and kh.co_buoc_ghi:
        # Mot ke hoach CO buoc ghi ma KHONG co tieu chi nghiem thu nao la mot
        # ke hoach khong noi duoc "the nao la xong". Khong chan no, nhung
        # khong cho no len DAT.
        return (TrangThaiXacMinh.SUY_GIAM,
                "mọi bước đạt, nhưng kế hoạch KHÔNG khai tiêu chí nghiệm thu "
                "nào cho một lần thực thi có ghi — không chấm được mục tiêu gốc")
    if phan_bien:
        px = str(phan_bien.get("phan_xu") or "").strip().upper()
        if px == "REJECT":
            return (TrangThaiXacMinh.KHONG_DAT,
                    "Reviewer REJECT: "
                    + str(phan_bien.get("ly_do") or "")[:200])
        if px == "REVISE":
            return (TrangThaiXacMinh.THIEU_BANG_CHUNG,
                    "Reviewer REVISE: "
                    + str(phan_bien.get("ly_do") or "")[:200])
        if not phan_bien.get("doc_lap"):
            return (TrangThaiXacMinh.SUY_GIAM,
                    "mọi phép kiểm đạt, nhưng phản biện KHÔNG độc lập về họ "
                    "model — không giả vờ đó là bằng chứng")
    return (TrangThaiXacMinh.DAT,
            f"{len(dat)} bước đạt, {len(bb)} tiêu chí nghiệm thu bắt buộc đạt")


def can_phan_bien(kh: KeHoachThucThi, y: YDinhThucThi) -> bool:
    """Có cần một lượt Reviewer NGỮ NGHĨA không? §7: chỉ khi thật sự cần.

    Cần khi: kế hoạch khai tường minh `CachKiem.REVIEWER` ở đâu đó, HOẶC lần
    thực thi có rủi ro CAO / chạm production. Ngoài hai trường hợp đó, phép
    kiểm tất định đã đủ và một lượt model chỉ tốn hạn mức.
    """
    if any(c is CachKiem.REVIEWER
           for b in kh.buoc for c, _ in b.cach_kiem):
        return True
    if any(c is CachKiem.REVIEWER
           for t in kh.nghiem_thu for c, _ in t.cach_kiem):
        return True
    return y.tac_dong_production or y.rui_ro.rank >= 2
