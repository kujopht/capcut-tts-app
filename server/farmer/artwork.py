"""Sinh anh bia + anh nen TAT DINH bang ffmpeg.

## Vi sao ffmpeg chu khong phai Pillow

Pillow KHONG co trong venv cua may san xuat; ffmpeg thi CO (ca tren AWS lan
may Windows — duong day TTS da phu thuoc vao no). Them mot goi Python vao mot
venv thuoc root tren may dang chay san xuat la mot thay doi ha tang that; goi
mot nhi phan da co thi khong.

## Vi sao khong ve chu len anh

Ve chu can mot tep font, va duong dan font khac nhau giua Windows va Linux —
mot phu thuoc am tham nua de hong o dung noi kho sua nhat. `CoverPipelineService`
da co san co che chen tieu de TAT DINH cho SVG; module nay chi lo phan NEN.
Bia khong chu van la mot bia hop le, va no khong bao gio sai chinh ta.

## Tat dinh

Mau duoc dan ra tu `work_id` bang sha256. Cung mot tac pham luon ra cung mot
cap mau, nen mot lan chay lai khong tao ra anh khac — va khong lam hong tinh
idempotent cua kho luu tru.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

#: Kich thuoc chuan. Bia doc (ti le bia sach); nen ngang (dung lam banner).
COVER_SIZE = "1024x1536"
BACKGROUND_SIZE = "1920x1080"

#: Bang mau nen — do bao hoa vua phai de chu trang de doc khi giao dien phu
#: tieu de len tren.
_PALETTE = (
    ("0f2027", "2c5364"), ("232526", "414345"), ("1f1c2c", "928dab"),
    ("0b486b", "f56217"), ("2b5876", "4e4376"), ("42275a", "734b6d"),
    ("141e30", "243b55"), ("3a1c71", "d76d77"),
)


class ArtworkError(RuntimeError):
    """Khong sinh duoc anh. Ben goi phai de tac pham o ARTWORK_PENDING."""


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise ArtworkError("khong tim thay ffmpeg — khong sinh duoc anh")
    return binary


def colours_for(work_id: str) -> Tuple[str, str]:
    """Cap mau TAT DINH cho mot tac pham."""
    digest = hashlib.sha256(work_id.encode("utf-8")).hexdigest()
    return _PALETTE[int(digest[:8], 16) % len(_PALETTE)]


def _render(size: str, c0: str, c1: str, out: Path) -> None:
    """Mot khung hinh webp. Thu `gradients` truoc, roi roi ve mau don.

    `gradients` la mot filter tuong doi moi; mot ban ffmpeg cu se khong co no.
    Roi ve `color` (co o moi ban) la co y: mot nen don sac van la mot nen hop
    le, va no tot hon la khong co anh nao ca.
    """
    binary = _ffmpeg()
    thu = [
        [binary, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i",
         f"gradients=s={size}:c0=0x{c0}:c1=0x{c1}:duration=1:speed=0",
         "-frames:v", "1", str(out)],
        [binary, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=0x{c0}:s={size}",
         "-frames:v", "1", str(out)],
    ]
    loi = ""
    for argv in thu:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=120, encoding="utf-8",
                                  errors="replace")
        except Exception as exc:                                # noqa: BLE001
            loi = f"{type(exc).__name__}: {exc}"
            continue
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return
        loi = (proc.stderr or "").strip()[-200:]
    raise ArtworkError(f"ffmpeg khong sinh duoc {out.name}: {loi}")


def generate(work_id: str) -> Tuple[bytes, bytes]:
    """(cover_webp, background_webp) — TAT DINH theo `work_id`."""
    c0, c1 = colours_for(work_id)
    with tempfile.TemporaryDirectory(prefix="farmer-art-") as tmp:
        thu_muc = Path(tmp)
        bia = thu_muc / "cover.webp"
        nen = thu_muc / "background.webp"
        _render(COVER_SIZE, c0, c1, bia)
        # Dao mau cho anh nen de no phan biet duoc voi bia khi hai cai nam
        # canh nhau tren giao dien.
        _render(BACKGROUND_SIZE, c1, c0, nen)
        return bia.read_bytes(), nen.read_bytes()
