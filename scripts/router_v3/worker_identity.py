"""Danh tính cầu nối ỔN ĐỊNH qua nhiều lần khởi động lại — Router LTS Phase 6.

VÌ SAO: token cầu nối trước đây được SINH MỚI mỗi lần khởi động
(`secrets.token_urlsafe` trong `bridge.py`), nên Router phải ghép lại
TỪNG LẦN AG0x khởi động lại — "không gõ tay token" chỉ đúng cho MỘT lần,
rồi lại phải gõ lại sau khi máy AG0x khởi động lại/khởi động máy tính.

Lưu cổng+token vào một tệp trong hồ sơ CỦA CHÍNH tài khoản AG0x (không
phải gốc dùng chung) và DÙNG LẠI ở lần khởi động sau — Router vẫn dùng
được thông tin ghép đã lưu từ trước, không cần ghép lại. Đây LÀ cách hiện
thực "tự kết nối lại, không gõ tay token khi khởi động lại bình thường".

KHÔNG PHẢI credential nhà cung cấp: đây là bí mật ỨNG DỤNG của Router
(giống token cầu nối vốn đã có), không phải OAuth/mật khẩu Google/Windows.
Khởi động lại cầu nối KHÔNG BAO GIỜ cần đăng nhập lại Google — `agy` tự
giữ phiên của nó ở nơi khác hoàn toàn, module này không chạm vào đó.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Optional, TypedDict


class DanhTinh(TypedDict):
    port: int
    token: str


def duong_danh_tinh(worker_id: str) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
               or str(Path.home()))
    return base / "FanficAudioStudio" / "router" / "identity" / f"{worker_id}.json"


def _siet_quyen_tep(p: Path) -> None:
    if os.name != "nt":
        return
    try:
        moi = dict(os.environ)
        moi["MSYS_NO_PATHCONV"] = "1"
        subprocess.run(["icacls", str(p), "/inheritance:r", "/grant:r",
                        f"{os.environ.get('USERNAME', '')}:(F)",
                        "/grant:r", "SYSTEM:(F)"],
                       capture_output=True, text=True, env=moi)
    except Exception:
        pass


def doc(worker_id: str) -> Optional[DanhTinh]:
    p = duong_danh_tinh(worker_id)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(d, dict) or "port" not in d or "token" not in d:
        return None
    return {"port": int(d["port"]), "token": str(d["token"])}


def _luu(worker_id: str, danh_tinh: DanhTinh) -> None:
    p = duong_danh_tinh(worker_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(danh_tinh), encoding="utf-8")
    _siet_quyen_tep(p)


def doc_hoac_tao(worker_id: str) -> DanhTinh:
    """Đọc danh tính đã lưu, hoặc sinh mới nếu chưa từng có.

    `port=0` khi sinh mới nghĩa là HĐH tự chọn cổng rảnh — cổng đó được
    LƯU LẠI để lần khởi động sau xin CHÍNH cổng đó, không phải một cổng
    ngẫu nhiên khác mỗi lần (đó là điều kiện để Router không phải ghép lại).
    """
    d = doc(worker_id)
    if d is not None:
        return d
    moi: DanhTinh = {"port": 0, "token": secrets.token_urlsafe(32)}
    _luu(worker_id, moi)
    return moi


def ghi_cong_that_su(worker_id: str, cong: int) -> None:
    """Sau khi bind thành công với `port=0` (HĐH tự chọn), ghi lại cổng
    THẬT vào tệp — lần sau xin đúng cổng đó thay vì lại xin 0."""
    d = doc(worker_id)
    if d is None:
        return
    if d["port"] != cong:
        d = {"port": cong, "token": d["token"]}
        _luu(worker_id, d)


def xoay_token(worker_id: str) -> DanhTinh:
    """Chủ động bỏ danh tính cũ — dùng khi nghi ngờ token bị lộ. Bắt buộc
    ghép lại ở lần khởi động sau (không phải hành vi mặc định)."""
    duong_danh_tinh(worker_id).unlink(missing_ok=True)
    return doc_hoac_tao(worker_id)
