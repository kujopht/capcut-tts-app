#!/usr/bin/env python3
"""
BAO CAO (chi doc) cho nghi van lich su: chuoi rong tren `profiles.last_read_at`/
`last_listen_at`/`last_watch_at` co the tung bi Appwrite tu dien thanh gio
server HIEN TAI thay vi rong that (xem `appwrite-datetime-empty-string-quirk`,
phat hien o Phase 6/hardening, nhanh feature/admin-trusted-video-v2).

DAY LA VIEC HOAN LAI (Phase 7, muc 10) — CHUA thuc thi sua du lieu that.
Script nay CHI DOC, KHONG BAO GIO ghi — khong co duong mutate nao duoc
hien thuc trong file nay, kill CA KHI goi nham mot co (khong ton tai) cung
khong lam gi ca. Dung de:

    1. Chay THU truoc tren Appwrite tu luu tru DEV (an toan, du lieu khong
       quan trong) de xac nhan logic phat hien dung.
    2. Sau khi Appwrite Cloud production duoc khoi phuc quota/truy cap, chay
       LAI script nay TRO VE production (chi doc) de co SO LUONG ung vien
       that va DANH SACH user_id nghi van.
    3. Nguoi van hanh TU QUYET DINH co can sua khong, va neu can, viet MOT
       script sua RIENG (co --apply, co xac nhan tay, co backup truoc) dua
       tren danh sach ung vien script nay in ra — KHONG mo rong script nay
       de tu sua, giu triet ly "dry-run truoc, con nguoi duyet, sua sau"
       tach biet ro rang giua hai buoc.

HEURISTIC PHAT HIEN (suy doan, KHONG chac chan 100% — ghi ro trong bao cao):
mot ho so la UNG VIEN NGHI VAN neu `last_X_at` KHAC RONG nhung con tro noi
dung tuong ung (novel_id/chapter_id cho doc, novel_id/chapter_id cho nghe,
series_id/episode_id cho xem) LAI RONG — day la to hop KHONG THE xay ra qua
luong ghi binh thuong (moi lan set `last_read_at` deu di kem dat
`last_read_novel_id`/`last_read_chapter_id` cung luc, xem
`server/main.py` cac route `/api/progress/*`), nen no la dau hieu MOT
GHI DE AM THAM tu tat Appwrite (chuoi rong -> gio hien tai) khi mot lan
`save_profile()` khac (vd doi bio/avatar) vo tinh gui chuoi rong cho
truong nay TRUOC khi ma sua o Phase 7 hardening duoc trien khai.

KHONG suy doan nguoc: mot ho so co CA hai (timestamp VA con tro noi dung)
deu KHONG duoc coi la nghi van, du timestamp co the (hoac khong the) van
dung — script nay CHI bao nhung truong hop chac chan la BAT THUONG VE CAU
TRUC, khong doan mo ho.

Chay (chi doc, an toan tren MOI moi truong ke ca production sau nay):
    .venv\\Scripts\\python.exe -m scripts.audit_profiles_datetime_dry_run

Chi doc tu Appwrite dev tu luu tru cua du an nay (mac dinh, AN TOAN de thu):
    FAS_ENV_FILE=server/.env.selfhost \\
      .venv\\Scripts\\python.exe -m scripts.audit_profiles_datetime_dry_run

KHONG BAO GIO in user_id/email ra ngoai pham vi can thiet cho bao cao noi
bo nay — nhung day van la du lieu quan tri, dung chia se man hinh/log cong
khai.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TRANG_BI_CHAN = 100


def _q_limit(n: int) -> str:
    return json.dumps({"method": "limit", "values": [n]})


def _q_offset(n: int) -> str:
    return json.dumps({"method": "offset", "values": [n]})


def _quet_toan_bo_profiles(identity: Any, database_id: str) -> List[Dict[str, Any]]:
    """
    CHI DOC — phan trang qua `GET /v1/databases/{db}/collections/profiles/
    documents`, KHONG co lenh POST/PATCH/DELETE nao trong ham nay.

    So luong profiles du kien o quy mo vai chuc nghin, KHONG phai hang trieu
    — quet toan bang MOT LAN cho MOT bao cao thu thang la chap nhan duoc
    (khac voi dashboard/route phuc vu request, noi quet toan bang la cam,
    xem `docs/handoffs/admin-trusted-video-v2-handoff.md` muc 6). Neu du an
    nay lon hon nhieu trong tuong lai, phan trang co san o day van an toan
    (chi cham hon), khong can sua lai.
    """
    path = f"/v1/databases/{database_id}/collections/profiles/documents"
    ra: List[Dict[str, Any]] = []
    offset = 0
    while True:
        data = identity._request(  # noqa: SLF001 — script noi bo, khong phai API cong khai
            "GET", path, params={"queries[]": [_q_limit(TRANG_BI_CHAN), _q_offset(offset)]})
        trang = list(data.get("documents") or [])
        ra.extend(trang)
        if len(trang) < TRANG_BI_CHAN:
            return ra
        offset += TRANG_BI_CHAN


def _la_ung_vien(doc: Dict[str, Any]) -> List[str]:
    """Tra ve danh sach TEN TRUONG nghi van tren MOT ho so (rong = khong nghi
    van gi). Xem heuristic day du o docstring dau file."""
    nghi_van: List[str] = []
    if doc.get("last_read_at") and not (
            doc.get("last_read_novel_id") or doc.get("last_read_chapter_id")):
        nghi_van.append("last_read_at")
    if doc.get("last_listen_at") and not (
            doc.get("last_listen_novel_id") or doc.get("last_listen_chapter_id")):
        nghi_van.append("last_listen_at")
    if doc.get("last_watch_at") and not (
            doc.get("last_watch_series_id") or doc.get("last_watch_episode_id")):
        nghi_van.append("last_watch_at")
    return nghi_van


def chay() -> int:
    from server.appwrite_adapter import AppwriteIdentityAdapter
    from server.config import load_settings

    settings = load_settings()
    if not settings.appwrite.configured:
        print("LỖI: thiếu cấu hình Appwrite — chạy với "
             "FAS_ENV_FILE=server/.env.selfhost để thử trên dev, hoặc trỏ "
             "biến môi trường Appwrite thật khi sẵn sàng chạy trên production.")
        return 1

    print(f"Endpoint  : {settings.appwrite.endpoint}")
    print(f"Database  : {settings.appwrite.database_id}")
    print("Chế độ    : CHỈ ĐỌC — không có đường ghi nào trong script này.")
    print()

    identity = AppwriteIdentityAdapter(settings.appwrite)
    docs = _quet_toan_bo_profiles(identity, settings.appwrite.database_id)

    ung_vien: List[Dict[str, Any]] = []
    for doc in docs:
        truong = _la_ung_vien(doc)
        if truong:
            ung_vien.append({
                "user_id": str(doc.get("user_id") or doc.get("$id") or ""),
                "truong_nghi_van": truong,
            })

    print(f"Tổng số hồ sơ đã quét : {len(docs)}")
    print(f"Ứng viên nghi vấn     : {len(ung_vien)}")
    print()
    if ung_vien:
        print("Danh sách (chỉ user_id + trường nghi vấn, KHÔNG in email):")
        for u in ung_vien:
            print(f"  {u['user_id']:24} {', '.join(u['truong_nghi_van'])}")
        print()
        print("LƯU Ý: đây là heuristic (xem docstring đầu file) — hãy xác")
        print("nhận lại vài hồ sơ bằng tay trước khi coi là chắc chắn. Việc")
        print("SỬA (đặt lại các trường trên về rỗng) KHÔNG được thực hiện ở")
        print("đây — cần một script riêng, có --apply, có xác nhận tay, có")
        print("backup/export trước khi đổi, theo đúng yêu cầu Phase 7 mục 10.")
    else:
        print("Không tìm thấy ứng viên nào theo heuristic hiện tại.")

    return 0


if __name__ == "__main__":
    sys.exit(chay())
