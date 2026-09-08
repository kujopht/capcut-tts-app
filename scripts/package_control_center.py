"""Đóng gói Router Control Center V0.1 — một tệp zip chạy được.

KHÔNG phải một trình cài đặt, và cố ý không phải: Control Center chạy bằng
Python có sẵn của kho, dùng chung `requirements-control-room.txt` với Control
Room. Thứ người dùng cần là một hiện vật CÓ PHIÊN BẢN, CÓ BĂM, mở ra chạy
được ngay — không phải một EXE cần ký số (xem `CLAUDE.md`: Smart App Control
đang bật, EXE chưa ký bị Code Integrity chặn).

GÓI GỒM ĐÚNG NHỮNG GÌ CẦN ĐỂ CHẠY, không hơn:

    scripts/control_center/**     bộ máy + giao diện
    scripts/router_v3/**          worktree, adapter, cổng kiểm định
    scripts/router_v4/**          fabric, scheduler, executor, lease
    scripts/cc_agent_tool.py      công cụ động từ hữu hạn cho agent
    scripts/__init__.py
    router-cc-gui(.cmd)           lối vào GIAO DIỆN ĐỒ HOẠ (đường chính)
    router-cc, router-cc.cmd      lối vào TUI (dự phòng/gỡ lỗi)
    requirements-control-center-gui.txt  phụ thuộc GUI (chỉ PySide6)
    requirements-control-room.txt phụ thuộc TUI (textual, rich)
    docs/CONTROL_CENTER.md        tài liệu
    MANIFEST.txt                  băm SHA-256 của TỪNG tệp trong gói

KHÔNG BAO GIỜ ĐÓNG GÓI: `.router/` (sổ, worktree, nhật ký — chứa dữ liệu vận
hành thật), `.git/`, `.env`, `__pycache__`, hay bất kỳ tệp nào khớp mẫu bí
mật. Có một cổng quét TRƯỚC khi ghi zip: thấy thứ giống credential thì DỪNG,
không đóng gói.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parents[1]
VERSION = "0.1.2"

#: Cay tep dua vao goi. Thu tu khong quan trong; noi dung thi co.
GOM: Tuple[str, ...] = (
    "scripts/__init__.py",
    "scripts/cc_agent_tool.py",
    "scripts/control_center",
    "scripts/router_v3",
    "scripts/router_v4",
    "router-cc",
    "router-cc.cmd",
    # V0.1.1: loi vao GIAO DIEN DO HOA. `scripts/control_center` o tren da
    # keo theo ca `gui/` (no la mot thu muc), nhung hai tep loi vao va tep
    # phu thuoc nam o goc kho nen phai liet ke rieng — thieu chung thi goi
    # van "chay duoc" bang TUI va khong ai phat hien duong chinh bi mat.
    "router-cc-gui",
    "router-cc-gui.cmd",
    "requirements-control-room.txt",
    "requirements-control-center-gui.txt",
    "docs/CONTROL_CENTER.md",
)

#: KHONG BAO GIO vao goi, du nam duoi mot muc o `GOM`.
LOAI: Tuple[str, ...] = (
    "__pycache__", ".pyc", ".router", ".git", ".env", ".venv",
    "conversation", "credential", "saved_profiles",
)

#: Mau giong bi mat. Thay mot cai la DUNG — khong doan, khong "chac la mau".
BI_MAT = (
    re.compile(rb"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"\bAIza[0-9A-Za-z\-_]{35}"),
    re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(rb"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\."),
)


class GoiHong(RuntimeError):
    pass


def _nen_bo(p: Path) -> bool:
    s = str(p).replace("\\", "/")
    return any(x in s for x in LOAI)


def thu_thap() -> List[Path]:
    ra: List[Path] = []
    for muc in GOM:
        goc = REPO / muc
        if not goc.exists():
            raise GoiHong(f"thiếu {muc} — gói sẽ không chạy được")
        if goc.is_file():
            if not _nen_bo(goc):
                ra.append(goc)
            continue
        for p in sorted(goc.rglob("*")):
            if p.is_file() and not _nen_bo(p):
                ra.append(p)
    return sorted(set(ra))


def quet_bi_mat(tep: List[Path]) -> None:
    """Cổng cuối trước khi ghi zip. FAIL CLOSED.

    Một gói là thứ được sao chép, gửi đi, giải nén ở máy khác. Nếu có một
    credential lọt vào, nó đi xa hơn nhiều so với một dòng log.
    """
    dinh: List[str] = []
    for p in tep:
        try:
            b = p.read_bytes()
        except OSError as exc:
            raise GoiHong(f"không đọc được {p}: {exc}") from exc
        for mau in BI_MAT:
            if mau.search(b):
                dinh.append(str(p.relative_to(REPO)).replace("\\", "/"))
                break
    if dinh:
        raise GoiHong(
            "DỪNG ĐÓNG GÓI: thấy chuỗi giống credential trong "
            + ", ".join(dinh[:5])
            + ". Không đóng gói cho tới khi việc này được làm rõ.")


def bam(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def dong_goi(ra_thu_muc: Path) -> Tuple[Path, str, int]:
    tep = thu_thap()
    quet_bi_mat(tep)

    ra_thu_muc.mkdir(parents=True, exist_ok=True)
    dich = ra_thu_muc / f"router-control-center-v{VERSION}.zip"

    dong_manifest = [
        f"Router Control Center v{VERSION}",
        "",
        "GIAO DIEN DO HOA (duong chinh):",
        "  python -m pip install -r requirements-control-center-gui.txt",
        "  router-cc-gui.cmd        # bam doi duoc tu Explorer",
        "  ./router-cc-gui          # hoac tu dong lenh",
        "",
        "GIAO DIEN TERMINAL (du phong / go loi):",
        "  python -m pip install -r requirements-control-room.txt",
        "  ./router-cc              # giao dien Textual",
        "  ./router-cc --headless   # anh chup JSON, khong can TTY",
        "",
        "Ca hai dung CHUNG mot so SQLite, nen mo canh nhau van thay cung",
        "du an/viec/phien.",
        "",
        "SHA-256 cua tung tep:",
    ]
    for p in tep:
        rel = str(p.relative_to(REPO)).replace("\\", "/")
        dong_manifest.append(f"  {bam(p)}  {rel}")
    manifest = "\n".join(dong_manifest) + "\n"

    with zipfile.ZipFile(dich, "w", zipfile.ZIP_DEFLATED) as z:
        for p in tep:
            z.write(p, str(p.relative_to(REPO)).replace("\\", "/"))
        z.writestr("MANIFEST.txt", manifest)

    return dich, bam(dich), len(tep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đóng gói Control Center V0.1")
    ap.add_argument("--out", default=str(REPO / "dist"),
                    help="thư mục xuất (mặc định: <kho>/dist)")
    a = ap.parse_args(argv)
    try:
        dich, sha, n = dong_goi(Path(a.out).resolve())
    except GoiHong as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    print(f"gói   : {dich}")
    print(f"tệp   : {n}")
    print(f"kích cỡ: {dich.stat().st_size:,} bytes")
    print(f"sha256: {sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
