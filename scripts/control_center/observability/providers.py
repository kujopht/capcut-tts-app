"""Các provider cụ thể: Router, kho git, dịch vụ qua SSH, và các probe
CHƯA CÓ ĐƯỜNG AN TOÀN (Appwrite / R2 / Drive) — khai giao diện, báo
`UNAVAILABLE` kèm lý do chính xác, không chặn cả tính năng.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from scripts.control_center.observability.model import (KhoiQuanSat, QuanSat,
                                                        TrangThai)
from scripts.control_center.observability.provider import ProviderCoSo
from scripts.router_v3.packet import redact
from scripts.router_v3.tien_trinh import an_cua_so


# =========================================================== ROUTER =========
class RouterProvider(ProviderCoSo):
    """Trạng thái do CHÍNH Control Center điều phối.

    Đặt cạnh các provider khác nhưng nằm ở nhóm `router` — và đó là cả
    điểm của V0.5: nó KHÔNG bao giờ được gộp vào `trang_thai_chung` của
    dự án. `AnhChupSong.trang_thai_chung` cố ý bỏ qua nhóm này.
    """

    ma = "router"
    nhan = "Router"
    nhom = "router"

    def kha_nang(self) -> Sequence[str]:
        return ("running_tasks", "live_agents", "recent_tasks")

    def _do(self, ctx) -> KhoiQuanSat:
        store = ctx["store"]
        pid = ctx["project_id"]
        tasks = store.tasks(pid)
        sessions = store.sessions(pid)
        chay = [t for t in tasks if getattr(t.state, "value", t.state)
                == "RUNNING"]
        song = [s for s in sessions
                if getattr(s.state, "alive", False)]
        k = KhoiQuanSat(khoa=self.ma, nhan=self.nhan)
        now = time.time()
        k.them(QuanSat(
            khoa="running_tasks",
            # Router luon do duoc (doc so cua chinh minh), nen ACTIVE khi
            # co viec va DOWN khi khong. `DOWN` o day noi ve ROUTER, va
            # nhom `router` khong tham gia trang thai chung cua du an.
            trang_thai=TrangThai.ACTIVE if chay else TrangThai.DOWN,
            gia_tri=len(chay), nguon="router:store", do_luc=now,
            nhan="việc đang chạy"))
        k.them(QuanSat(
            khoa="live_agents",
            trang_thai=TrangThai.ACTIVE if song else TrangThai.DOWN,
            gia_tri=len(song), nguon="router:store", do_luc=now,
            nhan="agent đang sống"))
        k.them(QuanSat(
            khoa="recent_tasks", trang_thai=TrangThai.ACTIVE,
            gia_tri=len(tasks), nguon="router:store", do_luc=now,
            nhan="tổng việc trong sổ"))
        return k


# ============================================================== GIT =========
class GitProvider(ProviderCoSo):
    """Kho git của dự án: nhánh, HEAD, sạch/bẩn. Bậc 2 (KHO)."""

    ma = "git"
    nhan = "Kho git"
    nhom = "kho"
    han = 20.0

    def kha_nang(self) -> Sequence[str]:
        return ("branch", "head", "dirty")

    def _git(self, kho: str, *args: str) -> Optional[str]:
        try:
            p = subprocess.run(["git", "-C", kho, *args],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=self.han, **an_cua_so())
        except (OSError, subprocess.SubprocessError):
            return None
        return (p.stdout or "").strip() if p.returncode == 0 else None

    def _do(self, ctx) -> KhoiQuanSat:
        kho = str(ctx.get("repo_path") or "")
        k = KhoiQuanSat(khoa=self.ma, nhan=self.nhan)
        if not kho or not (Path(kho) / ".git").exists():
            k.them(QuanSat(khoa="branch", trang_thai=TrangThai.UNAVAILABLE,
                           nguon="git",
                           ly_do=f"không phải kho git: {kho or '(trống)'}"))
            return k
        now = time.time()
        nhanh = self._git(kho, "rev-parse", "--abbrev-ref", "HEAD")
        head = self._git(kho, "rev-parse", "HEAD")
        tt = self._git(kho, "status", "--porcelain")
        for khoa, gt, nhan in (("branch", nhanh, "nhánh"),
                               ("head", (head or "")[:10] or None, "HEAD")):
            if gt:
                k.them(QuanSat(khoa=khoa, trang_thai=TrangThai.ACTIVE,
                               gia_tri=gt, nguon="git", do_luc=now,
                               nhan=nhan))
            else:
                k.them(QuanSat(khoa=khoa, trang_thai=TrangThai.UNKNOWN,
                               nguon="git", ly_do="lệnh git không trả về"))
        if tt is None:
            k.them(QuanSat(khoa="dirty", trang_thai=TrangThai.UNKNOWN,
                           nguon="git", ly_do="`git status` không trả về"))
        else:
            n = len([d for d in tt.splitlines() if d.strip()])
            k.them(QuanSat(khoa="dirty",
                           trang_thai=(TrangThai.DEGRADED if n
                                       else TrangThai.ACTIVE),
                           gia_tri=n, nguon="git", do_luc=now,
                           nhan="tệp đang đổi"))
        return k


# ====================================================== SSH SERVICE =========
#: Lenh CHI DOC duoc phep gui qua SSH. Allowlist, fail closed.
#:
#: Moi phan tu la mot MAU co dinh; provider khong bao gio ghep lenh tu
#: chuoi nguoi dung. Doi chieu voi `KHONG_DUOC_CO` trong `provider.py`:
#: khong mot muc nao o day doi trang thai may xa.
LENH_DOC = {
    "is_active": "systemctl is-active {don_vi}",
    "show": ("systemctl show {don_vi} "
             "--property=MainPID,NRestarts,ActiveState,SubState,"
             "ExecMainStartTimestamp --no-pager"),
    "status_file": "cat {tep_trang_thai}",
    # Du phong khi `cat` bi tu choi quyen: `stat` chi doc SIEU DU LIEU va
    # thuong van chay duoc khi noi dung khong doc duoc. Do that tren
    # production: `status.json` cua farmer thuoc root, nen `cat` tra
    # "Permission denied" — nhung moc sua doi van lay duoc, va do la thu
    # tra loi cau "so nay con moi khong".
    #
    # KHONG dung `sudo`: no doi nang quyen tren mot may production, va
    # mot lop QUAN SAT khong duoc lam viec do. Cach sua dung nam o phia
    # may chu (cho tep readable theo nhom) — ghi trong bao cao.
    "status_mtime": "stat -c %Y {tep_trang_thai}",
    "disk": "df -Pk {duong_dia} | tail -1",
}


class SshServiceProvider(ProviderCoSo):
    """Một systemd service trên máy xa, quan sát qua SSH — CHỈ ĐỌC.

    KHÔNG BAO GIỜ nhận lệnh tuỳ ý: mỗi lượt chỉ gửi những mẫu trong
    `LENH_DOC` với tham số đã lấy từ cấu hình dự án. Cấu hình chỉ giữ
    **bí danh khoá**, không giữ nội dung khoá riêng — xem `config.py`.

    Khoá riêng KHÔNG đi vào dòng lệnh nào có thể bị đọc lại: `ssh -i
    <đường dẫn>` mang ĐƯỜNG DẪN, không mang nội dung. Đường dẫn vẫn bị
    `redact` trước khi vào `bang_chung`/nhật ký.
    """

    ma = "ssh_service"
    nhan = "Dịch vụ (SSH)"
    nhom = "dich_vu"
    han = 12.0

    def __init__(self, cau_hinh: Dict[str, Any]):
        c = cau_hinh or {}
        self.ma = str(c.get("id") or "ssh_service")
        self.nhan = str(c.get("label") or "Dịch vụ (SSH)")
        self._host = str(c.get("host") or "")
        self._user = str(c.get("user") or "")
        self._don_vi = str(c.get("unit") or "")
        self._tep_tt = str(c.get("status_file") or "")
        self._duong_dia = str(c.get("disk_path") or "/")
        self._khoa = str(c.get("key_path") or "")
        self.han = float(c.get("timeout") or 12.0)
        #: `han_tuoi` cho moi quan sat cua provider nay: qua nguong thi
        #: `hieu_luc()` tra `STALE` thay vi mot con so cu doi lot hien tai.
        self._han_tuoi = float(c.get("max_age") or 120.0)

    def kha_nang(self) -> Sequence[str]:
        return ("ssh", "service_state", "main_pid", "restarts",
                "status_file", "healthy", "round", "last_update", "disk")

    # -- ha tang ------------------------------------------------------------

    def _duong_khoa(self) -> Optional[Path]:
        if not self._khoa:
            return None
        p = Path(os.path.expandvars(os.path.expanduser(self._khoa)))
        return p if p.is_file() else None

    def _ssh(self, lenh: str):
        """Chạy MỘT lệnh đọc trên máy xa. Trả `(ma, ra, loi)`."""
        exe = shutil.which("ssh")
        if not exe:
            return None, "", "không có `ssh` trên PATH của máy này"
        khoa = self._duong_khoa()
        if khoa is None:
            return None, "", (f"không thấy tệp khoá đã cấu hình "
                              f"({self._khoa or 'chưa đặt'})")
        argv = [
            exe, "-i", str(khoa),
            "-o", "BatchMode=yes",              # KHONG bao gio hoi mat khau
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={int(max(3, self.han - 2))}",
            "-o", "NumberOfPasswordPrompts=0",
            f"{self._user}@{self._host}" if self._user else self._host,
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

    # -- do -----------------------------------------------------------------

    def _do(self, ctx) -> KhoiQuanSat:
        k = KhoiQuanSat(khoa=self.ma, nhan=self.nhan)
        if not self._host or not self._don_vi:
            k.them(QuanSat(khoa="ssh", trang_thai=TrangThai.UNAVAILABLE,
                           nguon=self.ma,
                           ly_do="cấu hình thiếu `host` hoặc `unit`"))
            return k

        nguon = f"ssh:{self._host}"
        now = time.time()
        ma, ra, loi = self._ssh(
            LENH_DOC["is_active"].format(don_vi=self._don_vi))
        if ma is None:
            # KHONG ket luan DOWN. Khong noi duoc voi may thi khong biet
            # dich vu the nao — day dung la cho ma mot ban cai te se ghi
            # `DOWN` va noi doi.
            k.them(QuanSat(khoa="ssh", trang_thai=TrangThai.UNKNOWN,
                           nguon=nguon,
                           ly_do=redact(loi)[:200] or "SSH không nối được"))
            return k

        k.them(QuanSat(khoa="ssh", trang_thai=TrangThai.ACTIVE, gia_tri="ok",
                       nguon=nguon, do_luc=now, han_tuoi=self._han_tuoi,
                       nhan="SSH"))
        tt = (ra or "").strip()
        # `is-active` tra `active`/`inactive`/`failed`/`activating`; ma
        # thoat != 0 cho moi cai khong phai `active`, nen phai doc CHU.
        if tt == "active":
            tt_dv = TrangThai.ACTIVE
        elif tt in ("activating", "reloading", "deactivating"):
            tt_dv = TrangThai.DEGRADED
        elif tt in ("inactive", "failed", "dead"):
            tt_dv = TrangThai.DOWN
        else:
            tt_dv = TrangThai.UNKNOWN
        k.them(QuanSat(
            khoa="service_state", trang_thai=tt_dv,
            gia_tri=tt or None, nguon=nguon, do_luc=now,
            han_tuoi=self._han_tuoi, nhan="systemd",
            ly_do=("" if tt_dv is not TrangThai.UNKNOWN
                   else f"`is-active` trả chuỗi lạ: {tt!r}"),
            bang_chung=redact(tt)[:120]))

        self._doc_show(k, nguon, now)
        if self._tep_tt:
            self._doc_status_file(k, nguon, now)
        self._doc_dia(k, nguon, now)
        return k

    def _doc_show(self, k: KhoiQuanSat, nguon: str, now: float) -> None:
        ma, ra, loi = self._ssh(
            LENH_DOC["show"].format(don_vi=self._don_vi))
        if ma != 0:
            for khoa in ("main_pid", "restarts"):
                k.them(QuanSat(khoa=khoa, trang_thai=TrangThai.UNKNOWN,
                               nguon=nguon,
                               ly_do=redact(loi)[:160]
                               or "`systemctl show` không trả về"))
            return
        d: Dict[str, str] = {}
        for dong in (ra or "").splitlines():
            if "=" in dong:
                a, b = dong.split("=", 1)
                d[a.strip()] = b.strip()
        pid = d.get("MainPID", "")
        k.them(QuanSat(
            khoa="main_pid",
            trang_thai=(TrangThai.ACTIVE if pid.isdigit() and int(pid) > 0
                        else TrangThai.DOWN),
            gia_tri=int(pid) if pid.isdigit() and int(pid) > 0 else 0,
            nguon=nguon, do_luc=now, han_tuoi=self._han_tuoi, nhan="MainPID"))
        rs = d.get("NRestarts", "")
        if rs.isdigit():
            n = int(rs)
            k.them(QuanSat(
                khoa="restarts",
                # Co restart KHONG phai DOWN — dich vu dang chay. No la
                # mot dau hieu, nen DEGRADED.
                trang_thai=TrangThai.DEGRADED if n else TrangThai.ACTIVE,
                gia_tri=n, nguon=nguon, do_luc=now,
                han_tuoi=self._han_tuoi, nhan="NRestarts"))
        else:
            k.them(QuanSat(khoa="restarts", trang_thai=TrangThai.UNKNOWN,
                           nguon=nguon,
                           ly_do="`NRestarts` không đọc được"))
        moc = d.get("ExecMainStartTimestamp", "")
        if moc:
            k.them(QuanSat(khoa="started_at", trang_thai=TrangThai.ACTIVE,
                           gia_tri=moc, nguon=nguon, do_luc=now,
                           han_tuoi=self._han_tuoi, nhan="bắt đầu lúc"))

    def _doc_status_file(self, k: KhoiQuanSat, nguon: str,
                         now: float) -> None:
        ma, ra, loi = self._ssh(
            LENH_DOC["status_file"].format(tep_trang_thai=self._tep_tt))
        if ma != 0:
            vi = (redact(loi)[:160]
                  or f"không đọc được {self._tep_tt}")
            for khoa in ("status_file", "healthy", "round"):
                k.them(QuanSat(khoa=khoa, trang_thai=TrangThai.UNKNOWN,
                               nguon=nguon, ly_do=vi))
            # Con noi dung khong doc duoc, nhung MOC SUA DOI thi thuong
            # van lay duoc — va do la thu tra loi "so nay con moi khong".
            self._doc_mtime(k, nguon, now, vi)
            return
        try:
            d = json.loads(ra or "{}")
            if not isinstance(d, dict):
                raise ValueError("không phải object")
        except (ValueError, json.JSONDecodeError) as exc:
            k.them(QuanSat(khoa="status_file",
                           trang_thai=TrangThai.UNKNOWN, nguon=nguon,
                           ly_do=f"status.json không đọc được: {exc}"[:160]))
            return
        k.them(QuanSat(khoa="status_file", trang_thai=TrangThai.ACTIVE,
                       gia_tri="ok", nguon=nguon, do_luc=now,
                       han_tuoi=self._han_tuoi, nhan="status.json",
                       bang_chung=redact(json.dumps(
                           d, ensure_ascii=False))[:400]))
        khoe = d.get("healthy")
        if isinstance(khoe, bool):
            k.them(QuanSat(
                khoa="healthy",
                trang_thai=TrangThai.ACTIVE if khoe else TrangThai.DEGRADED,
                gia_tri=khoe, nguon=nguon, do_luc=now,
                han_tuoi=self._han_tuoi, nhan="healthy"))
        else:
            k.them(QuanSat(khoa="healthy", trang_thai=TrangThai.UNAVAILABLE,
                           nguon=nguon,
                           ly_do="status.json không có khoá `healthy`"))
        for khoa_ta, ten_json, nhan in (
                ("round", "round", "round"),
                ("last_update", "updated_at", "cập nhật lúc"),
                ("started_at_app", "started_at", "app bắt đầu"),
                ("archive_status", "archive_status", "archive")):
            gt = d.get(ten_json)
            if gt is None:
                k.them(QuanSat(khoa=khoa_ta,
                               trang_thai=TrangThai.UNAVAILABLE,
                               nguon=nguon,
                               ly_do=f"status.json không có `{ten_json}`"))
            else:
                k.them(QuanSat(khoa=khoa_ta, trang_thai=TrangThai.ACTIVE,
                               gia_tri=gt, nguon=nguon, do_luc=now,
                               han_tuoi=self._han_tuoi, nhan=nhan))

    def _doc_mtime(self, k: KhoiQuanSat, nguon: str, now: float,
                   vi_sao_cat_hong: str) -> None:
        """`last_update` từ mốc sửa đổi tệp, khi nội dung không đọc được."""
        ma, ra, loi = self._ssh(
            LENH_DOC["status_mtime"].format(tep_trang_thai=self._tep_tt))
        so = (ra or "").strip()
        if ma != 0 or not so.isdigit():
            k.them(QuanSat(khoa="last_update",
                           trang_thai=TrangThai.UNKNOWN, nguon=nguon,
                           ly_do=(f"{vi_sao_cat_hong}; `stat` cũng không "
                                  f"đọc được: {redact(loi)[:80]}")[:200]))
            return
        moc = float(so)
        tuoi = max(0.0, now - moc)
        k.them(QuanSat(
            khoa="last_update",
            # Tep trang thai qua cu = dich vu con chay nhung khong con
            # ghi tien do -> mot dau hieu, chua phai DOWN.
            trang_thai=(TrangThai.DEGRADED if tuoi > 900 else
                        TrangThai.ACTIVE),
            gia_tri=int(moc), nguon=nguon, do_luc=now,
            han_tuoi=self._han_tuoi,
            nhan="status.json sửa lúc (epoch)",
            bang_chung=f"{tuoi:.0f}s trước; nội dung không đọc được "
                       f"({vi_sao_cat_hong[:60]})"))

    def _doc_dia(self, k: KhoiQuanSat, nguon: str, now: float) -> None:
        ma, ra, loi = self._ssh(
            LENH_DOC["disk"].format(duong_dia=self._duong_dia))
        if ma != 0 or not ra:
            k.them(QuanSat(khoa="disk", trang_thai=TrangThai.UNKNOWN,
                           nguon=nguon,
                           ly_do=redact(loi)[:160] or "`df` không trả về"))
            return
        phan = ra.split()
        pc = next((x for x in phan if x.endswith("%")), "")
        so = pc.rstrip("%")
        if not so.isdigit():
            k.them(QuanSat(khoa="disk", trang_thai=TrangThai.UNKNOWN,
                           nguon=nguon,
                           ly_do=f"`df` không đọc được: {redact(ra)[:80]}"))
            return
        n = int(so)
        k.them(QuanSat(
            khoa="disk",
            trang_thai=(TrangThai.DEGRADED if n >= 90 else TrangThai.ACTIVE),
            gia_tri=n, nguon=nguon, do_luc=now, han_tuoi=self._han_tuoi,
            nhan="đĩa đã dùng %"))


# ============================== PROBE CHUA CO DUONG AN TOAN =================
class ProbeChuaCoDuong(ProviderCoSo):
    """Provider khai GIAO DIỆN nhưng báo `UNAVAILABLE` kèm lý do chính xác.

    Mục 4 của yêu cầu V0.5: Appwrite / R2 / Drive chỉ được lộ ra ở dạng
    chỉ-đọc **nếu đã có mã tích hợp an toàn**. Kho này KHÔNG có: mọi
    đường tới ba hệ đó đi qua credential production mà V0.5 bị cấm đọc
    hay tạo. Nên chúng ở đây với một lý do đọc được, KHÔNG phải một con
    số bịa và cũng KHÔNG phải `DOWN`.

    Đây là chỗ một bản cài tệ sẽ ghi `state: "unknown", count: 0`. `0` là
    một khẳng định về production mà không ai đo — cùng loại lỗi với
    "Router rảnh nên farmer đã dừng".
    """

    def __init__(self, ma: str, nhan: str, nhom: str, ly_do: str,
                 kha_nang: Sequence[str] = ()):
        self.ma, self.nhan, self.nhom = ma, nhan, nhom
        self._ly_do = ly_do
        self._kn = tuple(kha_nang)

    def kha_nang(self) -> Sequence[str]:
        return self._kn

    def _do(self, ctx) -> KhoiQuanSat:
        k = KhoiQuanSat(khoa=self.ma, nhan=self.nhan, ly_do=self._ly_do)
        k.them(QuanSat(khoa="state", trang_thai=TrangThai.UNAVAILABLE,
                       nguon=self.ma, ly_do=self._ly_do))
        return k
