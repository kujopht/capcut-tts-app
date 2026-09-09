"""Cấu hình quan sát KHAI BÁO, và phép kiểm nó.

BÍ MẬT KHÔNG NẰM Ở ĐÂY. Cấu hình chỉ giữ **bí danh/đường dẫn** tới khoá
đã có sẵn trên máy (`key_path`), không bao giờ nội dung khoá, mật khẩu
hay token. `kiem_cau_hinh()` từ chối một tệp cấu hình mang thứ trông như
bí mật — vì tệp này nằm trong kho git, và một khoá riêng lọt vào đây là
một sự cố không hoàn tác được bằng một lần commit.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

GOC_GOI = Path(__file__).resolve().parents[1]
DUONG_MAC_DINH = GOC_GOI / "config" / "observability.json"

#: Loai provider duoc phep khai trong cau hinh. Fail closed: mot loai la
#: bi tu choi thay vi bo qua am tham.
LOAI_HOP_LE = {"router", "git", "ssh_service", "unavailable"}

#: Khoa CAM xuat hien trong cau hinh — day la noi de LOT mot bi mat vao
#: kho git.
KHOA_CAM = ("private_key", "key", "secret", "password", "passphrase",
            "token", "api_key", "credential", "credentials")

#: Chu ky noi dung khoa rieng / token. Neu thay -> tu choi ca tep.
_MAU_BI_MAT = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bghp_[0-9A-Za-z]{20,}\b"),
    re.compile(r"\bsk-[0-9A-Za-z]{20,}\b"),
)


class CauHinhLoi(ValueError):
    pass


def kiem_cau_hinh(d: Any) -> Dict:
    """Trả về cấu hình đã kiểm, hoặc ném `CauHinhLoi`."""
    if not isinstance(d, dict):
        raise CauHinhLoi("cấu hình phải là một object")
    tho = json.dumps(d, ensure_ascii=False)
    for r in _MAU_BI_MAT:
        if r.search(tho):
            raise CauHinhLoi(
                "cấu hình chứa thứ trông như NỘI DUNG bí mật — chỉ được "
                "khai đường dẫn/bí danh, không bao giờ nội dung")
    ds = d.get("projects")
    if not isinstance(ds, dict):
        raise CauHinhLoi("thiếu `projects` (object theo project_id)")
    for pid, c in ds.items():
        if not isinstance(c, dict):
            raise CauHinhLoi(f"{pid}: phải là object")
        prov = c.get("providers")
        if not isinstance(prov, list) or not prov:
            raise CauHinhLoi(f"{pid}: `providers` phải là danh sách khác rỗng")
        for i, p in enumerate(prov):
            if not isinstance(p, dict):
                raise CauHinhLoi(f"{pid}.providers[{i}]: phải là object")
            loai = p.get("type")
            if loai not in LOAI_HOP_LE:
                raise CauHinhLoi(
                    f"{pid}.providers[{i}]: `type`={loai!r} không hợp lệ "
                    f"(cho phép: {sorted(LOAI_HOP_LE)})")
            for k in p:
                if k.lower() in KHOA_CAM and k.lower() != "key_path":
                    raise CauHinhLoi(
                        f"{pid}.providers[{i}]: khoá {k!r} bị cấm — dùng "
                        f"`key_path` trỏ tới khoá đã có trên máy")
            if loai == "ssh_service":
                for k in ("id", "host", "unit"):
                    if not p.get(k):
                        raise CauHinhLoi(
                            f"{pid}.providers[{i}]: `ssh_service` thiếu {k!r}")
                kp = p.get("key_path")
                if kp and not isinstance(kp, str):
                    raise CauHinhLoi(
                        f"{pid}.providers[{i}]: `key_path` phải là chuỗi")
            if loai == "unavailable":
                for k in ("id", "reason"):
                    if not p.get(k):
                        raise CauHinhLoi(
                            f"{pid}.providers[{i}]: `unavailable` thiếu {k!r}")
    return d


def nap(duong: Optional[Path] = None) -> Dict:
    """Nạp cấu hình. Thiếu tệp KHÔNG phải lỗi — trả cấu hình rỗng.

    Một kho chưa khai gì thì mọi dự án dùng `GenericProjectProvider`, và
    đó là hành vi đúng: quan sát chung vẫn chạy, chỉ không có probe riêng.
    """
    p = Path(duong) if duong else DUONG_MAC_DINH
    if not p.is_file():
        return {"projects": {}}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CauHinhLoi(f"không đọc được {p}: {exc}") from exc
    return kiem_cau_hinh(d)


def duong_khoa_ton_tai(duong: str) -> bool:
    if not duong:
        return False
    return Path(os.path.expandvars(os.path.expanduser(duong))).is_file()
