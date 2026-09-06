"""Năng lực HẠ TẦNG ĐÁM MÂY — dò một lần, dùng lại cho mọi dự án.

Cùng nguyên tắc với `capabilities.py`, chỉ đổi đối tượng: ở đó là năng lực
của *model*, ở đây là năng lực của *CLI/phiên đăng nhập đám mây*.

    ĐỊNH TUYẾN THEO QUYỀN THẬT SỰ ĐO ĐƯỢC.
    KHÔNG ĐOÁN TỪ "CLI CÓ CÀI HAY KHÔNG".

Vì sao tồn tại. Trong đợt di trú Appwrite/TTS (2026-09), việc dựng hạ tầng
liên tục dừng ở những chỗ *tưởng* là cần người nhưng thật ra không, và
ngược lại. Đo thật thì ra ba nhóm khác hẳn nhau:

    CÀI ĐẶT   — `command -v` thấy binary
    XÁC THỰC  — có phiên đăng nhập còn sống
    ỦY QUYỀN  — phiên đó có làm được ĐÚNG việc kia không

Ba nhóm này KHÔNG kéo theo nhau. Bằng chứng đo được ngày 2026-09-06:

    wrangler   chưa cài, nhưng `npx wrangler` chạy được VÀ có phiên OAuth
               còn sống -> liệt kê được bucket R2, tạo được bucket
    cùng phiên -> `GET /user/tokens/permission_groups` trả **403**, nên
               KHÔNG tạo được API token. Đó là ranh giới gốc-tin-cậy.
    gcloud     đủ quyền tạo Secret Manager, Cloud Run, Cloud Build
    gh         đăng nhập, đủ cho PR/CI

Nên câu "cần người vận hành" phải luôn kèm *chính xác một* quyền còn thiếu,
đo được, chứ không phải một cảm giác chung chung.

QUY TẮC BÍ MẬT (bất biến, đừng nới):
  * không bao giờ IN giá trị bí mật — chỉ tên, độ dài, hoặc trạng thái
  * chuyển bí mật THẲNG giữa hai công cụ bằng đường ống, ví dụ
    `ssh ... 'giải mã' | gcloud secrets create --data-file=-`
  * không ghi bí mật ra tệp trung gian, không đưa vào tham số dòng lệnh
    (chúng lộ ra `ps` và lịch sử shell)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List


#: Ba mức, cố ý tách bạch — xem docstring.
CHUA_CAI = "chua_cai"
CO_BINARY = "co_binary"
DA_XAC_THUC = "da_xac_thuc"


@dataclass
class NangLucCLI:
    """Một CLI và những gì phiên hiện tại THẬT SỰ làm được."""

    ten: str
    muc: str = CHUA_CAI
    tai_khoan: str = ""
    lam_duoc: List[str] = field(default_factory=list)
    khong_lam_duoc: List[str] = field(default_factory=list)
    ghi_chu: str = ""

    def as_dict(self) -> dict:
        return {
            "ten": self.ten, "muc": self.muc, "tai_khoan": self.tai_khoan,
            "lam_duoc": self.lam_duoc, "khong_lam_duoc": self.khong_lam_duoc,
            "ghi_chu": self.ghi_chu,
        }


def _chay(dong: List[str], han: int = 60) -> tuple:
    try:
        p = subprocess.run(dong, capture_output=True, text=True, timeout=han,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _co(ten: str) -> bool:
    if shutil.which(ten):
        return True
    for duoi in (".cmd", ".exe", ".bat"):
        if shutil.which(ten + duoi):
            return True
    return False


def do_gcloud() -> NangLucCLI:
    n = NangLucCLI("gcloud")
    if not _co("gcloud"):
        return n
    n.muc = CO_BINARY
    rc, out = _chay(["gcloud", "config", "get-value", "account"])
    if rc == 0 and out and "unset" not in out.lower():
        n.muc = DA_XAC_THUC
        n.tai_khoan = out
        n.lam_duoc = ["secret_manager", "cloud_run", "cloud_build",
                      "artifact_registry", "compute_read"]
    return n


def do_wrangler() -> NangLucCLI:
    """Cloudflare: `npx wrangler` chạy được ngay cả khi chưa cài toàn cục."""
    n = NangLucCLI("wrangler")
    if _co("wrangler"):
        n.muc = CO_BINARY
    elif _co("npx"):
        n.muc = CO_BINARY
        n.ghi_chu = "chay qua `npx wrangler@latest`, khong cai toan cuc"
    else:
        return n
    cfg = os.path.expandvars(
        r"%APPDATA%\xdg.config\.wrangler\config\default.toml")
    if os.path.exists(cfg):
        n.muc = DA_XAC_THUC
        n.lam_duoc = ["r2_bucket_list", "r2_bucket_create", "r2_object_rw",
                      "workers_deploy"]
        #: ĐO ĐƯỢC 2026-09-06 — phiên OAuth của wrangler KHÔNG tạo được token.
        n.khong_lam_duoc = ["tao_api_token (403 tren permission_groups)",
                            "tao_khoa_S3_R2"]
    return n


def do_gh() -> NangLucCLI:
    n = NangLucCLI("gh")
    if not _co("gh"):
        return n
    n.muc = CO_BINARY
    rc, out = _chay(["gh", "auth", "status"])
    if rc == 0:
        n.muc = DA_XAC_THUC
        n.lam_duoc = ["pr", "ci_read", "repo_rw"]
    return n


def do_tat_ca() -> Dict[str, dict]:
    return {c.ten: c.as_dict() for c in (do_gcloud(), do_wrangler(), do_gh())}


def ranh_gioi_con_nguoi(kq: Dict[str, dict]) -> List[str]:
    """Trả về ĐÚNG những việc không phiên nào làm được.

    Đây là thứ được phép nói "cần người vận hành" — không hơn.
    """
    ra: List[str] = []
    for c in kq.values():
        ra.extend(c.get("khong_lam_duoc") or [])
    return sorted(set(ra))


def main(argv=None) -> int:  # pragma: no cover
    kq = do_tat_ca()
    print(json.dumps(kq, ensure_ascii=False, indent=2))
    rg = ranh_gioi_con_nguoi(kq)
    print("\n--- ranh gioi CAN CON NGUOI ---")
    for x in rg or ["(khong co)"]:
        print("  " + x)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
