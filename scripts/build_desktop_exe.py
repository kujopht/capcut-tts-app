"""Đóng gói `Router Control Center.exe` bằng PyInstaller.

MỘT TỆP hay MỘT THƯ MỤC? — **onedir**, và đây là lý do:

`--onefile` giải nén cả bộ vào `%TEMP%` mỗi lần chạy. Với gói này thì đó là
hàng chục MB mỗi lần mở, và tệ hơn: `CLAUDE.md` của kho ghi rõ Smart App
Control đang **bật cưỡng chế** trên máy này, nên một EXE tự giải nén rồi
chạy mã từ `%TEMP%` là đúng hình dạng mà Code Integrity hay chặn. `onedir`
mở nhanh và ít bị nghi hơn.

`--noconsole` (windowed): yêu cầu nghiệm thu là **không có cửa sổ terminal
nào**. Kèm theo đó là một nghĩa vụ: mọi lỗi khởi động phải báo bằng
`MessageBox`, vì `stderr` không còn ai đọc — `desktop.py` làm việc đó.

TÊN CÓ KHOẢNG TRẮNG (`Router Control Center.exe`) là cố ý: đó là tên người
dùng thấy trong Explorer. Nó cũng là lý do mọi chỗ gọi EXE này trong tài
liệu và kịch bản đều phải bọc dấu ngoặc kép.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC) not in sys.path:
    sys.path.insert(0, str(GOC))

from scripts.control_center.ghi_utf8 import GhiUTF8  # noqa: E402

TEN = "Router Control Center"

#: KHONG `print()`. Mọi câu kịch bản này in ra là tiếng Việt, và `print()`
#: giao chuỗi cho tầng VĂN BẢN của luồng — codec do locale quyết định,
#: cp1252 trên máy này. Đúng luật ở `docs/CONTROL_CENTER.md` §14, và
#: không phải giả thuyết: dòng `cỡ : …` (chữ **ỡ**, U+1EE1) nổ
#: `UnicodeEncodeError` NGAY SAU khi build xong, tức là làm mất báo cáo
#: của một lần dựng mất vài phút.
ghi = GhiUTF8()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true",
                    help="xoá build/ và dist/ trước khi dựng")
    # VI SAO CAN CO: mot ban dang CHAY khoa chinh thu muc cua no —
    # `Router Control Center.exe` khong ghi de duoc khi con song, va
    # `.router/control_center/control.db` bi giu boi tien trinh do. Nen
    # "dung lai ban moi de kiem" va "giu ban nguoi dung dang mo" la hai
    # viec khong the dung chung mot thu muc. Truoc day khong co co nay,
    # nen cach duy nhat la tat ung dung cua nguoi khac.
    ap.add_argument("--dist", default="",
                    help=("thư mục đích (mặc định `dist/`). Dùng khi bản "
                          "hiện tại đang chạy và giữ khoá thư mục của nó"))
    a = ap.parse_args(argv)

    try:
        import PyInstaller                                  # noqa: F401
    except ModuleNotFoundError:
        ghi(
            "thiếu pyinstaller — cài: python -m pip install -r "
            "requirements-control-center-desktop.txt\n")
        return 2

    ra = Path(a.dist).resolve() if a.dist else (GOC / "dist")
    lam = GOC / "build" / ("desktop" if not a.dist else f"desktop-{ra.name}")
    if a.clean:
        shutil.rmtree(ra / TEN, ignore_errors=True)
        shutil.rmtree(lam, ignore_errors=True)

    lenh = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--name", TEN,
        "--noconsole",                  # KHONG cua so terminal
        "--onedir",                     # xem docstring
        "--distpath", str(ra),
        "--workpath", str(lam),
        "--specpath", str(lam),
        # Frontend la tep TINH — phai di theo goi, khong phai import.
        "--add-data", f"{GOC / 'scripts' / 'control_center' / 'web'}"
                      f";scripts/control_center/web",
        # CAU HINH FABRIC cua Router V4. PyInstaller chi goi module Python;
        # tep du lieu phai khai tuong minh.
        #
        # Thieu no thi EXE build XONG, mo duoc, nap giao dien duoc, tai
        # dinh kem duoc — roi CHET dung luc nguoi dung gui viec dau tien:
        #
        #   FileNotFoundError: thieu _internal/scripts/router_v4/
        #   config/fabric.json
        #
        # Do la loai loi khong the thay tu ma nguon: chay `python -m` thi
        # tep nam san canh module. Chi lo ra khi chay EXE THAT va lam dung
        # thao tac cham vao no.
        "--add-data", f"{GOC / 'scripts' / 'router_v4' / 'config'}"
                      f";scripts/router_v4/config",
        # V0.5: cau hinh QUAN SAT SONG. Cung ly do voi `fabric.json` —
        # PyInstaller chi goi module Python, tep du lieu phai khai tuong
        # minh. Thieu no thi ban EXE chay duoc, nhung moi du an mat
        # probe rieng va chi con quan sat chung; loi do KHONG the thay
        # tu ma nguon, vi chay `python -m` thi tep nam san canh module.
        "--add-data", f"{GOC / 'scripts' / 'control_center' / 'config'}"
                      f";scripts/control_center/config",
        "--add-data",
        f"{GOC / 'scripts' / 'router_v3' / 'control_room' / 'PROOF_SCREEN.txt'}"
        f";scripts/router_v3/control_room",
        # `uvicorn` nap cac lop nay bang ten chuoi luc chay, nen PyInstaller
        # khong thay chung khi quet import. Thieu chung thi EXE build xong
        # roi CHET LUC MO — dung loai loi chi lo ra sau khi dong goi.
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.loops.asyncio",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.http.h11_impl",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.protocols.websockets.websockets_impl",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "uvicorn.lifespan.off",
        # pywebview chon backend luc chay theo cung mot cach.
        "--hidden-import", "webview.platforms.edgechromium",
        "--collect-all", "webview",
        # Khong keo theo nhung thu goi nay khong dung. PySide6 nang ~150 MB
        # va vo desktop nay khong can mot dong Qt nao.
        "--exclude-module", "PySide6",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "textual",
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        str(GOC / "scripts" / "control_center" / "desktop.py"),
    ]
    ghi("  " + " ".join(f'"{x}"' if " " in x else x for x in lenh))
    r = subprocess.run(lenh, cwd=str(GOC))
    if r.returncode != 0:
        return r.returncode

    exe = ra / TEN / f"{TEN}.exe"
    if not exe.is_file():
        ghi(f"build xong nhưng không thấy {exe}")
        return 3
    co = exe.stat().st_size
    tong = sum(p.stat().st_size for p in (ra / TEN).rglob("*") if p.is_file())
    ghi("")
    ghi(f"  EXE  : {exe}")
    ghi(f"  cỡ   : {co:,} byte (thư mục: {tong / 1048576:.0f} MB)")
    ghi("")
    ghi("  Bấm đôi tệp EXE ở trên. Không cần console, không cần trình duyệt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
