"""Kho BẰNG CHỨNG địa chỉ hoá theo nội dung — cùng khuôn với `attachments.py`.

Nội dung đầy đủ (một tóm tắt dài của worker, một log, một tin nhắn nghìn
dòng) KHÔNG vào SQLite: nó vào `blobs/<sha[:2]>/<sha>`, còn sổ chỉ giữ
`blob_sha`. Ba tính chất mua được, đúng như git:

  * **Trùng nội dung lưu đúng MỘT lần.** Cùng một tool output lặp qua 40
    lượt là một tệp. Lịch sử LOGIC vẫn đủ 40 dòng ở `su_kien`; lịch sử
    VẬT LÝ chỉ tốn một lần.
  * **Ghi lại là no-op.** Ghi cùng nội dung hai lần không cần khoá, không
    cần giao dịch — nên khôi phục sau sự cố miễn phí.
  * **Toàn vẹn kiểm được.** Băm lại là biết tệp có bị sửa. `kiem_toan_ven`
    làm đúng việc đó.

Nén zlib khi vượt `NEN_TU` byte. Lọc bí mật TRƯỚC khi băm và ghi — băm của
một bí mật cũng là một bí mật (đoán được bằng từ điển).

Đọc phải qua `sha` và đường dẫn đã `resolve()` phải nằm TRONG `goc` —
`attachments.py` bất biến #3, nguyên xi.
"""
from __future__ import annotations

import hashlib
import os
import zlib
from pathlib import Path
from typing import Dict, Optional, Tuple

from scripts.control_center.memory.bi_mat import loc
from scripts.control_center.memory.model import chuan_hoa

#: Nén từ ngưỡng này. Dưới đó nén không lợi, chỉ tốn CPU.
NEN_TU = 4096

#: Trần một blob. Vượt thì CẮT và ghi rõ trong meta — một log 2 GB không
#: được làm sổ ký ức phình theo. Đây là trần duy nhất của V0.6 và nó KHÔNG
#: xoá gì đã có.
TRAN_BLOB = 8 * 1024 * 1024


class BlobLoi(RuntimeError):
    pass


class KhoBlob:
    def __init__(self, goc: Path):
        self.goc = Path(goc).resolve()
        self.goc.mkdir(parents=True, exist_ok=True)

    # -- duong dan ---------------------------------------------------------

    def _duong(self, sha: str) -> Path:
        if not sha or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise BlobLoi(f"sha không hợp lệ: {sha!r}")
        p = (self.goc / sha[:2] / sha).resolve()
        try:
            p.relative_to(self.goc)
        except ValueError:
            raise BlobLoi("đường dẫn blob ra ngoài kho") from None
        return p

    # -- ghi ---------------------------------------------------------------

    def ghi(self, van: str) -> Tuple[str, int, int]:
        """`(sha, byte gốc, số lần lọc)`. Idempotent."""
        sach, n_loc = loc(chuan_hoa(van))
        if len(sach.encode("utf-8")) > TRAN_BLOB:
            sach = sach.encode("utf-8")[:TRAN_BLOB].decode("utf-8", "ignore")
            sach += "\n[... ĐÃ CẮT: blob vượt trần 8 MiB ...]"
        du = sach.encode("utf-8")
        sha = hashlib.sha256(du).hexdigest()
        p = self._duong(sha)
        if p.is_file():
            return sha, len(du), n_loc
        p.parent.mkdir(parents=True, exist_ok=True)
        # Mot byte dau danh dau cach goi: `R` = tho, `Z` = zlib.
        goi = (b"R" + du) if len(du) < NEN_TU else (b"Z" + zlib.compress(du, 6))
        tam = p.with_suffix(".tmp." + str(os.getpid()))
        tam.write_bytes(goi)
        # rename nguyen tu: khong bao gio co blob nua chung tren dia.
        os.replace(tam, p)
        return sha, len(du), n_loc

    # -- doc ---------------------------------------------------------------

    def doc(self, sha: str) -> Optional[str]:
        p = self._duong(sha)
        if not p.is_file():
            return None
        goi = p.read_bytes()
        if not goi:
            return ""
        if goi[:1] == b"Z":
            du = zlib.decompress(goi[1:])
        elif goi[:1] == b"R":
            du = goi[1:]
        else:                                  # ban cu / khong dau
            du = goi
        return du.decode("utf-8", "replace")

    def co(self, sha: str) -> bool:
        try:
            return self._duong(sha).is_file()
        except BlobLoi:
            return False

    def kiem_toan_ven(self, sha: str) -> bool:
        van = self.doc(sha)
        if van is None:
            return False
        return hashlib.sha256(van.encode("utf-8")).hexdigest() == sha

    # -- thong ke ----------------------------------------------------------

    def thong_ke(self) -> Dict[str, int]:
        so, byte = 0, 0
        if self.goc.is_dir():
            for d in self.goc.iterdir():
                if not d.is_dir():
                    continue
                for f in d.iterdir():
                    if f.is_file() and not f.name.endswith(".tmp"):
                        so += 1
                        try:
                            byte += f.stat().st_size
                        except OSError:
                            pass
        return {"so_blob": so, "byte_tren_dia": byte}
