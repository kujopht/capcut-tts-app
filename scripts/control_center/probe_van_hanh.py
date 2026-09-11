"""MÔI GIỚI PROBE VẬN HÀNH — phép ĐỌC production có KIỂU, không có shell.

VÌ SAO GÓI NÀY TỒN TẠI — một thất bại thật, đo được từ sổ:

    2026-09-11 06:25:57  người dùng: "Kiểm tra READ-ONLY vì sao từ hôm qua
                         tới giờ tôi không thấy production artifact mới
                         được mirror lên Google Drive."
    06:26:37             bộ phân rã (`planner=rule`) dựng MỘT việc
                         `fanfic.t2efd-1`, `type=analysis`,
                         `requirements.shell=false`,
                         tài nguyên `READ:FILESYSTEM:.`
    06:30:37             AG03/claude-sonnet-4-6 -> FAILED,
                         `failure_reason=tool_permission_denied`

Chuỗi nhân quả, không phải phỏng đoán: câu hỏi là câu hỏi VẬN HÀNH
(systemd, rclone, Drive, R2) nhưng Router lại xếp nó thành một việc PHÂN
TÍCH KHO, và danh sách lệnh của một việc kho chỉ có đúng hai dòng
`cc_agent_tool.py changes|compile`. Không lệnh nào trong hai dòng đó chạm
được tới production, nên worker gọi công cụ `command` chung — và `agy
--print` TỰ CHỐI `command` vì headless không hiện được hộp thoại hỏi
quyền. Worker kết thúc lượt mà không in một chữ nào.

Cách sửa KHÔNG phải là nới quyền. Đây đã là lần thứ TƯ cùng một bài học
(`command`, `read_file`, `read_url`, nay lại `command`): **Router làm phép
đọc an toàn rồi đưa BẰNG CHỨNG CÓ CẤU TRÚC cho worker.** Xem
`nguon_git.git_nhat_ky_doc` và `web_reader.doc_web` — cùng một khuôn.

BỐN LUẬT CỦA GÓI NÀY:

1. **Không có lối thoát ra shell.** API công khai nhận TÊN THAO TÁC + tham
   số đã kiểm, không bao giờ nhận một chuỗi lệnh. `chay("rm -rf /")` không
   phải là một lời gọi hợp lệ — nó là một `OpKhongHopLe`.
2. **Tham số bị kiểm theo danh sách cho phép LẤY TỪ CẤU HÌNH DỰ ÁN**, chứ
   không phải từ câu chữ người dùng: unit phải là unit đã khai, đường dẫn
   phải nằm dưới gốc đã khai, thuộc tính systemd phải nằm trong bảng.
3. **Chỉ ĐỌC, và có lưới thứ hai.** Ngoài việc mọi lệnh đều do mã trong
   tệp này dựng, `_kiem_chi_doc()` còn quét chuỗi cuối cùng và từ chối mọi
   động từ đột biến. Một mẫu lệnh viết sai vẫn bị chặn.
4. **Không leo thang quyền.** Không `sudo`. Trên farmer thật, `ubuntu`
   CÓ sudo không mật khẩu — và gói này vẫn không dùng. Một lớp QUAN SÁT
   không được phép nâng quyền trên máy production; chỗ sửa đúng nằm ở
   phía máy chủ (cho tệp readable theo nhóm), và điều đó được BÁO CÁO chứ
   không tự làm.

Kết quả mang NGUỒN GỐC ĐẦY ĐỦ (`KetQuaProbe`): nguồn, thao tác, đích, mốc
đo, tuổi, trạng thái sáu bậc, bằng chứng đã lọc bí mật, và lý do khi không
đo được. `UNAVAILABLE` không bao giờ mang giá trị — cùng luật với
`observability/model.py`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.control_center.memory.bi_mat import loc as _loc_bi_mat
from scripts.control_center.observability.model import QuanSat, TrangThai
from scripts.router_v3.tien_trinh import an_cua_so


def _loc(van: str) -> str:
    """Lọc bí mật MẠNH cho mọi thứ rời khỏi máy production.

    Dùng bộ mẫu của lớp ký ức (`memory.bi_mat`) chứ KHÔNG dùng
    `packet.redact`: bộ của `packet` KHÔNG có khoá AWS `AKIA…`/`ASIA…` —
    đúng hình dạng dễ gặp nhất trong log của một máy EC2. Bài kiểm
    `TestLocBiMat` bắt được khoảng trống này.
    """
    return _loc_bi_mat(str(van or ""))[0]


class ProbeLoi(Exception):
    """Gốc của mọi lỗi gói này."""


class OpKhongHopLe(ProbeLoi):
    """Tên thao tác không có trong bảng đăng ký."""


class ThamSoKhongHopLe(ProbeLoi):
    """Tham số trượt kiểm — KHÔNG bao giờ được đi tiếp tới lớp thực thi."""


class LenhBiCam(ProbeLoi):
    """Lưới thứ hai bắt được một lệnh mang động từ đột biến."""


# ------------------------------------------------------- an toàn chỉ đọc ----

#: Động từ ĐỘT BIẾN. Lưới thứ hai: kể cả khi một mẫu lệnh trong tệp này bị
#: viết sai, chuỗi cuối cùng vẫn phải đi qua đây. Khớp theo TỪ, không theo
#: chuỗi con — `restart` phải chặn `systemctl restart` mà không chặn đường
#: dẫn `/var/log/restarted.log`.
TU_CAM: Tuple[str, ...] = (
    # systemd / tiến trình
    "start", "stop", "restart", "reload", "enable", "disable", "mask",
    "unmask", "kill", "pkill", "killall", "reboot", "shutdown", "halt",
    "poweroff", "daemon-reload",
    # hệ tệp
    "rm", "rmdir", "unlink", "mv", "install", "dd", "mkfs", "truncate",
    "shred", "chmod", "chown", "chgrp", "ln", "mkdir", "touch", "tee",
    # gói / quyền
    "apt", "apt-get", "yum", "dnf", "snap", "pip", "pip3", "npm", "sudo",
    "su", "doas", "usermod", "useradd", "passwd", "visudo",
    # rclone ghi
    "copy", "copyto", "move", "moveto", "sync", "delete", "deletefile",
    "purge", "rcat", "settier", "cleanup", "bisync",
    # git ghi
    "push", "commit", "reset", "checkout", "clean",
)

#: Ký tự cho phép NỐI lệnh hoặc chuyển hướng — cấm tuyệt đối trong THAM SỐ.
#: (Bản thân mẫu lệnh có thể dùng `|`; tham số thì không được có gì cả.)
_METACHAR = re.compile(r"[;&`$><\n\r\\\"'*?\[\]{}()!#~]")

#: Bộ ký tự an toàn cho một tham số đơn (unit, đường dẫn, remote…).
_THAM_SO_SACH = re.compile(r"^[A-Za-z0-9_.:/@=,+-]{1,240}$")


def _kiem_chi_doc(lenh: str) -> str:
    """Lưới thứ HAI. Trả lại lệnh, hoặc ném `LenhBiCam`.

    Không thay thế phép kiểm tham số — nó là lớp phòng khi một mẫu lệnh
    mới được thêm vào mà quên mất mình đang viết một động từ ghi.
    """
    tho = " " + re.sub(r"[|]", " ", lenh or "") + " "
    for tu in TU_CAM:
        if re.search(rf"(?<![\w.-]){re.escape(tu)}(?![\w.-])", tho):
            raise LenhBiCam(
                f"lệnh chứa động từ ĐỘT BIẾN {tu!r} — lớp probe chỉ được ĐỌC")
    if re.search(r"[;&`]|\$\(|\|\||>>?", lenh or ""):
        raise LenhBiCam("lệnh chứa ký tự nối/chuyển hướng — không cho phép")
    return lenh


# ------------------------------------------------------------ tham số ------

#: Thuộc tính `systemctl show` được phép hỏi. Đây đều là siêu dữ liệu vận
#: hành; KHÔNG có `Environment*` (nó in thẳng biến môi trường, tức là bí mật).
THUOC_TINH_CHO_PHEP: Tuple[str, ...] = (
    "MainPID", "NRestarts", "ActiveState", "SubState", "LoadState",
    "UnitFileState", "ExecMainStartTimestamp", "ExecMainExitTimestamp",
    "ActiveEnterTimestamp", "InactiveEnterTimestamp", "Result",
    "StatusText", "MemoryCurrent", "CPUUsageNSec", "TasksCurrent",
    "Restart", "RestartUSec",
)

#: Bộ lọc nhật ký CÓ TÊN. Người dùng không bao giờ đưa regex vào đây.
LOC_JOURNAL: Dict[str, str] = {
    "tat_ca": "",
    "loi": "error|fail|exception|traceback|critical",
    "archive": "archive|rclone|drive|mirror|upload",
    "vong": "round|harvest|candidate|lane|batch",
}

#: Đơn vị thời gian cho `--since`. Chuỗi cuối do MÃ dựng từ số + đơn vị đã
#: kiểm, nên câu chữ người dùng không bao giờ chạm tới dòng lệnh.
DON_VI_THOI_GIAN: Tuple[str, ...] = ("minutes", "hours", "days")


def _kiem_chuoi(gt: Any, ten: str) -> str:
    s = str(gt or "").strip()
    if not s:
        raise ThamSoKhongHopLe(f"{ten}: rỗng")
    if _METACHAR.search(s) or " " in s:
        raise ThamSoKhongHopLe(
            f"{ten}: chứa ký tự không được phép ({s[:40]!r})")
    if not _THAM_SO_SACH.match(s):
        raise ThamSoKhongHopLe(f"{ten}: không khớp bộ ký tự an toàn")
    return s


def _kiem_so(gt: Any, ten: str, *, nho_nhat: int, lon_nhat: int) -> int:
    try:
        n = int(gt)
    except (TypeError, ValueError):
        raise ThamSoKhongHopLe(f"{ten}: phải là số nguyên") from None
    if not (nho_nhat <= n <= lon_nhat):
        raise ThamSoKhongHopLe(
            f"{ten}={n} ngoài khoảng [{nho_nhat}, {lon_nhat}]")
    return n


def _chuan_hoa_duong(d: str) -> str:
    """Chuẩn hoá đường dẫn POSIX. Từ chối `..` và đường tương đối."""
    s = _kiem_chuoi(d, "duong")
    if not s.startswith("/"):
        raise ThamSoKhongHopLe(f"duong: phải là đường tuyệt đối ({s!r})")
    doan = [x for x in s.split("/") if x not in ("", ".")]
    if any(x == ".." for x in doan):
        raise ThamSoKhongHopLe("duong: không được chứa `..`")
    return "/" + "/".join(doan)


def _duoi_goc(duong: str, goc: str) -> bool:
    """`duong` có nằm trong `goc` không — so theo ĐOẠN, không theo tiền tố.

    So tiền tố trần thì `/var/lib/fanfic-farmer-evil` lọt qua `/var/lib/
    fanfic-farmer`; đó là một lỗi thật hay gặp nên ở đây so từng đoạn.
    """
    a = [x for x in duong.split("/") if x]
    b = [x for x in goc.split("/") if x]
    return a[:len(b)] == b


# ------------------------------------------------------------ kết quả ------

@dataclass
class KetQuaProbe:
    """MỘT phép đo vận hành, kèm nguồn gốc đầy đủ (Phần 8 của đặc tả)."""

    op: str
    dich: str
    trang_thai: TrangThai
    gia_tri: Any = None
    nguon: str = ""
    do_luc: float = field(default_factory=time.time)
    han_tuoi: float = 120.0
    ly_do: str = ""
    bang_chung: str = ""
    ma_thoat: Optional[int] = None

    def __post_init__(self) -> None:
        # Cung luat voi observability/model.py: "khong biet" ma van mang
        # mot gia tri chinh la BIA SO.
        if self.trang_thai in (TrangThai.UNKNOWN, TrangThai.UNAVAILABLE):
            if not self.ly_do:
                raise ValueError(f"{self.op}: {self.trang_thai.value} phải có `ly_do`")
            if self.gia_tri is not None:
                raise ValueError(
                    f"{self.op}: {self.trang_thai.value} không được mang giá trị")

    @property
    def tuoi(self) -> float:
        return max(0.0, time.time() - self.do_luc)

    @property
    def qua_han(self) -> bool:
        return bool(self.han_tuoi) and self.tuoi > self.han_tuoi

    def hieu_luc(self) -> TrangThai:
        if self.qua_han and self.trang_thai.do_duoc:
            return TrangThai.STALE
        return self.trang_thai

    def to_dict(self) -> Dict:
        return {"op": self.op, "dich": self.dich,
                "trang_thai": self.hieu_luc().value,
                "trang_thai_do": self.trang_thai.value,
                "gia_tri": self.gia_tri, "nguon": self.nguon,
                "do_luc": self.do_luc, "tuoi_giay": round(self.tuoi, 1),
                "qua_han": self.qua_han, "ly_do": self.ly_do,
                "bang_chung": self.bang_chung, "ma_thoat": self.ma_thoat}

    def to_quan_sat(self) -> QuanSat:
        """Đổi sang `QuanSat` để dùng chung đường hiển thị của V0.5."""
        return QuanSat(khoa=self.op.replace(".", "_"),
                       trang_thai=self.trang_thai, gia_tri=self.gia_tri,
                       nguon=self.nguon, do_luc=self.do_luc,
                       han_tuoi=self.han_tuoi, ly_do=self.ly_do,
                       bang_chung=self.bang_chung, nhan=self.op)


# ------------------------------------------------------------ vận chuyển ----

class TruyenSsh:
    """Gửi MỘT lệnh đọc tới máy xa. Cờ giống `SshServiceProvider` V0.5.

    Khoá riêng chỉ đi vào dòng lệnh dưới dạng ĐƯỜNG DẪN (`ssh -i <đường>`),
    không bao giờ nội dung; và đường dẫn vẫn bị `redact` trước khi vào bằng
    chứng hay nhật ký.
    """

    def __init__(self, cau_hinh: Dict[str, Any]):
        c = cau_hinh or {}
        self.host = str(c.get("host") or "")
        self.user = str(c.get("user") or "")
        self._khoa_raw = str(c.get("key_path") or "")
        self.han = float(c.get("timeout") or 20.0)

    @property
    def nguon(self) -> str:
        return f"ssh:{self.host}" if self.host else "ssh:?"

    def _duong_khoa(self) -> Optional[Path]:
        if not self._khoa_raw:
            return None
        p = Path(os.path.expandvars(os.path.expanduser(self._khoa_raw)))
        return p if p.is_file() else None

    def san_sang(self) -> Tuple[bool, str]:
        if not self.host:
            return False, "cấu hình thiếu `host`"
        if not shutil.which("ssh"):
            return False, "không có `ssh` trên PATH của máy này"
        if self._duong_khoa() is None:
            return False, f"không thấy tệp khoá đã cấu hình ({self._khoa_raw or 'chưa đặt'})"
        return True, ""

    def chay(self, lenh: str) -> Tuple[Optional[int], str, str]:
        ok, vi = self.san_sang()
        if not ok:
            return None, "", vi
        _kiem_chi_doc(lenh)
        argv = [
            shutil.which("ssh"), "-i", str(self._duong_khoa()),
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(max(3, self.han - 2))}",
            "-o", "NumberOfPasswordPrompts=0",
            f"{self.user}@{self.host}" if self.user else self.host,
            lenh,
        ]
        try:
            p = subprocess.run(argv, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=self.han, **an_cua_so())
        except subprocess.TimeoutExpired:
            return None, "", f"quá hạn {self.han:.0f}s"
        except OSError as exc:
            return None, "", f"{type(exc).__name__}: {exc}"
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


# ------------------------------------------------------------ bảng op ------

@dataclass(frozen=True)
class DinhNghiaOp:
    ten: str
    nhan: str
    kha_nang: str
    dung: Callable[["MoiGioiProbe", Dict[str, Any]], Tuple[str, str]]
    han_tuoi: float = 120.0


class MoiGioiProbe:
    """Môi giới probe vận hành cho MỘT dự án.

    Chỉ dựng được từ cấu hình quan sát của dự án — nghĩa là đích (host,
    unit, đường dẫn) đến từ tệp cấu hình đã kiểm, không đến từ câu người
    dùng hay từ đầu ra của một mô hình.
    """

    def __init__(self, cau_hinh_ssh: Optional[Dict[str, Any]] = None, *,
                 truyen: Optional[TruyenSsh] = None,
                 khong_kha_dung: Optional[Dict[str, str]] = None):
        c = dict(cau_hinh_ssh or {})
        self._c = c
        self.truyen = truyen if truyen is not None else (
            TruyenSsh(c) if c else None)
        self._khong_kha_dung = dict(khong_kha_dung or {})

        self._don_vi = tuple(x for x in [str(c.get("unit") or "")] if x)
        self._rclone_config = str(c.get("rclone_config") or "")
        self._rclone_remote = str(c.get("rclone_remote") or "")

        goc: List[str] = []
        for k in ("status_file", "disk_path"):
            v = str(c.get(k) or "")
            if v:
                try:
                    goc.append(_chuan_hoa_duong(v))
                except ThamSoKhongHopLe:
                    pass
        for v in (c.get("read_paths") or []):
            try:
                goc.append(_chuan_hoa_duong(str(v)))
            except ThamSoKhongHopLe:
                pass
        # `disk_path` thuong la "/" — no KHONG duoc tro thanh giay phep doc
        # ca may, nen goc "/" chi dung cho `disk_usage`.
        self._goc_doc = tuple(sorted({g for g in goc if g != "/"}))
        self._goc_dia = tuple(sorted({g for g in goc})) or ("/",)

    # -- kiểm tham số theo CẤU HÌNH ----------------------------------------

    def kiem_don_vi(self, gt: Any) -> str:
        s = _kiem_chuoi(gt, "don_vi")
        if s not in self._don_vi:
            raise ThamSoKhongHopLe(
                f"don_vi={s!r} không nằm trong danh sách đã khai "
                f"({list(self._don_vi) or 'trống'})")
        return s

    def kiem_duong(self, gt: Any, *, cho_dia: bool = False) -> str:
        d = _chuan_hoa_duong(str(gt))
        goc = self._goc_dia if cho_dia else self._goc_doc
        if not any(_duoi_goc(d, g) for g in goc):
            raise ThamSoKhongHopLe(
                f"duong={d!r} không nằm dưới gốc đọc đã khai ({list(goc)})")
        return d

    def kiem_remote(self, gt: Any) -> str:
        s = _kiem_chuoi(gt, "remote")
        if self._rclone_remote and s != self._rclone_remote:
            raise ThamSoKhongHopLe(
                f"remote={s!r} không phải remote đã khai "
                f"({self._rclone_remote!r})")
        return s

    # -- bảng thao tác ------------------------------------------------------

    def _op_is_active(self, p: Dict) -> Tuple[str, str]:
        u = self.kiem_don_vi(p.get("don_vi"))
        return f"systemctl is-active {u}", u

    def _op_show(self, p: Dict) -> Tuple[str, str]:
        u = self.kiem_don_vi(p.get("don_vi"))
        tt = p.get("thuoc_tinh") or ("MainPID", "NRestarts", "ActiveState",
                                     "SubState", "ExecMainStartTimestamp")
        if isinstance(tt, str):
            tt = [tt]
        xin = []
        for x in tt:
            s = _kiem_chuoi(x, "thuoc_tinh")
            if s not in THUOC_TINH_CHO_PHEP:
                raise ThamSoKhongHopLe(
                    f"thuoc_tinh={s!r} không được phép "
                    f"(có {len(THUOC_TINH_CHO_PHEP)} thuộc tính hợp lệ)")
            xin.append(s)
        if not xin:
            raise ThamSoKhongHopLe("thuoc_tinh: danh sách rỗng")
        return (f"systemctl show {u} --property={','.join(xin)} --no-pager", u)

    def _op_journal(self, p: Dict) -> Tuple[str, str]:
        u = self.kiem_don_vi(p.get("don_vi"))
        so = _kiem_so(p.get("so_luong", 40), "so_luong", nho_nhat=1,
                      lon_nhat=400)
        n = _kiem_so(p.get("khoang_so", 24), "khoang_so", nho_nhat=1,
                     lon_nhat=90)
        dv = _kiem_chuoi(p.get("khoang_don_vi", "hours"), "khoang_don_vi")
        if dv not in DON_VI_THOI_GIAN:
            raise ThamSoKhongHopLe(
                f"khoang_don_vi={dv!r} phải thuộc {list(DON_VI_THOI_GIAN)}")
        loc = _kiem_chuoi(p.get("loc", "tat_ca"), "loc")
        if loc not in LOC_JOURNAL:
            raise ThamSoKhongHopLe(
                f"loc={loc!r} phải thuộc {sorted(LOC_JOURNAL)}")
        # Chuoi `--since` do MA dung tu so + don vi DA KIEM, nen cau chu
        # nguoi dung khong bao gio cham toi dong lenh. Dang '24 hours ago'
        # la dang da chay THAT tren farmer; `--since 24h` tran KHONG hop le.
        lenh = (f"journalctl -u {u} --since '{n} {dv} ago' --no-pager "
                f"-o short-iso -n {so}")
        mau = LOC_JOURNAL[loc]
        if mau:
            # Mau PHAI duoc dat trong nhay don: no chua `|`, va de tran thi
            # shell hieu thanh ONG DAN — `grep -iE error|fail` se chay `fail`
            # nhu mot lenh. Mau lay tu bang co ten, khong tu nguoi dung.
            lenh += f" | grep -iE '{mau}'"
        return lenh, u

    def _op_stat(self, p: Dict) -> Tuple[str, str]:
        d = self.kiem_duong(p.get("duong"))
        return f"stat -c %n:size=%s:mtime=%Y:mode=%a:owner=%U:%G {d}", d

    def _op_list_dir(self, p: Dict) -> Tuple[str, str]:
        d = self.kiem_duong(p.get("duong"))
        so = _kiem_so(p.get("so_luong", 40), "so_luong", nho_nhat=1,
                      lon_nhat=200)
        return f"ls -1t {d} | head -n {so}", d

    def _op_read_text(self, p: Dict) -> Tuple[str, str]:
        d = self.kiem_duong(p.get("duong"))
        so = _kiem_so(p.get("so_dong", 40), "so_dong", nho_nhat=1,
                      lon_nhat=400)
        return f"tail -n {so} {d}", d

    def _op_disk(self, p: Dict) -> Tuple[str, str]:
        d = self.kiem_duong(p.get("duong", "/"), cho_dia=True)
        return f"df -Pk {d} | tail -n 1", d

    def _op_rclone_remotes(self, p: Dict) -> Tuple[str, str]:
        if not self._rclone_config:
            raise ThamSoKhongHopLe("chưa khai `rclone_config` cho dự án này")
        cf = _chuan_hoa_duong(self._rclone_config)
        return f"rclone --config {cf} listremotes", cf

    def _op_rclone_lsjson(self, p: Dict) -> Tuple[str, str]:
        if not self._rclone_config:
            raise ThamSoKhongHopLe("chưa khai `rclone_config` cho dự án này")
        cf = _chuan_hoa_duong(self._rclone_config)
        rm = self.kiem_remote(p.get("remote") or self._rclone_remote)
        duong = _kiem_chuoi(p.get("duong_remote", ""), "duong_remote") \
            if p.get("duong_remote") else ""
        so = _kiem_so(p.get("so_luong", 30), "so_luong", nho_nhat=1,
                      lon_nhat=200)
        dich = f"{rm}:{duong}" if duong else f"{rm}:"
        return (f"rclone --config {cf} lsjson --max-depth 1 {dich} "
                f"| head -c {so * 400}", dich)

    #: Bảng ĐĂNG KÝ. Đây là toàn bộ tập thao tác tồn tại — không có `chay
    #: lệnh tuỳ ý`, và không có đường nào thêm một thao tác lúc chạy.
    def _bang(self) -> Dict[str, DinhNghiaOp]:
        return {
            "systemd.is_active": DinhNghiaOp(
                "systemd.is_active", "trạng thái service", "systemd",
                lambda s, p: s._op_is_active(p), 60.0),
            "systemd.show": DinhNghiaOp(
                "systemd.show", "thuộc tính service", "systemd",
                lambda s, p: s._op_show(p), 60.0),
            "systemd.journal_tail": DinhNghiaOp(
                "systemd.journal_tail", "nhật ký service", "systemd",
                lambda s, p: s._op_journal(p), 120.0),
            "filesystem.stat": DinhNghiaOp(
                "filesystem.stat", "siêu dữ liệu tệp", "filesystem",
                lambda s, p: s._op_stat(p), 120.0),
            "filesystem.list_dir": DinhNghiaOp(
                "filesystem.list_dir", "liệt kê thư mục", "filesystem",
                lambda s, p: s._op_list_dir(p), 120.0),
            "filesystem.read_text": DinhNghiaOp(
                "filesystem.read_text", "đọc đuôi tệp văn bản", "filesystem",
                lambda s, p: s._op_read_text(p), 120.0),
            "filesystem.disk_usage": DinhNghiaOp(
                "filesystem.disk_usage", "dung lượng đĩa", "filesystem",
                lambda s, p: s._op_disk(p), 300.0),
            "rclone.listremotes": DinhNghiaOp(
                "rclone.listremotes", "danh sách remote", "rclone",
                lambda s, p: s._op_rclone_remotes(p), 600.0),
            "rclone.lsjson": DinhNghiaOp(
                "rclone.lsjson", "liệt kê remote (JSON)", "rclone",
                lambda s, p: s._op_rclone_lsjson(p), 300.0),
        }

    def ops(self) -> Tuple[str, ...]:
        return tuple(sorted(self._bang()))

    # -- chạy ---------------------------------------------------------------

    def chay(self, op: str, **tham_so: Any) -> KetQuaProbe:
        """Chạy MỘT thao tác có kiểu. Không bao giờ ném vì lỗi máy xa —
        lỗi thành `UNKNOWN`/`UNAVAILABLE` kèm lý do. Ném CHỈ khi lời gọi
        sai (op lạ, tham số trượt kiểm): đó là lỗi lập trình, không phải
        trạng thái của production."""
        bang = self._bang()
        dn = bang.get(op)
        if dn is None:
            raise OpKhongHopLe(
                f"thao tác {op!r} không tồn tại. Hợp lệ: {list(bang)}")
        cam = self._khong_kha_dung.get(op) or self._khong_kha_dung.get(dn.kha_nang)
        if cam:
            return KetQuaProbe(op=op, dich="", trang_thai=TrangThai.UNAVAILABLE,
                               nguon=self._nguon(), ly_do=cam)
        lenh, dich = dn.dung(self, dict(tham_so))
        _kiem_chi_doc(lenh)
        if self.truyen is None:
            return KetQuaProbe(op=op, dich=dich,
                               trang_thai=TrangThai.UNAVAILABLE,
                               nguon="", ly_do="dự án chưa khai đường probe nào")
        now = time.time()
        ma, ra, loi = self.truyen.chay(lenh)
        if ma is None:
            return KetQuaProbe(op=op, dich=dich, trang_thai=TrangThai.UNKNOWN,
                               nguon=self.truyen.nguon, do_luc=now,
                               han_tuoi=dn.han_tuoi,
                               ly_do=_loc(loi)[:200] or "không nối được máy xa")
        if ma == 1 and not ra and "| grep " in lenh:
            # `grep` tra 1 khi KHONG CO DONG NAO KHOP. Do la mot phep do
            # THAT ("48h qua khong co dong log nao ve archive"), khong phai
            # mot that bai — goi no UNKNOWN la vut di bang chung.
            return KetQuaProbe(op=op, dich=dich, trang_thai=TrangThai.ACTIVE,
                               gia_tri="", nguon=self.truyen.nguon,
                               do_luc=now, han_tuoi=dn.han_tuoi, ma_thoat=ma,
                               bang_chung="(không có dòng nào khớp bộ lọc)")
        if ma != 0 and not ra:
            return KetQuaProbe(op=op, dich=dich, trang_thai=TrangThai.UNKNOWN,
                               nguon=self.truyen.nguon, do_luc=now,
                               han_tuoi=dn.han_tuoi, ma_thoat=ma,
                               ly_do=_loc(loi)[:200] or f"mã thoát {ma}")
        return KetQuaProbe(op=op, dich=dich, trang_thai=TrangThai.ACTIVE,
                           gia_tri=_loc(ra)[:4000], nguon=self.truyen.nguon,
                           do_luc=now, han_tuoi=dn.han_tuoi, ma_thoat=ma,
                           bang_chung=_loc(ra)[:1200])

    def _nguon(self) -> str:
        return self.truyen.nguon if self.truyen else ""

    def kha_dung(self) -> Dict[str, Any]:
        """Năng lực nào dùng được BÂY GIỜ, cái nào không và VÌ SAO."""
        ra: Dict[str, Any] = {"ops": list(self.ops()), "khong_kha_dung": {}}
        if self.truyen is None:
            ra["san_sang"] = False
            ra["ly_do"] = "dự án chưa khai provider ssh_service"
            return ra
        ok, vi = self.truyen.san_sang()
        ra["san_sang"] = ok
        ra["nguon"] = self.truyen.nguon
        if not ok:
            ra["ly_do"] = vi
        if not self._rclone_config:
            ra["khong_kha_dung"]["rclone"] = "chưa khai `rclone_config`"
        ra["khong_kha_dung"].update(self._khong_kha_dung)
        ra["don_vi"] = list(self._don_vi)
        ra["goc_doc"] = list(self._goc_doc)
        return ra


# ------------------------------------------------- dựng từ cấu hình dự án ---

def tu_du_an(project_id: str, *, cau_hinh: Optional[Dict] = None,
             duong_cau_hinh=None) -> MoiGioiProbe:
    """Dựng môi giới từ cấu hình quan sát ĐÃ KIỂM của dự án."""
    from scripts.control_center.observability import config as _cf
    d = _cf.kiem_cau_hinh(cau_hinh) if cau_hinh is not None else _cf.nap(
        duong_cau_hinh)
    du_an = (d.get("projects") or {}).get(project_id) or {}
    ssh = None
    khong: Dict[str, str] = {}
    for p in (du_an.get("providers") or []):
        if p.get("type") == "ssh_service" and ssh is None:
            ssh = p
        elif p.get("type") == "unavailable":
            ly = str(p.get("reason") or "chưa khai đường đọc")
            for kn in (p.get("capabilities") or []):
                khong[str(kn)] = ly
    return MoiGioiProbe(ssh, khong_kha_dung=khong)


# ------------------------------------------------ kiểm toán đường ống ------

#: Sáu phân loại của đặc tả. `F` là mặc định và là câu trả lời ĐÚNG khi
#: bằng chứng chưa đủ — không bao giờ đoán A–E.
PHAN_LOAI = {
    "A": "Chưa có việc nào đạt chuẩn production.",
    "B": "Production có artifact nhưng archive lên Drive đang chờ.",
    "C": "Archive lên Drive đang HỎNG.",
    "D": "Đường ống tắc TRƯỚC bước archive.",
    "E": "Sai remote/tài khoản/đường dẫn Drive.",
    "F": "Chưa đủ bằng chứng để kết luận.",
}


@dataclass
class BaoCaoDuongOng:
    project_id: str
    phan_loai: str
    ly_do: str
    bang_chung: List[KetQuaProbe] = field(default_factory=list)
    thieu: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {"project_id": self.project_id, "phan_loai": self.phan_loai,
                "phan_loai_nhan": PHAN_LOAI.get(self.phan_loai, ""),
                "ly_do": self.ly_do, "thieu": list(self.thieu),
                "ts": self.ts,
                "bang_chung": [b.to_dict() for b in self.bang_chung]}

    def render(self) -> str:
        d = [f"KIỂM TOÁN ĐƯỜNG ỐNG PRODUCTION — {self.project_id}",
             f"Phân loại: {self.phan_loai} — {PHAN_LOAI.get(self.phan_loai,'')}",
             f"Lý do: {self.ly_do}", ""]
        for b in self.bang_chung:
            tt = b.hieu_luc().value
            if b.gia_tri is None:
                d.append(f"  [{tt:11s}] {b.op} ({b.dich}) — {b.ly_do}")
            else:
                gt = " ".join(str(b.gia_tri).split())[:200]
                d.append(f"  [{tt:11s}] {b.op} ({b.dich}) = {gt}"
                         f"  · nguồn {b.nguon} · {b.tuoi:.0f}s trước")
        if self.thieu:
            d += ["", "CHƯA ĐO ĐƯỢC (cần adapter đọc mới):"]
            d += [f"  - {x}" for x in self.thieu]
        return "\n".join(d)


def kiem_duong_ong(mg: MoiGioiProbe, *, gio: int = 24) -> BaoCaoDuongOng:
    """Thu thập bằng chứng CÓ THẬT rồi phân loại A–F.

    Luật cứng: chỉ khẳng định A–E khi có quan sát ĐO ĐƯỢC chống lưng. Thiếu
    thì `F` kèm danh sách đúng thứ còn thiếu — vì "không đo được" và "không
    có gì xảy ra" là hai câu khác nhau, và trộn chúng là bịa.
    """
    bc: List[KetQuaProbe] = []
    thieu: List[str] = []
    kd = mg.kha_dung()
    if not kd.get("san_sang"):
        return BaoCaoDuongOng(
            project_id="", phan_loai="F",
            ly_do=f"không có đường probe: {kd.get('ly_do') or 'chưa cấu hình'}",
            thieu=["kết nối probe tới máy production"])

    don_vi = (kd.get("don_vi") or [None])[0]

    def thu(op: str, **kw) -> Optional[KetQuaProbe]:
        try:
            r = mg.chay(op, **kw)
        except ProbeLoi as exc:
            return KetQuaProbe(op=op, dich="", trang_thai=TrangThai.UNAVAILABLE,
                               nguon=kd.get("nguon", ""), ly_do=str(exc)[:200])
        return r

    if don_vi:
        for op, kw in (("systemd.is_active", {"don_vi": don_vi}),
                       ("systemd.show", {"don_vi": don_vi}),
                       ("systemd.journal_tail",
                        {"don_vi": don_vi, "khoang_so": gio,
                         "khoang_don_vi": "hours", "so_luong": 40}),
                       ("systemd.journal_tail",
                        {"don_vi": don_vi, "khoang_so": max(gio, 48),
                         "khoang_don_vi": "hours", "loc": "archive",
                         "so_luong": 40})):
            r = thu(op, **kw)
            if r is not None:
                bc.append(r)

    for g in (kd.get("goc_doc") or []):
        r = thu("filesystem.stat", duong=g)
        if r is not None:
            bc.append(r)
        r2 = thu("filesystem.list_dir", duong=g, so_luong=20)
        if r2 is not None:
            bc.append(r2)

    r = thu("rclone.listremotes")
    if r is not None:
        bc.append(r)

    # -- NHIP TIM: status.json co DANG duoc ghi lai khong -------------------
    # Noi dung tep khong doc duoc (600 fanfic:fanfic), nhung MOC SUA DOI thi
    # doc duoc — va no tra loi dung cau "vong lap farmer con song khong".
    nhip = None
    for b in bc:
        if b.op != "filesystem.stat" or "status" not in b.dich:
            continue
        m = re.search(r"mtime=(\d+)", str(b.gia_tri or ""))
        if not m:
            continue
        tuoi = max(0.0, time.time() - int(m.group(1)))
        nhip = KetQuaProbe(
            op="derived.status_heartbeat", dich=b.dich,
            trang_thai=(TrangThai.ACTIVE if tuoi <= 3600 else TrangThai.DEGRADED),
            gia_tri=f"status.json sửa lần cuối {int(tuoi)}s trước",
            nguon=b.nguon, do_luc=b.do_luc, han_tuoi=b.han_tuoi,
            bang_chung=f"mtime={m.group(1)}")
        bc.append(nhip)
        break

    # -- phan loai, chi tu bang chung DO DUOC -------------------------------
    dv_state = next((b for b in bc if b.op == "systemd.is_active"), None)
    rclone_ok = next((b for b in bc if b.op == "rclone.listremotes"), None)

    do_duoc_archive = bool(rclone_ok and rclone_ok.hieu_luc().do_duoc
                           and rclone_ok.gia_tri)
    if not do_duoc_archive:
        thieu.append(
            "trạng thái Drive/rclone (liệt kê remote) — "
            + (rclone_ok.ly_do if rclone_ok and rclone_ok.ly_do
               else "chưa có đường đọc"))
    thieu.append("bộ đếm archive/round của farmer (`status.json`) — "
                 "tệp không đọc được bằng tài khoản quan sát")
    thieu.append("hàng đợi Appwrite và artifact R2 — chưa có adapter đọc")

    if dv_state is not None and dv_state.hieu_luc() is TrangThai.ACTIVE \
            and str(dv_state.gia_tri or "").strip() != "active":
        return BaoCaoDuongOng(
            project_id="", phan_loai="D", bang_chung=bc, thieu=thieu,
            ly_do=f"service không ở trạng thái `active` "
                  f"({str(dv_state.gia_tri).strip()!r})")

    biet = []
    if dv_state is not None and dv_state.hieu_luc().do_duoc:
        biet.append(f"service `{dv_state.dich}` = {str(dv_state.gia_tri).strip()}")
    if nhip is not None:
        biet.append(str(nhip.gia_tri))
    kho_archive = next((b for b in bc if b.op == "systemd.journal_tail"
                        and b.gia_tri == ""), None)
    if kho_archive is not None:
        biet.append("không có dòng nhật ký nào về archive/rclone/drive "
                    "trong cửa sổ đã soi")
    return BaoCaoDuongOng(
        project_id="", phan_loai="F", bang_chung=bc, thieu=thieu,
        ly_do=("đo được: " + "; ".join(biet) + ". "
               if biet else "")
        + ("nhưng KHÔNG đọc được bộ đếm archive/round, hàng đợi Appwrite hay "
           "listing Drive — nên không thể phân biệt A/B/C/D/E. Nói thẳng là "
           "chưa đủ bằng chứng thay vì chọn bừa một nguyên nhân."))


# ------------------------------------------------- gói bằng chứng cho worker

DAU_PROBE = "BẰNG CHỨNG VẬN HÀNH DO ROUTER ĐO"


def goi_bang_chung(bao_cao: BaoCaoDuongOng, *, tran_ky_tu: int = 6000) -> str:
    """Văn bản CÓ CẤU TRÚC để đính vào mục tiêu của worker headless.

    Worker KHÔNG cần công cụ `command`: nó nhận số đo đã có kèm nguồn gốc,
    và việc của nó là phân tích, không phải đi lấy dữ liệu.

    Trần token được giữ bằng cách CẮT NỘI DUNG rồi mới tuần tự hoá — cắt
    thẳng chuỗi JSON đã tuần tự hoá thì ra JSON GÃY, và một khối JSON gãy
    còn tệ hơn không có (worker sẽ đoán phần thiếu). Bài kiểm
    `test_goi_bang_chung_co_JSON_nguon_goc_va_bi_chan_do_dai` bắt lỗi này.
    """
    d = dict(bao_cao.to_dict())
    while True:
        tho = json.dumps(d, ensure_ascii=False)
        if len(tho) <= tran_ky_tu or len(d.get("bang_chung") or []) <= 1:
            break
        # Bo bot BANG CHUNG cuoi (it lien quan nhat), va noi ro da bo.
        bc = list(d["bang_chung"])
        bo = bc.pop()
        d["bang_chung"] = bc
        d["da_cat"] = int(d.get("da_cat", 0)) + 1
        d["da_cat_op"] = sorted(set(list(d.get("da_cat_op", []))
                                    + [str(bo.get("op", "?"))]))
    if len(tho) > tran_ky_tu:
        # Mot muc duy nhat cung vuot tran: rut gon truong dai nhat cua no.
        for m in d.get("bang_chung") or []:
            for k in ("gia_tri", "bang_chung"):
                if isinstance(m.get(k), str) and len(m[k]) > 400:
                    m[k] = m[k][:400] + "…(cắt)"
        tho = json.dumps(d, ensure_ascii=False)
    van = [f"{DAU_PROBE} (chỉ đọc, đã lọc bí mật). Phân tích NGAY trên dữ liệu "
           "dưới đây. KHÔNG chạy lệnh shell/systemctl/rclone: phiên headless "
           "từ chối quyền `command` và lượt của bạn sẽ kết thúc rỗng. Thiếu số "
           "nào thì NÓI RÕ thiếu gì, đừng suy ra.", "",
           bao_cao.render(), "",
           "JSON (nguồn gốc đầy đủ):", tho]
    return "\n".join(van)
