"""Khoa R2 cho hang doi danh gia — TAT DINH, dung chung boi CA HAI may.

Tach ra thanh module rieng vi ca farmer (AWS) lan may danh gia (Windows) deu
phai dan ra CUNG mot khoa cho cung mot tac pham. Neu moi ben tu ghep chuoi,
mot ben doi hau to la ban an bi ghi vao mot noi ben kia khong bao gio doc.

Nam duoi `review/` chu khong duoi `FanficWorld/production/`: day la du lieu
LAM VIEC cua duong day, khong phai san pham. San pham co bo cuc chinh tac
rieng o `server/farmer/canonical.py`.
"""
from __future__ import annotations

R2_OWNER = "svc_harvester"
REVIEW_PREFIX = f"review/{R2_OWNER}"


def sample_key(work_id: str) -> str:
    """Mau noi dung farmer gui di."""
    return f"{REVIEW_PREFIX}/samples/{work_id}.json"


def verdict_key(work_id: str) -> str:
    """Ban an co cau truc may danh gia ghi ve."""
    return f"{REVIEW_PREFIX}/verdicts/{work_id}.json"
