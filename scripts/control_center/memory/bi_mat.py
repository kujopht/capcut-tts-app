"""Lọc bí mật Ở CỔNG VÀO của ký ức — mạnh hơn `packet.redact`, và phải thế.

`router_v3.packet.redact()` là bộ lọc chuẩn của kho, và bộ này PHỦ nó (có
bài kiểm đòi thế). Nhưng nó được viết cho một đường VỀ của worker; một lớp
KÝ ỨC nuốt mọi thứ — tin nhắn người dùng dán vội, tóm tắt tool, log — và
giữ lại VĨNH VIỄN, nên ba khoảng trống của `redact()` ở đây thành lỗi thật:

  * `-----BEGIN ... PRIVATE KEY-----` chỉ thay ĐÚNG DÒNG ĐẦU, để nguyên
    thân khoá base64 phía dưới. Ở đây cả khối BEGIN…END bị thay.
  * Không có AWS (`AKIA…`), Slack (`xox…`), Google (`AIza…`), GitLab,
    npm, Bearer, `password=…`, `user:pass@host`. Ở đây có.
  * `.env`-shape (`KEY=value` với tên khoá nhạy cảm) không có. Ở đây có.

Trả về CẢ số lần lọc, để bản ghi mang `da_loc=N` — người đọc biết "chỗ này
từng có một thứ giống credential" mà không bao giờ thấy nó.
"""
from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from scripts.router_v3.packet import _MAU_BI_MAT as _MAU_GOC, REDACTED

DA_LOC = REDACTED   # cùng nhãn với phần còn lại của kho: `[DA-LOC]`

#: Khối PEM TRỌN — thay cả thân, không chỉ dòng đầu.
_KHOI_PEM = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.S)

#: Thêm so với `packet` — thứ một lớp ký ức sẽ gặp.
_MAU_THEM: Sequence[re.Pattern] = (
    _KHOI_PEM,
    # KHONG dung `\b` hai dau: hai khoa dan sat nhau (`AKIA…QAKIA…`) khong
    # co ranh tu o giua, va `\b` lam mau bo qua khoa thu hai. Tien to
    # `AKIA`/`ASIA` + 16 ky tu hoa/so da du dac trung.
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{15,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    # KEY=value / key: value voi ten khoa nhay cam. Giu ten, loc gia tri.
    re.compile(r"(?i)\b((?:[A-Z0-9_]*(?:PASS(?:WORD)?|PASSWD|SECRET|TOKEN|"
               r"API[_-]?KEY|PRIVATE[_-]?KEY|ACCESS[_-]?KEY|AUTH)[A-Z0-9_]*)"
               r"\s*[:=]\s*['\"]?)([^\s'\"#,;]{8,})"),
    re.compile(r"(?i)(://[^/\s:@]+:)([^/\s@]{4,})(@)"),
)

#: THU TU QUAN TRONG: mau THEM chay TRUOC mau goc. Mau goc thay rieng dong
#: `-----BEGIN ... PRIVATE KEY-----` bang `[DA-LOC]`; neu no chay truoc thi
#: moc BEGIN bien mat va mau "ca khoi PEM" khong con gi de khop — than khoa
#: base64 nam lai nguyen ven. Do duoc bang bai kiem, khong phai suy.
_TAT_CA: Sequence[re.Pattern] = tuple(_MAU_THEM) + tuple(_MAU_GOC)


def loc(van: str) -> Tuple[str, int]:
    """`(văn bản đã lọc, số lần lọc)`. Không bao giờ ném."""
    ra = str(van or "")
    dem = 0
    for mau in _TAT_CA:
        if mau.groups >= 2:
            # Mau giu ten khoa (nhom 1), loc gia tri (nhom 2).
            def _thay(m):
                if m.lastindex and m.lastindex >= 3:
                    return f"{m.group(1)}{DA_LOC}{m.group(3)}"
                return f"{m.group(1)}{DA_LOC}"
            ra, n = mau.subn(_thay, ra)
        else:
            ra, n = mau.subn(DA_LOC, ra)
        dem += n
    return ra, dem


def loc_dict(d: dict) -> Tuple[dict, int]:
    """Lọc mọi chuỗi trong một dict (đệ quy, giữ khoá)."""
    tong = 0

    def _di(x):
        nonlocal tong
        if isinstance(x, str):
            y, n = loc(x)
            tong += n
            return y
        if isinstance(x, dict):
            return {k: _di(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [_di(v) for v in x]
        return x

    return _di(dict(d or {})), tong


def mau_goc() -> List[str]:
    """Mẫu của `packet` — để bài kiểm khẳng định bộ này PHỦ bộ gốc."""
    return [m.pattern for m in _MAU_GOC]


def mau_tat_ca() -> List[str]:
    return [m.pattern for m in _TAT_CA]
