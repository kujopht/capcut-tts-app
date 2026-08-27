#!/usr/bin/env python3
"""
Bo kiem tra hang doi tai nguyen NHE cho AI Engineering Router V2 (xem
`docs/AI_ROUTER.md`) — goi THU CONG o dau mot phien lam viec lon hoac o
ranh gioi giua cac Phase, KHONG polling lien tuc (xem "Phase 15 — Quota
balancer" trong tai lieu). Khong phai dich vu nen, khong luu trang thai.

THUC TE TUNG nha cung cap co the kiem tra duoc (khong gia dinh):
- ANTIGRAVITY: co that qua `agy --print "/usage"` va `/credits` — hai hang
  doi rieng (Gemini Models / Claude and GPT models), phan tram con lai +
  thoi diem reset, cong voi so du AI-credit tra phi con lai (phai bang 0
  hoac khong tang bat ngo — xem `check_antigravity_paid_overage_safe`).
- CODEX: KHONG co lenh usage/quota/limit rieng trong CLI nay — tin hieu
  duy nhat quan sat duoc la `codex login status` (con dang nhap hay
  khong). Ghi ro day la GIOI HAN THAT, khong gia lap mot con so khong co
  that.
- CLAUDE: KHONG co lenh CLI nao lo ra usage/quota. Ap luc phai SUY RA tu
  phan hoi rate-limit/cham lai thuc te trong phien, khong the truy van
  truc tiep.

KHONG in/log bat ky secret/token nao — chi in trang thai/phan tram/ten
model, dung nguyen tac giong `ai_router_telemetry.py`.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from typing import Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _tim_agy() -> Optional[str]:
    tu_path = shutil.which("agy") or shutil.which("agy.exe")
    if tu_path:
        return tu_path
    ung_vien = os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")
    return ung_vien if os.path.isfile(ung_vien) else None


def _tim_codex() -> Optional[str]:
    tu_path = shutil.which("codex") or shutil.which("codex.exe")
    if tu_path:
        return tu_path
    # Cai qua Codex desktop app: duong dan co mot doan hash thay doi theo
    # ban cap nhat — do tim dong thay vi gia dinh co dinh (xem ghi chu
    # trong docs/AI_ROUTER.md).
    mau = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe")
    ung_vien = sorted(glob.glob(mau))
    return ung_vien[-1] if ung_vien else None


def _chay(duong_dan_binary: str, *args: str, timeout: int = 30) -> str:
    try:
        ket_qua = subprocess.run(
            [duong_dan_binary, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout)
        return (ket_qua.stdout or "") + (ket_qua.stderr or "")
    except Exception as exc:  # noqa: BLE001 - day la cong cu chan doan, muon thay loi ro
        return f"<lỗi khi gọi {os.path.basename(duong_dan_binary)}: {exc}>"


def check_antigravity() -> dict:
    agy = _tim_agy()
    if not agy:
        return {"cai_dat": False}
    usage_raw = _chay(agy, "--print", "/usage", "--output-format", "text", "--print-timeout", "30s")
    credits_raw = _chay(agy, "--print", "/credits", "--output-format", "text", "--print-timeout", "30s")
    return {"cai_dat": True, "usage_raw": usage_raw.strip(), "credits_raw": credits_raw.strip()}


def check_antigravity_paid_overage_safe(credits_raw: str) -> Optional[bool]:
    """`True` neu tim thay dong 'Remaining credits' va no la 0 (an toan —
    khong co gi de tieu du useG1Credits co bat ngo bi bat). `None` neu
    khong doc duoc dong nay (khong ket luan, KHONG gia dinh an toan)."""
    for dong in credits_raw.splitlines():
        if "remaining credits" in dong.lower():
            phan = dong.split("\t") if "\t" in dong else dong.split()
            for muc in reversed(phan):
                if muc.strip().isdigit():
                    return int(muc.strip()) == 0
    return None


def check_codex() -> dict:
    codex = _tim_codex()
    if not codex:
        return {"cai_dat": False}
    trang_thai = _chay(codex, "login", "status", timeout=20).strip()
    return {
        "cai_dat": True,
        "trang_thai_dang_nhap": trang_thai,
        "luu_y": "Codex CLI không có lệnh usage/quota riêng — đây là tín hiệu DUY NHẤT quan sát được.",
    }


def check_claude() -> dict:
    return {
        "luu_y": "Claude Code CLI không lộ ra lệnh usage/quota — áp lực hạn mức "
                 "phải SUY RA từ phản hồi rate-limit/chậm lại thực tế trong phiên, "
                 "không tra vấn trực tiếp được.",
    }


def main() -> int:
    ket_qua = {
        "antigravity": check_antigravity(),
        "codex": check_codex(),
        "claude": check_claude(),
    }
    if ket_qua["antigravity"].get("cai_dat"):
        an_toan = check_antigravity_paid_overage_safe(ket_qua["antigravity"]["credits_raw"])
        ket_qua["antigravity"]["paid_overage_risk_zero"] = an_toan
    print(json.dumps(ket_qua, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
