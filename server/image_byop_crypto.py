"""
Ma hoa BYOP (Bring-Your-Own-Pollinations) — Image Studio V1, PHASE 4C.

TAI SU DUNG nguyen ven `ByokCrypto` (AES-256-GCM, AAD rang buoc theo
(user_id, provider_id)) tu `server/translation_byok_crypto.py` — KHONG viet
lai thuat toan ma hoa. Diem khac DUY NHAT: khoa master RIENG
(`IMAGE_BYOP_MASTER_KEY`), tach voi `TRANSLATION_BYOK_MASTER_KEY` — mat mot
khoa (vi du rotate sai) khong lam lo du lieu cua tinh nang kia, cung nguyen
tac voi viec tach `AppwriteSettings`/`R2Settings` trong `server/config.py`.

`provider_id` co dinh la `"pollinations_byop"` — xem
`server/image_domain.py::PollinationsConnection`.
"""

from __future__ import annotations

import os
from typing import Optional

from server.translation_byok_crypto import ByokConfigError, ByokCrypto, ByokDecryptError

PROVIDER_ID = "pollinations_byop"

__all__ = [
    "ByokConfigError",
    "ByokDecryptError",
    "PROVIDER_ID",
    "build_image_byop_crypto",
]


def build_image_byop_crypto(env: Optional[dict] = None) -> Optional[ByokCrypto]:
    """CHO PHEP RONG (tra `None`) khi `IMAGE_BYOP_MASTER_KEY` hoan toan VANG
    MAT — BYOP don gian bi khoa sau co (xem `image_byop_service.py`), giu dev/
    test khong co credential van chay duoc. Neu bien CO MAT ma SAI dinh dang
    thi nem loi NGAY, khong am tham chay tiep."""
    e = env if env is not None else os.environ
    gia_tri = (e.get("IMAGE_BYOP_MASTER_KEY", "") or "").strip()
    if not gia_tri:
        return None
    return ByokCrypto.tu_moi_truong(gia_tri)
