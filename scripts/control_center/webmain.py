"""Điểm vào giao diện WEB: `python -m scripts.control_center.webmain`.

Đây là đường CHÍNH của V0.2. Nó làm đúng bốn việc, theo thứ tự:

    1. sinh token phiên (ngẫu nhiên, mỗi lần chạy một token)
    2. chọn một cổng RỖNG trên 127.0.0.1
    3. mở trình duyệt tới `http://127.0.0.1:<cổng>/?t=<token>`
    4. chạy uvicorn — và CHỈ bind 127.0.0.1

BA ĐIỀU VỀ AN TOÀN, vì một localhost server không phải là riêng tư:

* **`127.0.0.1`, không bao giờ `0.0.0.0`.** Một ký tự khác biệt giữa "công
  cụ cá nhân" và "mở cổng điều khiển Router ra cả mạng LAN". Có bài kiểm
  đọc mã nguồn (đã bỏ chú thích) và đòi chuỗi kia không xuất hiện.
* **Cổng ngẫu nhiên do hệ điều hành cấp**, không phải một cổng cố định.
  Cổng cố định làm một trang web đoán được đích để bắn request; cổng đổi
  mỗi lần chạy thì nó phải quét, và token vẫn chặn.
* **Token đi qua URL rồi bị xoá khỏi URL ngay** bởi frontend
  (`history.replaceState`) — nên nó không nằm lại trong lịch sử trình
  duyệt hay trong `Referer`.

`--khong-mo` để chạy server mà không tự mở trình duyệt (dùng khi kiểm).
"""
from __future__ import annotations

import argparse
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# Console Windows mac dinh la cp1252, va MOI dong tep nay in ra deu la
# tieng Viet co dau. Khong tu bao ve thi `--check` do UnicodeEncodeError va
# THOAT 1 — nghia la cai cong kiem phu thuoc cua launcher bao "thieu goi"
# trong khi khong thieu gi.
#
# `router-cc-web.cmd` co dat PYTHONUTF8=1, nen duong bam doi khong bi. Nhung
# lenh `python -m scripts.control_center.webmain` (co trong tai lieu) thi
# bi — va do la lenh nguoi ta go khi go loi. Da vap dung loi nay o
# `fanfic-ctl.cmd` va `router-cc.cmd`; lan nay chan ngay tai nguon.
for _luong in (sys.stdout, sys.stderr):
    try:
        if _luong and (_luong.encoding or "").lower() != "utf-8":
            _luong.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                       # noqa: BLE001
        pass

#: Dia chi bind. HANG SO, va co bai kiem doi no la 127.0.0.1.
DIA_CHI = "127.0.0.1"


def cong_rong() -> int:
    """Xin hệ điều hành một cổng còn rỗi trên 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((DIA_CHI, 0))
        return int(s.getsockname()[1])


def _bao_thieu_goi(ten: str) -> None:
    """Thiếu phụ thuộc thì nói ĐÚNG câu lệnh cần chạy, ở cả hai đường.

    Cùng lý do như `gui/__main__.py`: launcher có thể được bấm đôi, và khi
    đó stderr không có ai đọc. Nên báo cả bằng hộp thoại của Windows.
    """
    loi = (f"Thiếu gói {ten!r} — chưa có phụ thuộc giao diện web.\n\n"
           "Cài đặt:\n"
           "    python -m pip install -r requirements-control-center-web.txt\n\n"
           "Hoặc dùng giao diện terminal:\n    router-cc")
    try:
        sys.stderr.write("control-center-web: " + loi + "\n")
    except Exception:                                       # noqa: BLE001
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, loi, "Router Control Center", 0x10)
        except Exception:                                   # noqa: BLE001
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="control-center-web",
        description="Router Control Center V0.2 — giao diện web cục bộ")
    ap.add_argument("--root", default="", help="thư mục gốc giữ sổ .router/")
    ap.add_argument("--project", default="", help="dự án mở sẵn")
    ap.add_argument("--port", type=int, default=0,
                    help="cổng (0 = xin hệ điều hành một cổng rỗng)")
    ap.add_argument("--max-parallel", type=int, default=3)
    ap.add_argument("--khong-mo", action="store_true",
                    help="không tự mở trình duyệt")
    ap.add_argument("--no-recover", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="chỉ kiểm phụ thuộc rồi thoát (0 = đủ, 2 = thiếu)")
    a = ap.parse_args(argv)

    if a.check:
        for ten in ("fastapi", "uvicorn"):
            try:
                __import__(ten)
            except ModuleNotFoundError:
                _bao_thieu_goi(ten)
                return 2
        print("phụ thuộc giao diện web: đủ")
        return 0

    try:
        import uvicorn
    except ModuleNotFoundError as exc:                      # pragma: no cover
        _bao_thieu_goi(str(exc.name or "uvicorn"))
        return 2

    from scripts.control_center.bootstrap import khoi_tao
    from scripts.control_center.engine import ControlCenter
    from scripts.control_center.webapi import PhienWeb, dung_app

    cong = a.port or cong_rong()
    token = secrets.token_urlsafe(32)
    goc = Path(a.root).resolve() if a.root else Path.cwd()
    cc = ControlCenter(root=goc, max_parallel=a.max_parallel)
    # `khoi_tao` GIEO du an mac dinh cua ban phat hanh (`fanfic`, `router`).
    #
    # Ban dau webmain dung `ControlCenter` truc tiep va BO QUA buoc nay, nen
    # mo giao dien web tren mot may moi ra mot sidebar RONG — khong du an
    # nao, va duong duy nhat vao la tu go duong dan kho. Hai launcher kia
    # (`__main__.py` cua TUI va cua Qt) deu goi `khoi_tao`; bo qua no o day
    # lam ba duong vao khong con giong nhau. Phat hien bang cach chup DOM
    # that bang Chrome cuc bo, khong bang bai kiem nao.
    khoi_tao(cc.store, root=goc)
    if not a.no_recover:
        try:
            cc.recover()
        except Exception as exc:                            # noqa: BLE001
            sys.stderr.write(f"phục hồi bỏ qua: {exc}\n")
    cc.start()

    phien = PhienWeb(cc, token=token, cong=cong)
    app = dung_app(phien)

    dia = f"http://{DIA_CHI}:{cong}"
    duong_day_du = f"{dia}/?t={token}"
    print("=" * 78)
    print("  Router Control Center — giao diện web")
    print(f"  {duong_day_du}")
    print("  (chỉ localhost · mọi request đòi token phiên)")
    print("=" * 78)
    # IN CA TOKEN, va co ly do: khong in thi voi `--khong-mo` KHONG CO CACH
    # NAO mo duoc giao dien, va neu nguoi dung dong tab thi ho mat luon
    # duong vao cho tan khi khoi dong lai server. Console nay la cua chinh
    # ho, tren may cua ho; token chi song trong mot lan chay.
    sys.stdout.flush()

    if not a.khong_mo:
        # Mo trinh duyet SAU khi server san sang. Doi mot nhip ngan thay vi
        # mo ngay: mo truoc khi uvicorn bind xong se cho ra mot trang loi
        # ket noi, va nguoi dung phai tu bam tai lai.
        duong = duong_day_du
        if a.project:
            duong += f"#project={a.project}"
        threading.Timer(0.8, lambda: webbrowser.open(duong)).start()

    try:
        uvicorn.run(app, host=DIA_CHI, port=cong, log_level="warning",
                    access_log=False)
    except KeyboardInterrupt:
        pass
    finally:
        cc.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
