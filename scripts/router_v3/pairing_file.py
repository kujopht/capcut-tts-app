"""Tệp ghép một-lần trên đĩa dùng chung — Router V3.2, Phase 5.

VÌ SAO: gõ tay cổng+token qua getpass đã sai nhiều lần trong thực tế (chép
nhầm, gõ nhầm khi ẩn ký tự). Bên AG02 và Router đã cùng một hệ thống tệp
dùng chung có ACL siết sẵn (`C:\\FanficWorkers`, xem `setup_shared_root.py`)
— tệp là cách trao token không qua tay người, không qua model context.

TỆP CHỈ CHỨA ĐÚNG BA TRƯỜNG: `worker_id`, `port`, `token`. Không có gì khác
— không lịch sử, không đường dẫn worktree, không credential nhà cung cấp.

QUYỀN: thư mục cha (`C:\\FanficWorkers\\pairing`) đã kế thừa ACL ít quyền
nhất từ gốc dùng chung — chỉ tài khoản Router chính và các worker được liệt
kê khi cấp phát mới đọc được, không `Everyone`/`Users`. Module này KHÔNG tự
suy ra ACL: nó tin thư mục cha đã đúng (do `setup_shared_root.py` cấp phát),
và chỉ phòng hờ bằng cách không nới quyền tệp rộng hơn thư mục cha.

XOÁ AN TOÀN: một lần dùng xong, ghi đè nội dung bằng byte ngẫu nhiên TRƯỚC
khi xoá — xoá thường chỉ bỏ mục lục, nội dung có thể còn phục hồi được.
Không phải xoá cấp quân sự nhiều lượt; token là bí mật ứng dụng ngắn hạn, tự
vô hiệu khi cầu nối dừng — mức này tương xứng.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional, TypedDict


class PairingRecord(TypedDict):
    worker_id: str
    port: int
    token: str


def write(path: Path, *, worker_id: str, port: int, token: str) -> None:
    """Ghi tệp ghép. Thư mục cha PHẢI đã tồn tại với ACL đúng — không tự tạo
    thư mục ở đây, vì tạo mới sẽ kế thừa ACL của NƠI GỌI TỪ ĐÓ (tài khoản
    AG0x), không phải ACL đã cấp phát sẵn cho gốc dùng chung."""
    if not path.parent.is_dir():
        raise FileNotFoundError(
            f"{path.parent} chưa tồn tại — cấp phát bằng setup_shared_root.py "
            f"trước, đừng để tệp ghép tự tạo thư mục với ACL không kiểm soát.")
    du_lieu: PairingRecord = {"worker_id": worker_id, "port": port, "token": token}
    path.write_text(json.dumps(du_lieu), encoding="utf-8")


def read(path: Path) -> Optional[PairingRecord]:
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(d, dict):
        return None
    if not all(k in d for k in ("worker_id", "port", "token")):
        return None
    return {"worker_id": str(d["worker_id"]), "port": int(d["port"]),
           "token": str(d["token"])}


def secure_delete(path: Path) -> bool:
    """Ghi đè rồi xoá. Trả về False nếu tệp không tồn tại — không phải lỗi,
    có thể một tiến trình khác đã dọn trước."""
    if not path.exists():
        return False
    try:
        kich_thuoc = path.stat().st_size
        with open(path, "r+b") as f:
            f.write(secrets.token_bytes(kich_thuoc))
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass  # ghi de la phong ho them; xoa duoi day van phai chay
    path.unlink(missing_ok=True)
    return True
