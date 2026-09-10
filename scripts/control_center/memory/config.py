"""Cấu hình ký ức — khai báo, chỉ tham chiếu, không bao giờ chứa bí mật.

Cùng khuôn với `observability/config.py`: một tệp JSON đi theo gói
(`control_center/config/memory.json` — nằm trong `--add-data` sẵn có của
bản EXE, nên không cần dòng build mới), một tệp ghi đè theo bản cài
(`<gốc>/.router/memory.json`), và một bộ kiểm TỪ CHỐI cả tệp nếu thấy thứ
giống credential hay một khoá tên `password`/`secret`/`token`.

Hai thứ được cấu hình: NGÂN SÁCH token của khối ký ức, và các NGƯỞNG kích
hoạt điểm dừng. Không có "thư mục lưu" tuỳ ý — gốc ký ức luôn là
`<gốc>/.router/memory`, cạnh `control.db`, để hai sổ cùng vòng đời.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from scripts.control_center.memory.bi_mat import loc

TEP_MAC_DINH = Path(__file__).resolve().parents[1] / "config" / "memory.json"

KHOA_CAM = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|"
                      r"private[_-]?key)")

MAC_DINH: Dict[str, Any] = {
    "phien_ban": 1,
    "kich_hoat": True,
    "ngan_sach": {"tong": 2500, "vien_nang": 700, "diem_dung": 600,
                  "truy_hoi": 1000, "chi_muc": 200, "inline_toi_da": 400},
    "diem_dung": {"khi_viec_ket_thuc": True, "khi_tat_app": True,
                  "toi_thieu_cach_giay": 20},
    "truy_hoi": {"toi_da_ung_vien": 60, "gan_day": 12},
    "ghi_chu": "Tham chiếu credential chỉ bằng BÍ DANH (credential_alias), "
               "không bao giờ là giá trị.",
}


class CauHinhLoi(ValueError):
    pass


def kiem_cau_hinh(d: Dict[str, Any], *, nguon: str = "") -> None:
    """Từ chối cả tệp nếu có bí mật hoặc khoá tên nhạy cảm."""
    van = json.dumps(d, ensure_ascii=False)
    _, n = loc(van)
    if n:
        raise CauHinhLoi(f"{nguon or 'cấu hình'} chứa {n} chuỗi giống credential "
                         f"— tệp cấu hình chỉ được giữ tham chiếu/bí danh")

    def _di(x, duong=""):
        if isinstance(x, dict):
            for k, v in x.items():
                if KHOA_CAM.search(str(k)) and k != "credential_alias":
                    raise CauHinhLoi(f"{nguon}: khoá {duong}/{k} có tên nhạy cảm")
                _di(v, f"{duong}/{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                _di(v, f"{duong}[{i}]")

    _di(d)
    ns = d.get("ngan_sach") or {}
    for k in ("tong", "vien_nang", "diem_dung", "truy_hoi", "chi_muc",
              "inline_toi_da"):
        if k in ns and (not isinstance(ns[k], int) or ns[k] <= 0):
            raise CauHinhLoi(f"{nguon}: ngan_sach.{k} phải là số nguyên dương")


def _doc(p: Path) -> Optional[Dict[str, Any]]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def nap(*, goc: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    """`(cấu hình hiệu lực, đường tệp đã dùng)`. Luôn trả về được."""
    d = dict(MAC_DINH)
    duong = "mặc định (mã)"
    for p in (TEP_MAC_DINH, (Path(goc) / ".router" / "memory.json") if goc else None):
        if p is None:
            continue
        x = _doc(p)
        if x is None:
            continue
        kiem_cau_hinh(x, nguon=str(p))
        # Gop nong: tung khoa cap 1 la dict thi cap nhat, khong thi thay.
        for k, v in x.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                d[k] = {**d[k], **v}
            else:
                d[k] = v
        duong = str(p)
    return d, duong
