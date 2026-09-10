# -*- coding: utf-8 -*-
"""Ký Authenticode một bản đóng gói — vỏ mỏng quanh `signtool`, KHÔNG giữ bí mật.

    # Artifact Signing (Microsoft, trước là Trusted Signing) — khoá nằm trong HSM
    # của dịch vụ, máy này chỉ có dlib + metadata.json (không có khoá riêng):
    python scripts/ky_ban_dong_goi.py dist-v061 --artifact-signing \\
        --dlib "C:\\tools\\Microsoft.Trusted.Signing.Client\\bin\\x64\\Azure.CodeSigning.Dlib.dll" \\
        --metadata "C:\\tools\\metadata.json" [--dry-run]

    # Chứng chỉ ký mã của CA công cộng đã cài trong kho CurrentUser\\My (khoá riêng
    # nằm trên token/HSM theo yêu cầu CA/B Forum từ 6/2023) — tham chiếu bằng VÂN TAY:
    python scripts/ky_ban_dong_goi.py dist-v061 --thumbprint <sha1> [--dry-run]

Sau khi ký, tự gọi `kiem_ban_dong_goi` để in trạng thái chữ ký/người ký/SHA256
và dự đoán Smart App Control. `--dry-run` chỉ in lệnh sẽ chạy.

VÌ SAO KHÔNG có đường "tự ký": Smart App Control chỉ tin chứng chỉ do CA trong
Microsoft Trusted Root Program cấp (tài liệu Microsoft, xem
`docs/reports/SMART_APP_CONTROL_V061.md` §4). Một chứng chỉ tự ký — kể cả khi
đã cài gốc vào Trusted Root của máy — không đổi được quyết định của SAC, chỉ
đổi cái hộp thoại "publisher" của SmartScreen. Thêm đường đó vào đây là mời
người sau tin nhầm.

Luật: không nhận `--pfx`/mật khẩu; không đọc, không sao chép, không in khoá
riêng; mọi thứ đi qua `signtool` của Windows SDK.
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

GOC = Path(__file__).resolve().parents[1]
TEN_THU_MUC = "Router Control Center"
TEN_EXE = "Router Control Center.exe"
#: Máy chủ dấu thời gian RFC3161 (bắt buộc — không có thì chữ ký chết cùng chứng chỉ).
TIMESTAMP_MAC_DINH = "http://timestamp.acs.microsoft.com"


def tim_signtool() -> Optional[str]:
    """`signtool.exe` của Windows SDK — bản x64 mới nhất, hoặc trên PATH."""
    tren_path = shutil.which("signtool")
    if tren_path:
        return tren_path
    goc_kit = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    ung = sorted(glob.glob(os.path.join(goc_kit, "Windows Kits", "10", "bin", "*", "x64", "signtool.exe")))
    return ung[-1] if ung else None


def tim_exe(muc: Path) -> Path:
    if muc.is_file():
        return muc
    for u in (muc / TEN_THU_MUC / TEN_EXE, muc / TEN_EXE):
        if u.is_file():
            return u
    raise FileNotFoundError(f"không thấy EXE trong {muc}")


def lenh_ky(signtool: str, exe: Path, *, thumbprint: str = "", dlib: str = "",
            metadata: str = "", timestamp: str = TIMESTAMP_MAC_DINH,
            mo_ta: str = "Router Control Center") -> List[str]:
    """Soạn lệnh `signtool sign`. Không có nhánh nào nhận khoá riêng."""
    lenh = [signtool, "sign", "/v", "/fd", "SHA256", "/tr", timestamp, "/td", "SHA256",
            "/d", mo_ta]
    if dlib or metadata:
        if not (dlib and metadata):
            raise ValueError("Artifact Signing cần CẢ --dlib và --metadata")
        lenh += ["/dlib", dlib, "/dmdf", metadata]
    elif thumbprint:
        tp = thumbprint.replace(" ", "").lower()
        if len(tp) != 40 or any(c not in "0123456789abcdef" for c in tp):
            raise ValueError("--thumbprint phải là 40 ký tự hex (SHA1 của chứng chỉ)")
        lenh += ["/sha1", tp]
    else:
        raise ValueError("chọn --artifact-signing (--dlib + --metadata) hoặc --thumbprint")
    lenh.append(str(exe))
    return lenh


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("muc", help="thư mục dist hoặc đường dẫn EXE")
    ap.add_argument("--artifact-signing", action="store_true",
                    help="ký qua Microsoft Artifact Signing (cần --dlib và --metadata)")
    ap.add_argument("--dlib", default="", help="đường dẫn Azure.CodeSigning.Dlib.dll")
    ap.add_argument("--metadata", default="", help="metadata.json (Endpoint, CodeSigningAccountName, CertificateProfileName)")
    ap.add_argument("--thumbprint", default="", help="SHA1 chứng chỉ ký mã trong kho CurrentUser\\My")
    ap.add_argument("--timestamp", default=TIMESTAMP_MAC_DINH)
    ap.add_argument("--signtool", default="", help="đường dẫn signtool.exe (mặc định: tự tìm)")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in lệnh, không ký")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                   # noqa: BLE001
            pass
    try:
        exe = tim_exe(Path(a.muc))
    except FileNotFoundError as exc:
        print(f"!! {exc}")
        return 2
    signtool = a.signtool or tim_signtool() or "signtool.exe"
    try:
        lenh = lenh_ky(signtool, exe, thumbprint=a.thumbprint, dlib=a.dlib,
                       metadata=a.metadata, timestamp=a.timestamp)
    except ValueError as exc:
        print(f"!! {exc}")
        return 2
    print("lệnh: " + " ".join(f'"{x}"' if " " in x else x for x in lenh))
    if a.dry_run:
        print("(dry-run — không ký)")
        return 0
    if not Path(signtool).is_file() and not shutil.which(signtool):
        print("!! không thấy signtool.exe — cài Windows SDK (Signing Tools) hoặc truyền --signtool")
        return 2
    r = subprocess.run(lenh, cwd=str(GOC))
    if r.returncode != 0:
        print(f"!! signtool trả {r.returncode}")
        return r.returncode
    # Bao cao sau ky: chu ky/nguoi ky/SHA256/du doan SAC.
    sys.path.insert(0, str(GOC))
    from scripts.kiem_ban_dong_goi import dong_bao_cao, kiem_exe
    print(dong_bao_cao(kiem_exe(exe)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
