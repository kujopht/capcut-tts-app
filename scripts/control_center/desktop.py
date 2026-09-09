"""Điểm vào ứng dụng DESKTOP — `Router Control Center.exe`.

Đây là đường CHÍNH của V0.2 sau bản vỏ desktop. Nó mở một cửa sổ WebView2
và nạp giao diện web cục bộ. **Không mở Edge/Chrome.** Không cần console.

    Router Control Center.exe          <- bam doi
    router-cc-desktop.cmd              <- chay tu ma nguon
    python -m scripts.control_center.desktop

Mọi quyết định khởi động (một thực thể, nối lại hay tự chạy, ai sở hữu
backend) nằm ở `desktop_shell.py` — thuần Python, không cần GUI, và có bài
kiểm ở `scripts/tests`. Tệp này chỉ THỰC HIỆN kế hoạch đó rồi mở cửa sổ.

VÌ SAO BACKEND CHẠY TRONG CÙNG TIẾN TRÌNH (một luồng uvicorn) chứ không
phải một tiến trình con:

* Đóng cửa sổ là tắt sạch, không cần đi tìm và giết tiến trình con — chế
  độ hỏng phổ biến nhất của loại app này là để lại một backend mồ côi giữ
  cổng, và lần mở sau thì "cổng đang được dùng".
* Không có dòng lệnh nào mang token, nên token không lộ ra Task Manager.
* Ít một lớp phải chờ khoẻ.

Đánh đổi: một exception chết người trong backend sẽ hạ cả cửa sổ. Với một
công cụ cá nhân thì đó là đánh đổi đúng — và `webapi.py` đã bọc mọi
endpoint.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from scripts.control_center.ghi_utf8 import (BoDocUTF8, GhiUTF8,
                                             duong_nhat_ky,
                                             hop_thoai_loi)

# KHONG `sys.stdout.reconfigure(...)` o day, va do la mot dinh chinh:
# ban truoc dung `reconfigure(encoding='utf-8', errors='replace')`, va no
# vua LOSSY (bien `ư` thanh `?`) vua KHONG DU — trong ban build
# `--noconsole`, `sys.stdout` co the la `None` hoac khong co
# `.reconfigure`, nen phep goi bi bo qua am tham roi `print()` van di
# qua codec cua locale va no ngoai le.
#
# Moi chan doan gio di qua `GhiUTF8`: ma hoa UTF-8 roi ghi BYTE. Xem
# `ghi_utf8.py` cho ca cau chuyen.
TIEU_DE = "Router Control Center"

#: Doi tuong ghi chan doan. Nhan tep nhat ky trong `main()` khi da
#: biet thu muc goc. Truoc do van ghi duoc ra luong — chi chua co
#: tep.
ghi = GhiUTF8()


def _bao_loi(thong_diep: str) -> None:
    """Bao loi theo duong NGUOI DUNG THAY.

    EXE build o che do `--noconsole`, nen `stderr` khong co ai doc. Ca
    hai duong o day deu an toan voi Unicode: `GhiUTF8` ghi byte UTF-8,
    va `MessageBoxW` la API wide (UTF-16).
    """
    ghi(thong_diep)
    hop_thoai_loi(TIEU_DE, thong_diep)


def _goc_mac_dinh() -> Path:
    """Thư mục giữ sổ.

    Khi chạy từ EXE đã đóng gói, `cwd` là bất kỳ đâu Explorer đang mở, nên
    KHÔNG dùng `Path.cwd()`. Dùng thư mục cạnh chính EXE — đúng như
    `cc_agent_tool.py` neo `REPO_ROOT` vào vị trí tệp thay vì vào `cwd`.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def main(argv=None) -> int:
    # `BoDocUTF8`, khong phai `ArgumentParser`: moi chuoi `help=`
    # duoi day la tieng Viet, va `argparse` ghi chung thang ra tang
    # VAN BAN cua luong. Voi bo doc thuong thi `--help` tren may
    # cp1252 nem `UnicodeEncodeError` tren chu `ứ` — dung loai loi da
    # lam EXE chet, chi khac cho phat sinh.
    ap = BoDocUTF8(
        prog="Router Control Center", ghi=ghi,
        description="Router Control Center V0.2 — ứng dụng desktop")
    ap.add_argument("--root", default="", help="thư mục gốc giữ sổ .router/")
    ap.add_argument("--project", default="", help="dự án mở sẵn")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--no-recover", action="store_true")
    ap.add_argument("--debug-cdp", type=int, default=0,
                    help=("mở cổng DevTools của WebView2 (chỉ để KIỂM; "
                          "0 = tắt)"))
    ap.add_argument("--check", action="store_true",
                    help="chỉ kiểm phụ thuộc rồi thoát")
    a = ap.parse_args(argv)

    if a.check:
        thieu = []
        for ten in ("webview", "fastapi", "uvicorn"):
            try:
                __import__(ten)
            except ModuleNotFoundError:
                thieu.append(ten)
        if thieu:
            _bao_loi(
                f"Thiếu gói: {', '.join(thieu)}\n\n"
                "Cài đặt:\n"
                "    python -m pip install -r "
                "requirements-control-center-desktop.txt")
            return 2
        ghi("phụ thuộc desktop: đủ")
        return 0

    try:
        import webview
    except ModuleNotFoundError:
        _bao_loi("Thiếu gói 'pywebview' — chưa có phụ thuộc desktop.\n\n"
                 "Cài đặt:\n    python -m pip install -r "
                 "requirements-control-center-desktop.txt\n\n"
                 "Hoặc dùng đường gỡ lỗi:\n    router-cc-web.cmd")
        return 2

    from scripts.control_center.desktop_shell import (
        MotThucThe, ThongTinPhien, cho_backend_khoe, duong_giao_dien,
        duong_webview2, ghi_tep_khoa, quyet_dinh, ten_mutex_cua,
        xoa_tep_khoa)

    goc = Path(a.root).resolve() if a.root else _goc_mac_dinh()

    # Tu day chan doan cung duoc ghi vao mot TEP UTF-8 canh so. Voi ban
    # `--noconsole` thi day la NOI DUY NHAT doc duoc chan doan, nen no
    # khong phai tien nghi — no la cach duy nhat de go loi mot lan mo
    # that.
    ghi.dat_tep(duong_nhat_ky(goc))

    # CDP cua WebView2 phai duoc dat TRUOC khi cua so duoc dung. Chi bat
    # khi co `--debug-cdp`: mo mot cong DevTools mac dinh la mo mot duong
    # dieu khien vao chinh cua so nay.
    if a.debug_cdp:
        os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
            f"--remote-debugging-port={a.debug_cdp}")

    # Mot thuc the THEO THU MUC GOC, khong theo ca may — xem
    # `ten_mutex_cua`. Bam doi cung mot EXE van ra cung mot goc, nen hanh
    # vi cua nguoi dung khong doi mot chut nao.
    mot = MotThucThe(ten_mutex_cua(goc))
    kh = quyet_dinh(goc, co_thuc_the_khac=mot.da_co, cong_muon=a.port)

    if kh.hanh_dong == "nhuong":
        # KHONG bao loi bang MessageBox o day: bam doi hai lan la thao tac
        # binh thuong, va mot hop thoai loi cho viec do la lam nguoi dung
        # tuong minh vua lam sai.
        ghi(f"[desktop] {kh.ly_do} — thoát.")
        mot.nha()
        return 0

    ghi(f"[desktop] {kh.ly_do}")
    cc = None
    sv = None
    luong = None

    if kh.hanh_dong == "tu_chay":
        try:
            import uvicorn
            from scripts.control_center.bootstrap import khoi_tao
            from scripts.control_center.engine import ControlCenter
            from scripts.control_center.webapi import PhienWeb, dung_app
        except ModuleNotFoundError as exc:
            _bao_loi(f"Thiếu gói {exc.name!r} — chưa có phụ thuộc web.\n\n"
                     "Cài đặt:\n    python -m pip install -r "
                     "requirements-control-center-web.txt")
            mot.nha()
            return 2

        # `leader_bat=True`: day la mot diem vao THAT cua san pham, va o
        # chat phai la mot tro ly chu khong phai mot bieu mau nop viec.
        cc = ControlCenter(root=goc, max_parallel=a.max_parallel,
                           leader_bat=True)
        khoi_tao(cc.store, root=goc)
        if not a.no_recover:
            try:
                cc.recover()
            except Exception as exc:                        # noqa: BLE001
                ghi(f"[desktop] phục hồi bỏ qua: {exc}")
        cc.start()

        phien = PhienWeb(cc, token=kh.token, cong=kh.cong)
        sv = uvicorn.Server(uvicorn.Config(
            dung_app(phien), host="127.0.0.1", port=kh.cong,
            log_level="warning", access_log=False))
        luong = threading.Thread(target=sv.run, daemon=True)
        luong.start()

        if not cho_backend_khoe(kh.cong, kh.token):
            _bao_loi("Backend không khởi động được trong 20 giây.\n\n"
                     "Thử đường gỡ lỗi để xem nhật ký:\n"
                     "    router-cc-web.cmd")
            sv.should_exit = True
            cc.shutdown()
            mot.nha()
            return 3

        # Ghi tep khoa SAU KHI backend da khoe: mot tep khoa tro tay mot
        # cong chua san sang se lam lan mo sau doi 20s roi bo.
        ghi_tep_khoa(goc, ThongTinPhien(pid=os.getpid(), cong=kh.cong,
                                        token=kh.token,
                                        bat_dau_luc=time.time()))
        ghi(f"[desktop] backend sẵn sàng ở 127.0.0.1:{kh.cong}")

    duong = duong_giao_dien(kh.cong, kh.token)
    if a.project:
        duong += f"#project={a.project}"

    def _khi_dong():
        """Đóng cửa sổ = tắt backend, TRỪ KHI ta không sở hữu nó."""
        if not kh.so_huu:
            ghi("[desktop] backend do tiến trình khác sở hữu — để nguyên.")
            mot.nha()
            return
        ghi("[desktop] đang tắt backend…")
        if sv is not None:
            sv.should_exit = True
        if luong is not None:
            luong.join(timeout=8)
        if cc is not None:
            try:
                cc.shutdown()
            except Exception as exc:                        # noqa: BLE001
                ghi(f"[desktop] shutdown: {exc}")
        xoa_tep_khoa(goc)
        mot.nha()

    cua_so = webview.create_window(
        TIEU_DE, duong, width=1440, height=920, min_size=(980, 640),
        text_select=True, confirm_close=False)
    cua_so.events.closed += _khi_dong

    # `gui='edgechromium'` la WebView2. Ghim tuong minh chu khong de
    # pywebview tu chon: bo dong `mshtml` (IE11) cung nam trong danh sach
    # tu chon cua no tren Windows, va no khong chay duoc frontend nay —
    # khong ES module, khong `<dialog>`, khong WebSocket dang nay.
    # `storage_path`: HO SO WEBVIEW2 RIENG THEO THU MUC GOC.
    #
    # Mac dinh cua pywebview la `%APPDATA%\pywebview\EBWebView` — MOT
    # thu muc dung chung cho MOI ung dung pywebview tren may. WebView2
    # chi cho nhieu tien trinh dung chung mot ho so khi
    # `AdditionalBrowserArguments` GIONG NHAU, nen mot ban thu hai cua
    # app nay (hoac mot app pywebview cua ben thu ba) du de lam
    # `webview.start()` nem `0x8007139F` — "the group or resource is not
    # in the correct state" — va nguoi dung khong the suy ra vi sao.
    # Da gap that tren ban dong goi. Xem `duong_webview2`.
    ho_so = duong_webview2(goc)
    try:
        ho_so.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        ghi(f"[desktop] không tạo được hồ sơ WebView2 {ho_so}: {exc}")
    ghi(f"[desktop] hồ sơ WebView2: {ho_so}")
    try:
        webview.start(gui="edgechromium", debug=bool(a.debug_cdp),
                      private_mode=False, storage_path=str(ho_so))
    except Exception as exc:                                # noqa: BLE001
        _bao_loi(
            f"Không mở được cửa sổ WebView2: {type(exc).__name__}: {exc}\n\n"
            "Cần 'Microsoft Edge WebView2 Runtime' (Evergreen). Nếu thiếu, "
            "tải ở:\n"
            "    https://developer.microsoft.com/microsoft-edge/webview2/\n\n"
            "Hoặc dùng đường gỡ lỗi:\n    router-cc-web.cmd")
        _khi_dong()
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
